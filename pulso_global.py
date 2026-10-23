#!/usr/bin/env python3
"""
Pulso Global - terminal de indicadores económicos mundiales.

Backend (solo librería estándar) que agrega APIs públicas y gratuitas, calcula
métricas y alertas, y sirve la interfaz web (index.html + static/).

Fuentes (sin API key):
  Yahoo Finance (chart)  índices, materias primas, VIX, bono 10Y, DXY, cripto
  Frankfurter (BCE)      divisas
  mindicador.cl          Chile: dólar, UF, UTM, TPM, IPC, cobre, desempleo, IMACEC
  Banco Mundial          inflación, crecimiento del PIB y desempleo por país
  alternative.me         índice Fear & Greed (sentimiento cripto)
Variables de entorno: HOST, PORT, LOG_LEVEL (equivalentes a --host, --puerto, --log).
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import signal
import statistics
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

LOG = logging.getLogger("pulso")
AQUI = Path(__file__).resolve().parent
STATIC = AQUI / "static"
TIPOS = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
         ".woff2": "font/woff2", ".webmanifest": "application/manifest+json"}
UA = {"User-Agent": "Mozilla/5.0 (compatible; PulsoGlobal/1.0)", "Accept": "application/json"}
TTL_MERCADO = 60          # segundos que se reutiliza un snapshot
TTL_MACRO = 6 * 3600      # el Banco Mundial cambia una vez al año
UMBRAL_Z = 2.0
UMBRAL_VAR = {"indices": 2.0, "commodities": 3.0, "riesgo": 8.0, "cripto": 6.0, "fx": 1.0, "chile": 1.5}
UMBRAL_PB = 10.0          # puntos base para tasas (bono 10Y)


# --------------------------------------------------------------------------
# Catálogo de instrumentos
# --------------------------------------------------------------------------
def spec(id, sym, name, group, unit, dec, **extra):
    return dict(id=id, sym=sym, name=name, group=group, unit=unit, dec=dec, **extra)


YAHOO = [
    spec("spx", "^GSPC", "S&P 500", "indices", "pts", 2),
    spec("ndx", "^IXIC", "Nasdaq Composite", "indices", "pts", 2),
    spec("dji", "^DJI", "Dow Jones", "indices", "pts", 2),
    spec("sx5e", "^STOXX50E", "Euro Stoxx 50", "indices", "pts", 2),
    spec("ftse", "^FTSE", "FTSE 100", "indices", "pts", 2),
    spec("n225", "^N225", "Nikkei 225", "indices", "pts", 2),
    spec("hsi", "^HSI", "Hang Seng", "indices", "pts", 2),
    spec("bvsp", "^BVSP", "Bovespa", "indices", "pts", 0),
    spec("ipsa", "^IPSA", "IPSA (Chile)", "indices", "pts", 2),
    spec("vix", "^VIX", "VIX · volatilidad", "riesgo", "pts", 2),
    spec("tnx", "^TNX", "Bono EE.UU. 10 años", "riesgo", "%", 3, rate=True),
    spec("dxy", "DX-Y.NYB", "Índice dólar (DXY)", "riesgo", "pts", 2),
    spec("gold", "GC=F", "Oro", "commodities", "USD/oz", 2),
    spec("silver", "SI=F", "Plata", "commodities", "USD/oz", 2),
    spec("wti", "CL=F", "Petróleo WTI", "commodities", "USD/bbl", 2),
    spec("brent", "BZ=F", "Petróleo Brent", "commodities", "USD/bbl", 2),
    spec("copper", "HG=F", "Cobre", "commodities", "USD/lb", 3),
    spec("gas", "NG=F", "Gas natural", "commodities", "USD/MMBtu", 3),
    spec("btc", "BTC-USD", "Bitcoin", "cripto", "USD", 2),
    spec("eth", "ETH-USD", "Ethereum", "cripto", "USD", 2),
    spec("sol", "SOL-USD", "Solana", "cripto", "USD", 2),
]

FX = [
    spec("eurusd", "EUR/USD", "Euro / Dólar", "fx", "USD", 4, ccy="EUR", inv=True),
    spec("gbpusd", "GBP/USD", "Libra / Dólar", "fx", "USD", 4, ccy="GBP", inv=True),
    spec("usdjpy", "USD/JPY", "Dólar / Yen", "fx", "JPY", 2, ccy="JPY"),
    spec("usdcny", "USD/CNY", "Dólar / Yuan", "fx", "CNY", 4, ccy="CNY"),
    spec("usdbrl", "USD/BRL", "Dólar / Real", "fx", "BRL", 4, ccy="BRL"),
    spec("usdmxn", "USD/MXN", "Dólar / Peso mexicano", "fx", "MXN", 4, ccy="MXN"),
    spec("usdchf", "USD/CHF", "Dólar / Franco suizo", "fx", "CHF", 4, ccy="CHF"),
]

CHILE_SERIES = [
    spec("usdclp", "USD/CLP", "Dólar observado", "chile", "CLP", 2, codigo="dolar"),
    spec("uf", "UF", "Unidad de Fomento", "chile", "CLP", 2, codigo="uf", sinextremos=True),
    spec("cobre", "Cu", "Cobre (Cochilco)", "chile", "USD/lb", 3, codigo="libra_cobre"),
]
# (clave en mindicador, nombre, unidad, decimales)
CHILE_STATS = [
    ("tpm", "Tasa de política monetaria", "%", 2),
    ("ipc", "IPC · variación mensual", "%", 2),
    ("tasa_desempleo", "Desempleo", "%", 1),
    ("imacec", "IMACEC · variación anual", "%", 1),
    ("utm", "UTM", "CLP", 0),
]

PAISES = {"USA": "EE.UU.", "CHN": "China", "DEU": "Alemania", "JPN": "Japón", "GBR": "Reino Unido",
          "IND": "India", "BRA": "Brasil", "MEX": "México", "CHL": "Chile", "ESP": "España"}
MACRO = {"inflacion": ("FP.CPI.TOTL.ZG", "Inflación anual"),
         "pib": ("NY.GDP.MKTP.KD.ZG", "Crecimiento del PIB"),
         "desempleo": ("SL.UEM.TOTL.ZS", "Desempleo")}


# --------------------------------------------------------------------------
# Utilidades HTTP y métricas
# --------------------------------------------------------------------------
def http_json(url: str, timeout: int = 12, reintentos: int = 1):
    ultimo: Exception | None = None
    for intento in range(reintentos + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:  # red, HTTP o JSON inválido
            ultimo = e
            if intento < reintentos:
                time.sleep(0.5)
    raise ultimo or RuntimeError("no se realizó ningún intento")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def zscore(vals: list[float], ventana: int = 30) -> float:
    """z-score del último retorno diario frente a los `ventana` anteriores."""
    ret = [b / a - 1 for a, b in zip(vals, vals[1:]) if a]
    hist = ret[-ventana - 1:-1]
    if len(hist) < 10:
        return 0.0
    sd = statistics.stdev(hist)
    return (ret[-1] - statistics.fmean(hist)) / sd if sd else 0.0


def variacion_30d(fechas: list[str], vals: list[float], rate: bool = False) -> float:
    corte = (date.fromisoformat(fechas[-1]) - timedelta(days=30)).isoformat()
    idx = 0
    for i, f in enumerate(fechas):
        if f <= corte:
            idx = i
    base = vals[idx]
    return (vals[-1] - base) * 100 if rate else ((vals[-1] / base - 1) * 100 if base else 0.0)


def evaluar_alertas(s: dict, chg1: float, z: float, vals: list[float]) -> list[dict]:
    out = []
    rate = s.get("rate", False)
    umbral = UMBRAL_PB if rate else UMBRAL_VAR.get(s["group"], 2.0)
    if abs(chg1) >= umbral:
        out.append({"tipo": "variacion", "nivel": "alta" if abs(chg1) >= umbral * 1.5 else "media",
                    "valor": round(chg1, 2), "umbral": umbral, "unidad": "pb" if rate else "%"})
    if abs(z) >= UMBRAL_Z:
        out.append({"tipo": "atipico", "nivel": "alta" if abs(z) >= 3 else "media", "valor": round(z, 1)})
    if len(vals) >= 40 and not s.get("sinextremos"):
        if vals[-1] >= max(vals):
            out.append({"tipo": "maximo", "nivel": "info"})
        elif vals[-1] <= min(vals):
            out.append({"tipo": "minimo", "nivel": "info"})
    return out


def construir_item(s: dict, fechas: list[str], vals: list[float], fuente: str) -> dict:
    rate = s.get("rate", False)
    ult, prev = vals[-1], vals[-2]
    chg1 = (ult - prev) * 100 if rate else ((ult / prev - 1) * 100 if prev else 0.0)
    z = zscore(vals)
    return {
        "id": s["id"], "name": s["name"], "sym": s["sym"], "group": s["group"], "unit": s["unit"],
        "dec": s["dec"], "kind": "serie", "rate": rate, "value": round(ult, 6),
        "chg1": round(chg1, 4), "chg1u": "pb" if rate else "%",
        "chg30": round(variacion_30d(fechas, vals, rate), 4), "chg30u": "pb" if rate else "%",
        "sma7": round(statistics.fmean(vals[-7:]), 6), "sma30": round(statistics.fmean(vals[-30:]), 6),
        "z": round(z, 2), "min": round(min(vals), 6), "max": round(max(vals), 6),
        "dates": fechas, "series": [round(v, 6) for v in vals],
        "alerts": evaluar_alertas(s, chg1, z, vals), "source": fuente,
    }


def construir_stat(clave: str, nombre: str, unidad: str, dec: int, valor: float, fecha: str, fuente: str) -> dict:
    return {"id": clave, "name": nombre, "sym": "", "group": "chile", "unit": unidad, "dec": dec, "kind": "stat",
            "value": valor, "fecha": fecha, "dates": [], "series": [], "alerts": [], "source": fuente}


# --------------------------------------------------------------------------
# Parsers (puros, testeables sin red)
# --------------------------------------------------------------------------
def parse_yahoo(payload: dict):
    res = payload["chart"]["result"][0]
    meta = res.get("meta", {})
    ts = res.get("timestamp") or []
    cierres = res["indicators"]["quote"][0].get("close") or []
    pts = [(t, c) for t, c in zip(ts, cierres) if c is not None]
    if not pts:
        raise ValueError("serie vacía")
    fechas = [_iso(t) for t, _ in pts]
    vals = [float(c) for _, c in pts]
    precio = meta.get("regularMarketPrice")
    mtime = meta.get("regularMarketTime") or pts[-1][0]
    if precio is not None:
        if mtime - pts[-1][0] < 86400:      # la última vela es la de hoy: usar el precio en vivo
            vals[-1] = float(precio)
        else:
            fechas.append(_iso(mtime))
            vals.append(float(precio))
    return fechas, vals


def parse_frankfurter(payload: dict) -> dict[str, tuple[list[str], list[float]]]:
    dias = sorted(payload["rates"])
    out: dict[str, tuple[list[str], list[float]]] = {}
    for d in dias:
        for ccy, v in payload["rates"][d].items():
            f, x = out.setdefault(ccy, ([], []))
            f.append(d)
            x.append(float(v))
    return out


def parse_mindicador_serie(payload: dict, hoy: date | None = None, max_dias: int = 95):
    hoy = hoy or date.today()
    por_fecha = {}
    for p in payload.get("serie", []):
        d = p["fecha"][:10]
        if d <= hoy.isoformat() and p.get("valor") is not None:
            por_fecha[d] = float(p["valor"])
    dias = sorted(por_fecha)[-max_dias:]
    return dias, [por_fecha[d] for d in dias]


def parse_worldbank(payload: list) -> list[dict]:
    filas = payload[1] if len(payload) > 1 and payload[1] else []
    out = []
    for r in filas:
        if r.get("value") is None:
            continue
        iso = r.get("countryiso3code") or ""
        out.append({"iso": iso, "pais": PAISES.get(iso, r["country"]["value"]),
                    "valor": round(float(r["value"]), 2), "anio": int(r["date"])})
    return sorted(out, key=lambda x: -x["valor"])


def parse_fng(payload: dict) -> dict:
    datos = payload["data"]                      # más reciente primero
    hist = [int(x["value"]) for x in reversed(datos)]
    return {"value": hist[-1], "label": datos[0].get("value_classification", ""), "history": hist,
            "dates": [_iso(int(x["timestamp"])) for x in reversed(datos)]}


# --------------------------------------------------------------------------
# Fuentes: cada una devuelve (datos, estado)
# --------------------------------------------------------------------------
def fuente_yahoo():
    def uno(s):
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(s['sym'])}?range=3mo&interval=1d"
            fechas, vals = parse_yahoo(http_json(url))
            return construir_item(s, fechas, vals, "Yahoo Finance")
        except Exception as e:
            return e

    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(uno, YAHOO))
    items = [r for r in res if isinstance(r, dict)]
    fallidos = [s["name"] for s, r in zip(YAHOO, res) if not isinstance(r, dict)]
    if not items:
        raise RuntimeError(f"sin respuesta ({res[0]})")
    estado = {"estado": "ok" if not fallidos else "parcial", "n": len(items), "fallidos": fallidos}
    return items, estado


def fuente_frankfurter():
    items, per_usd = [], {"USD": 1.0}
    hoy = date.today()
    syms = ",".join(s["ccy"] for s in FX)
    url = f"https://api.frankfurter.dev/v1/{hoy - timedelta(days=95)}..{hoy}?base=USD&symbols={syms}"
    por_ccy = parse_frankfurter(http_json(url))
    for s in FX:
        fechas, vals = por_ccy[s["ccy"]]
        per_usd[s["ccy"]] = vals[-1]
        if s.get("inv"):
            vals = [1 / v for v in vals]
        items.append(construir_item(s, fechas, vals, "Frankfurter · BCE"))
    return (items, per_usd), {"estado": "ok", "n": len(items)}


MINDICADOR_HOSTS = ("https://mindicador.cl", "https://www.mindicador.cl")
TIMEOUT_CHILE = 6            # segundos por petición
PRESUPUESTO_CHILE = 14       # segundos máximos por actualización completa de Chile
TTL_CHILE = 15 * 60          # los datos son diarios: no se piden cada minuto
REINTENTO_CHILE = 2 * 60     # espera antes de reintentar algo que acaba de fallar
EDAD_MAX_DISCO = 3 * 86400   # datos guardados en disco más viejos que esto se ignoran
ESPERA_REINTENTO = 1.0       # pausa entre reintentos de una misma petición
PAUSA_CHILE = 0.3            # pausa entre peticiones (no saturar al servidor)
CACHE_CHILE = AQUI / "cache" / "chile.json"


def mindicador_json(ruta: str, hasta: float | None = None):
    """mindicador.cl es lento e inestable: prueba ambos hosts (y uno más de nuevo),
    con pausa entre intentos y respetando el tiempo máximo `hasta`."""
    ultimo: Exception | None = None
    hosts = (*MINDICADOR_HOSTS, MINDICADOR_HOSTS[0])
    for n, host in enumerate(hosts):
        if hasta is not None and time.time() > hasta:
            raise ultimo or TimeoutError("tiempo máximo agotado")
        try:
            return http_json(host + ruta, timeout=TIMEOUT_CHILE, reintentos=0)
        except Exception as e:
            ultimo = e
            if n < len(hosts) - 1:
                time.sleep(ESPERA_REINTENTO)
    raise ultimo or RuntimeError("no se realizó ningún intento")


def _err(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"[:140]


def _hace(seg: float) -> str:
    m = int(seg // 60)
    return f"{m} min" if m < 90 else (f"{m // 60} h" if m < 2880 else f"{m // 1440} días")


# Caché de Chile: clave -> (momento, dato); y fallos recientes: clave -> (momento, mensaje)
_chile: dict = {"datos": {}, "fallos": {}, "disco": False}
_chile_lock = threading.Lock()


def reiniciar_chile():
    _chile.update(datos={}, fallos={}, disco=False)


def _cargar_disco():
    if _chile["disco"]:
        return
    _chile["disco"] = True
    try:
        crudo = json.loads(CACHE_CHILE.read_text(encoding="utf-8"))
        ahora = time.time()
        for clave, (ts, dato) in crudo.items():
            if ahora - ts < EDAD_MAX_DISCO and clave not in _chile["datos"]:
                _chile["datos"][clave] = (ts, dato)
    except Exception:
        pass   # sin caché o archivo dañado: se ignora


def _guardar_disco():
    try:
        CACHE_CHILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_CHILE.write_text(json.dumps({k: list(v) for k, v in _chile["datos"].items()},
                                          ensure_ascii=False, allow_nan=False), encoding="utf-8")
    except Exception:
        pass


def _chile_obtener(clave: str, descargar, hasta: float):
    """Devuelve (dato, error, momento_del_dato). Usa la caché mientras sea reciente;
    si hay que pedirlo y falla, devuelve el último dato bueno junto con el error."""
    ahora = time.time()
    previo = _chile["datos"].get(clave)
    if previo and ahora - previo[0] < TTL_CHILE:
        return previo[1], None, previo[0]
    fallo = _chile["fallos"].get(clave)
    if not fallo or ahora - fallo[0] >= REINTENTO_CHILE:
        try:
            dato = descargar(hasta)
        except Exception as e:
            fallo = _chile["fallos"][clave] = (ahora, _err(e))
        else:
            _chile["datos"][clave] = (time.time(), dato)
            _chile["fallos"].pop(clave, None)
            _guardar_disco()
            time.sleep(PAUSA_CHILE)
            return dato, None, time.time()
    return (previo[1] if previo else None), fallo[1], (previo[0] if previo else 0.0)


def _descargar_serie(s: dict, anio: int):
    def f(hasta):
        fechas, vals = parse_mindicador_serie(mindicador_json(f"/api/{s['codigo']}/{anio}", hasta))
        if len(vals) < 45:   # inicio de año: completar con el anterior
            f0, v0 = parse_mindicador_serie(mindicador_json(f"/api/{s['codigo']}/{anio - 1}", hasta))
            fechas, vals = (f0 + fechas)[-95:], (v0 + vals)[-95:]
        return construir_item(s, fechas, vals, "mindicador.cl")
    return f


def _descargar_estadisticas(hasta):
    snap = mindicador_json("/api", hasta)
    out = []
    for clave, nombre, unidad, dec in CHILE_STATS:
        d = snap.get(clave)
        if isinstance(d, dict) and d.get("valor") is not None:
            out.append(construir_stat(clave, nombre, unidad, dec, float(d["valor"]), d["fecha"][:10], "mindicador.cl"))
    if not out:
        raise ValueError("la respuesta no trae indicadores")
    return out


def fuente_mindicador():
    items = []
    errores: list[str] = []
    obsoletos: list[str] = []
    with _chile_lock:
        _cargar_disco()
        hasta = time.time() + PRESUPUESTO_CHILE
        anio = date.today().year
        # Primero lo que no tiene respaldo (indicadores macro), después las series
        pedidos = [("Indicadores macro", "stats", _descargar_estadisticas)] + \
                  [(s["name"], s["id"], _descargar_serie(s, anio)) for s in CHILE_SERIES]
        for nombre, clave, descargar in pedidos:
            dato, error, momento = _chile_obtener(clave, descargar, hasta)
            if error:
                errores.append(f"{nombre}: {error}")
                if dato is not None:
                    obsoletos.append(f"{nombre} (hace {_hace(time.time() - momento)})")
            if dato is None:
                continue
            items += dato if isinstance(dato, list) else [dato]

    dolar = CHILE_SERIES[0]
    dolar_viejo = any(o.startswith(dolar["name"]) for o in obsoletos)
    if dolar_viejo or not any(i["id"] == "usdclp" for i in items):   # respaldo del dólar vía Yahoo Finance
        try:
            f, v = parse_yahoo(http_json("https://query1.finance.yahoo.com/v8/finance/chart/CLP%3DX?range=3mo&interval=1d"))
            items = [i for i in items if i["id"] != "usdclp"]
            items.insert(0, construir_item(dolar, f, v, "Yahoo Finance (respaldo)"))
            obsoletos = [o for o in obsoletos if not o.startswith(dolar["name"])]
        except Exception as e:
            errores.append(f"Respaldo del dólar: {_err(e)}")

    if obsoletos:
        errores.append("se muestran datos anteriores de: " + ", ".join(obsoletos))
    if not items:
        raise RuntimeError(" | ".join(errores) or "sin datos")
    items.sort(key=lambda i: i["kind"] != "serie")   # series primero, indicadores macro después
    estado = {"estado": "parcial" if errores else "ok", "n": len(items)}
    if errores:
        estado["error"] = " | ".join(errores)[:500]
    return items, estado


def fuente_fng():
    return parse_fng(http_json("https://api.alternative.me/fng/?limit=30")), {"estado": "ok", "n": 1}


_macro_cache = {"ts": 0.0, "data": None}


def fuente_macro():
    if _macro_cache["data"] and time.time() - _macro_cache["ts"] < TTL_MACRO:
        return _macro_cache["data"], {"estado": "ok", "n": 3}
    paises = ";".join(PAISES)
    data = {}
    for clave, (codigo, _) in MACRO.items():
        url = f"https://api.worldbank.org/v2/country/{paises}/indicator/{codigo}?format=json&mrnev=1&per_page=50"
        data[clave] = parse_worldbank(http_json(url))
    _macro_cache.update(ts=time.time(), data=data)
    return data, {"estado": "ok", "n": 3}


_ultimo_ok: dict = {}   # último resultado bueno de cada fuente (para no dejar la interfaz vacía)


def ejecutar(nombre: str, fn, fuentes: dict):
    try:
        datos, estado = fn()
    except Exception as e:
        LOG.warning("fuente %s: %s", nombre, _err(e))
        previo = _ultimo_ok.get(nombre)
        if previo is not None:
            fuentes[nombre] = {"estado": "parcial", "obsoleto": True,
                               "error": f"{_err(e)} · mostrando los últimos datos recibidos"}
            return previo
        fuentes[nombre] = {"estado": "error", "error": _err(e)}
        return None
    _ultimo_ok[nombre] = datos
    fuentes[nombre] = estado
    return datos


# --------------------------------------------------------------------------
# Snapshot + caché
# --------------------------------------------------------------------------
def construir_snapshot() -> dict:
    fuentes: dict = {}
    tareas = {"yahoo": fuente_yahoo, "frankfurter": fuente_frankfurter, "mindicador": fuente_mindicador,
              "alternativeme": fuente_fng, "bancomundial": fuente_macro}
    with ThreadPoolExecutor(5) as ex:
        futs = {k: ex.submit(ejecutar, k, fn, fuentes) for k, fn in tareas.items()}
        res = {k: f.result() for k, f in futs.items()}
    items = list(res["yahoo"] or [])
    per_usd = {"USD": 1.0}
    if res["frankfurter"]:
        fx_items, per_usd = res["frankfurter"]
        items += fx_items
    chile = res["mindicador"] or []
    items += chile
    clp = next((i["value"] for i in chile if i["id"] == "usdclp"), None)
    if clp:
        per_usd["CLP"] = clp
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuentes": fuentes, "items": items, "fx_per_usd": per_usd,
        "feargreed": res["alternativeme"], "macro": res["bancomundial"],
        "ttl": TTL_MERCADO,
    }


_cache: dict = {"ts": 0.0, "data": None}
_build = threading.Lock()      # solo una actualización a la vez


def _refrescar() -> dict:
    with _build:
        if _cache["data"] and time.time() - _cache["ts"] < TTL_MERCADO:
            return _cache["data"]            # otro hilo ya lo actualizó
        data = construir_snapshot()
        if all(f["estado"] == "error" for f in data["fuentes"].values()) and _cache["data"]:
            return {**_cache["data"], "stale": True}
        _cache.update(ts=time.time(), data=data)
        return data


def obtener_snapshot() -> dict:
    """Datos frescos si los hay; si expiraron, devuelve los anteriores al instante y
    actualiza en segundo plano (así ningún visitante espera a las APIs, salvo el primero)."""
    data = _cache["data"]
    if data and time.time() - _cache["ts"] < TTL_MERCADO:
        return data
    if data:
        if not _build.locked():
            threading.Thread(target=_refrescar, daemon=True, name="refresco").start()
        return data
    return _refrescar()


# --------------------------------------------------------------------------
# Servidor
# --------------------------------------------------------------------------
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; "
       "font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
CABECERAS_SEGURIDAD = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
COMPRIMIBLES = {"text/html", "text/css", "text/javascript", "application/json", "image/svg+xml"}


class Handler(BaseHTTPRequestHandler):
    server_version = "PulsoGlobal"
    sys_version = ""

    def version_string(self):
        return self.server_version
    protocol_version = "HTTP/1.1"
    timeout = 30                      # corta conexiones inactivas

    # -- respuesta genérica (gzip, cabeceras de seguridad, ETag, HEAD) --
    def _send(self, code: int, body: bytes, ctype: str, cache: str = "no-store",
              etag: str | None = None, head: bool = False):
        if etag and self.headers.get("If-None-Match") == etag:
            code, body = 304, b""
        codificacion = None
        if code == 200 and len(body) > 512 and ctype.split(";")[0] in COMPRIMIBLES \
                and "gzip" in self.headers.get("Accept-Encoding", ""):
            body, codificacion = gzip.compress(body, 5), "gzip"
        self.send_response(code)
        if code != 304:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("Vary", "Accept-Encoding")
        if codificacion:
            self.send_header("Content-Encoding", codificacion)
        if etag:
            self.send_header("ETag", etag)
        for k, v in CABECERAS_SEGURIDAD.items():
            self.send_header(k, v)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _json(self, code: int, obj, head: bool = False, cache: str = "no-store"):
        body = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode()
        self._send(code, body, "application/json; charset=utf-8", cache=cache, head=head)

    def _archivo(self, archivo: Path, tipo: str, head: bool):
        st = archivo.stat()
        etag = f'W/"{st.st_size:x}-{st.st_mtime_ns:x}"'
        self._send(200, archivo.read_bytes(), tipo, cache="no-cache", etag=etag, head=head)

    def _static(self, rel: str, head: bool):
        """Sirve archivos de /static sin permitir salir de esa carpeta (../)."""
        base = STATIC.resolve()
        archivo = (base / unquote(rel)).resolve()
        tipo = TIPOS.get(archivo.suffix.lower())
        if base not in archivo.parents or not archivo.is_file() or not tipo:
            return self._send(404, b"No encontrado", "text/plain; charset=utf-8", head=head)
        self._archivo(archivo, tipo, head)

    def _manejar(self, head: bool = False):
        try:
            ruta = urlparse(self.path).path
            if ruta in ("/", "/index.html"):
                self._archivo(AQUI / "index.html", "text/html; charset=utf-8", head)
            elif ruta.startswith("/static/"):
                self._static(ruta[len("/static/"):], head)
            elif ruta == "/api/snapshot":
                try:
                    datos = obtener_snapshot()
                except Exception:
                    LOG.exception("no se pudo construir el snapshot")
                    return self._json(503, {"error": "datos no disponibles por ahora"}, head)
                self._json(200, datos, head, cache="public, max-age=20")
            elif ruta in ("/api/health", "/healthz"):
                edad = round(time.time() - _cache["ts"]) if _cache["data"] else None
                self._json(200, {"ok": True, "snapshot_edad_s": edad}, head)
            else:
                self._send(404, b"No encontrado", "text/plain; charset=utf-8", head=head)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass                       # el cliente cerró la conexión
        except Exception:
            LOG.exception("error atendiendo %s", self.path)
            try:
                self._json(500, {"error": "error interno"}, head)
            except Exception:
                pass

    def do_GET(self):
        self._manejar()

    def do_HEAD(self):
        self._manejar(head=True)

    def log_message(self, fmt, *args):
        LOG.info("%s %s", self.address_string(), fmt % args)


class Servidor(ThreadingHTTPServer):
    request_queue_size = 64
    daemon_threads = True


def diagnostico() -> int:
    """Prueba cada API por separado e imprime el resultado (o el error exacto)."""
    hoy = date.today()
    pruebas = [
        ("Yahoo Finance · S&P 500", "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=5d&interval=1d"),
        ("Yahoo Finance · USD/CLP", "https://query1.finance.yahoo.com/v8/finance/chart/CLP%3DX?range=5d&interval=1d"),
        ("Frankfurter", f"https://api.frankfurter.dev/v1/{hoy - timedelta(days=7)}..{hoy}?base=USD&symbols=EUR"),
        ("mindicador.cl /api", "https://mindicador.cl/api"),
        ("mindicador.cl dólar", f"https://mindicador.cl/api/dolar/{hoy.year}"),
        ("mindicador.cl (www)", "https://www.mindicador.cl/api"),
        ("Banco Mundial", "https://api.worldbank.org/v2/country/CHL/indicator/FP.CPI.TOTL.ZG?format=json&mrnev=1"),
        ("alternative.me", "https://api.alternative.me/fng/?limit=1"),
    ]
    fallos = 0
    for nombre, url in pruebas:
        t0 = time.time()
        try:
            datos = http_json(url, timeout=15, reintentos=0)
            resumen = ", ".join(list(datos)[:4]) if isinstance(datos, dict) else f"lista de {len(datos)}"
            print(f"  OK     {nombre:<26} {time.time() - t0:4.1f}s  ({resumen})")
        except Exception as e:
            fallos += 1
            print(f"  FALLA  {nombre:<26} {time.time() - t0:4.1f}s  {_err(e)}")
    print(f"\n{len(pruebas) - fallos}/{len(pruebas)} fuentes responden.")
    return 1 if fallos else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"),
                    help="interfaz de escucha (0.0.0.0 para aceptar conexiones externas)")
    ap.add_argument("--puerto", type=int, default=int(os.environ.get("PORT", "8765")))
    ap.add_argument("--log", default=os.environ.get("LOG_LEVEL", "INFO"), help="DEBUG, INFO, WARNING...")
    ap.add_argument("--json", action="store_true", help="imprime un snapshot JSON y termina")
    ap.add_argument("--diagnostico", action="store_true", help="prueba cada API por separado y muestra el error exacto")
    args = ap.parse_args()

    logging.basicConfig(level=args.log.upper(), format="%(asctime)s %(levelname)s %(message)s")
    if args.diagnostico:
        raise SystemExit(diagnostico())
    if args.json:
        print(json.dumps(obtener_snapshot(), ensure_ascii=False, indent=2))
        return

    srv = Servidor((args.host, args.puerto), Handler)
    LOG.info("Pulso Global escuchando en http://%s:%d", args.host, args.puerto)
    threading.Thread(target=_refrescar, daemon=True, name="precarga").start()   # primer snapshot sin esperar visitas
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        LOG.info("cerrando servidor")
        srv.server_close()


if __name__ == "__main__":
    main()