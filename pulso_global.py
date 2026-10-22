#!/usr/bin/env python3
"""
Pulso Global - terminal de indicadores económicos mundiales.

Backend (solo librería estándar) que agrega APIs públicas y gratuitas, calcula
métricas y alertas, y sirve la interfaz web (index.html) en http://localhost:8765

Fuentes (sin API key):
  Yahoo Finance (chart)  índices, materias primas, VIX, bono 10Y, DXY, cripto
  Frankfurter (BCE)      divisas
  mindicador.cl          Chile: dólar, UF, UTM, TPM, IPC, cobre, desempleo, IMACEC
  Banco Mundial          inflación, crecimiento del PIB y desempleo por país
  alternative.me         índice Fear & Greed (sentimiento cripto)

Uso:
  python pulso_global.py                 # datos reales + abre el navegador
  python pulso_global.py --simulado      # datos sintéticos (sin internet)
  python pulso_global.py --json          # imprime un snapshot y termina
  python pulso_global.py --diagnostico   # prueba cada API y muestra el error exacto
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import threading
import time
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

AQUI = Path(__file__).resolve().parent
STATIC = AQUI / "static"
TIPOS = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
         ".woff2": "font/woff2"}
UA = {"User-Agent": "Mozilla/5.0 (compatible; PulsoGlobal/1.0)", "Accept": "application/json"}
TTL_MERCADO = 60          # segundos que se reutiliza un snapshot
TTL_MACRO = 6 * 3600      # el Banco Mundial cambia una vez al año
UMBRAL_Z = 2.0
UMBRAL_VAR = {"indices": 2.0, "commodities": 3.0, "riesgo": 8.0, "cripto": 6.0, "fx": 1.0, "chile": 1.5}
UMBRAL_PB = 10.0          # puntos base para tasas (bono 10Y)


# --------------------------------------------------------------------------
# Catálogo de instrumentos (base/vol/shock solo se usan en modo simulado)
# --------------------------------------------------------------------------
def spec(id, sym, name, group, unit, dec, base, vol, **extra):
    return dict(id=id, sym=sym, name=name, group=group, unit=unit, dec=dec, base=base, vol=vol, **extra)


YAHOO = [
    spec("spx", "^GSPC", "S&P 500", "indices", "pts", 2, 6700, .0075),
    spec("ndx", "^IXIC", "Nasdaq Composite", "indices", "pts", 2, 22800, .010),
    spec("dji", "^DJI", "Dow Jones", "indices", "pts", 2, 46500, .007),
    spec("sx5e", "^STOXX50E", "Euro Stoxx 50", "indices", "pts", 2, 5600, .008),
    spec("ftse", "^FTSE", "FTSE 100", "indices", "pts", 2, 9500, .006),
    spec("n225", "^N225", "Nikkei 225", "indices", "pts", 2, 48000, .011),
    spec("hsi", "^HSI", "Hang Seng", "indices", "pts", 2, 26000, .011),
    spec("bvsp", "^BVSP", "Bovespa", "indices", "pts", 0, 145000, .008),
    spec("ipsa", "^IPSA", "IPSA (Chile)", "indices", "pts", 2, 9500, .007),
    spec("vix", "^VIX", "VIX · volatilidad", "riesgo", "pts", 2, 16, .045, shock=.12),
    spec("tnx", "^TNX", "Bono EE.UU. 10 años", "riesgo", "%", 3, 4.1, .010, rate=True),
    spec("dxy", "DX-Y.NYB", "Índice dólar (DXY)", "riesgo", "pts", 2, 99, .003),
    spec("gold", "GC=F", "Oro", "commodities", "USD/oz", 2, 4100, .009, drift=.0016),
    spec("silver", "SI=F", "Plata", "commodities", "USD/oz", 2, 48, .016),
    spec("wti", "CL=F", "Petróleo WTI", "commodities", "USD/bbl", 2, 62, .018, shock=.042),
    spec("brent", "BZ=F", "Petróleo Brent", "commodities", "USD/bbl", 2, 66, .017),
    spec("copper", "HG=F", "Cobre", "commodities", "USD/lb", 3, 5.0, .011),
    spec("gas", "NG=F", "Gas natural", "commodities", "USD/MMBtu", 3, 3.2, .028),
    spec("btc", "BTC-USD", "Bitcoin", "cripto", "USD", 2, 98000, .022, shock=-.065),
    spec("eth", "ETH-USD", "Ethereum", "cripto", "USD", 2, 3500, .028),
    spec("sol", "SOL-USD", "Solana", "cripto", "USD", 2, 170, .038),
]

FX = [
    spec("eurusd", "EUR/USD", "Euro / Dólar", "fx", "USD", 4, 1.16, .0035, ccy="EUR", inv=True),
    spec("gbpusd", "GBP/USD", "Libra / Dólar", "fx", "USD", 4, 1.33, .0040, ccy="GBP", inv=True),
    spec("usdjpy", "USD/JPY", "Dólar / Yen", "fx", "JPY", 2, 150, .0050, ccy="JPY"),
    spec("usdcny", "USD/CNY", "Dólar / Yuan", "fx", "CNY", 4, 7.1, .0012, ccy="CNY"),
    spec("usdbrl", "USD/BRL", "Dólar / Real", "fx", "BRL", 4, 5.4, .0060, ccy="BRL"),
    spec("usdmxn", "USD/MXN", "Dólar / Peso mexicano", "fx", "MXN", 4, 18.5, .0060, ccy="MXN"),
    spec("usdchf", "USD/CHF", "Dólar / Franco suizo", "fx", "CHF", 4, .80, .0040, ccy="CHF"),
]

CHILE_SERIES = [
    spec("usdclp", "USD/CLP", "Dólar observado", "chile", "CLP", 2, 950, .005, codigo="dolar", shock=.016),
    spec("uf", "UF", "Unidad de Fomento", "chile", "CLP", 2, 40700, .00002, codigo="uf", drift=.00009, sinextremos=True),
    spec("cobre", "Cu", "Cobre (Cochilco)", "chile", "USD/lb", 3, 5.0, .008, codigo="libra_cobre"),
]
# (clave en mindicador, nombre, unidad, decimales, valor simulado)
CHILE_STATS = [
    ("tpm", "Tasa de política monetaria", "%", 2, 4.50),
    ("ipc", "IPC · variación mensual", "%", 2, 0.30),
    ("tasa_desempleo", "Desempleo", "%", 1, 8.7),
    ("imacec", "IMACEC · variación anual", "%", 1, 2.4),
    ("utm", "UTM", "CLP", 0, 69500),
]

PAISES = {"USA": "EE.UU.", "CHN": "China", "DEU": "Alemania", "JPN": "Japón", "GBR": "Reino Unido",
          "IND": "India", "BRA": "Brasil", "MEX": "México", "CHL": "Chile", "ESP": "España"}
MACRO = {"inflacion": ("FP.CPI.TOTL.ZG", "Inflación anual"),
         "pib": ("NY.GDP.MKTP.KD.ZG", "Crecimiento del PIB"),
         "desempleo": ("SL.UEM.TOTL.ZS", "Desempleo")}
MACRO_SIM = {
    "inflacion": {"USA": 2.9, "CHN": 0.2, "DEU": 2.5, "JPN": 2.7, "GBR": 2.5, "IND": 4.9, "BRA": 4.4, "MEX": 4.7, "CHL": 3.9, "ESP": 2.9},
    "pib": {"USA": 2.8, "CHN": 5.0, "DEU": -0.2, "JPN": 0.1, "GBR": 1.1, "IND": 6.5, "BRA": 3.4, "MEX": 1.2, "CHL": 2.6, "ESP": 3.2},
    "desempleo": {"USA": 4.0, "CHN": 5.0, "DEU": 3.4, "JPN": 2.6, "GBR": 4.3, "IND": 4.2, "BRA": 7.0, "MEX": 2.7, "CHL": 8.5, "ESP": 11.4},
}


# --------------------------------------------------------------------------
# Utilidades HTTP y métricas
# --------------------------------------------------------------------------
def http_json(url: str, timeout: int = 12, reintentos: int = 1):
    ultimo: Exception | None = None
    for _ in range(reintentos + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:  # red, HTTP o JSON inválido
            ultimo = e
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
# Modo simulado
# --------------------------------------------------------------------------
def fechas_habiles(n: int, todos: bool = False) -> list[str]:
    out, d = [], date.today()
    while len(out) < n:
        if todos or d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out[::-1]


def sim_serie(s: dict, n: int = 65, todos: bool = False):
    rng = random.Random(s["id"])
    v, vals = s["base"], []
    for _ in range(n):
        v *= 1 + s.get("drift", 0.0) + rng.gauss(0, s["vol"])
        vals.append(v)
    vals[-1] *= 1 + s.get("shock", 0.0)
    return fechas_habiles(n, todos), vals


def sim_item(s: dict) -> dict:
    fechas, vals = sim_serie(s, 90 if s["group"] == "cripto" else 65, s["group"] == "cripto")
    return construir_item(s, fechas, vals, "Simulado")


# --------------------------------------------------------------------------
# Fuentes: cada una devuelve (datos, estado)
# --------------------------------------------------------------------------
def fuente_yahoo(sim: bool):
    def uno(s):
        try:
            if sim:
                return sim_item(s)
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


def fuente_frankfurter(sim: bool):
    items, per_usd = [], {"USD": 1.0}
    if sim:
        for s in FX:
            fechas, vals = sim_serie(s)
            items.append(construir_item(s, fechas, vals, "Simulado"))
            per_usd[s["ccy"]] = 1 / vals[-1] if s.get("inv") else vals[-1]
        return (items, per_usd), {"estado": "ok", "n": len(items)}
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


def mindicador_json(ruta: str):
    """mindicador.cl a veces es lento o rechaza peticiones: prueba ambos hosts."""
    ultimo: Exception | None = None
    for host in MINDICADOR_HOSTS:
        try:
            return http_json(host + ruta, timeout=15, reintentos=0)
        except Exception as e:
            ultimo = e
    raise ultimo or RuntimeError("no se realizó ningún intento")


def _err(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"[:140]


def fuente_mindicador(sim: bool):
    items = []
    if sim:
        for s in CHILE_SERIES:
            fechas, vals = sim_serie(s)
            items.append(construir_item(s, fechas, vals, "Simulado"))
        hoy = date.today().isoformat()
        for clave, nombre, unidad, dec, v in CHILE_STATS:
            items.append(construir_stat(clave, nombre, unidad, dec, v, hoy, "Simulado"))
        return items, {"estado": "ok", "n": len(items)}
    anio = date.today().year

    def serie(s):
        try:
            fechas, vals = parse_mindicador_serie(mindicador_json(f"/api/{s['codigo']}/{anio}"))
            if len(vals) < 45:   # inicio de año: completar con el anterior
                f0, v0 = parse_mindicador_serie(mindicador_json(f"/api/{s['codigo']}/{anio - 1}"))
                fechas, vals = (f0 + fechas)[-95:], (v0 + vals)[-95:]
            return construir_item(s, fechas, vals, "mindicador.cl")
        except Exception as e:
            return e

    def estadisticas():
        try:
            snap = mindicador_json("/api")
            out = []
            for clave, nombre, unidad, dec, _ in CHILE_STATS:
                d = snap.get(clave)
                if d and d.get("valor") is not None:
                    out.append(construir_stat(clave, nombre, unidad, dec, float(d["valor"]), d["fecha"][:10], "mindicador.cl"))
            return out
        except Exception as e:
            return e

    with ThreadPoolExecutor(4) as ex:
        futs = [ex.submit(serie, s) for s in CHILE_SERIES]
        fut_st = ex.submit(estadisticas)
        res, stats = [f.result() for f in futs], fut_st.result()

    errores = []
    for s, r in zip(CHILE_SERIES, res):
        if isinstance(r, dict):
            items.append(r)
        else:
            errores.append(f"{s['name']}: {_err(r)}")
    if isinstance(stats, list):
        items += stats
    else:
        errores.append(f"Indicadores macro: {_err(stats)}")

    if not any(i["id"] == "usdclp" for i in items):   # respaldo del dólar vía Yahoo Finance
        try:
            f, v = parse_yahoo(http_json("https://query1.finance.yahoo.com/v8/finance/chart/CLP%3DX?range=3mo&interval=1d"))
            items.insert(0, construir_item(CHILE_SERIES[0], f, v, "Yahoo Finance (respaldo)"))
        except Exception as e:
            errores.append(f"Respaldo del dólar: {_err(e)}")

    if errores:   # completar con los últimos datos buenos lo que no llegó ahora
        presentes = {i["id"] for i in items}
        previos = [i for i in (_ultimo_ok.get(("mindicador", False)) or []) if i["id"] not in presentes]
        items += previos
        if previos:
            errores.append("se muestran datos anteriores de: " + ", ".join(i["name"] for i in previos))
    if not items:
        raise RuntimeError(" | ".join(errores) or "sin datos")
    estado = {"estado": "parcial" if errores else "ok", "n": len(items)}
    if errores:
        estado["error"] = " | ".join(errores)[:400]
    return items, estado


def fuente_fng(sim: bool):
    if sim:
        rng, v, hist = random.Random("fng"), 55.0, []
        for _ in range(30):
            v = min(95, max(5, v + rng.gauss(0, 4)))
            hist.append(int(v))
        return {"value": 72, "label": "Greed", "history": hist[:-1] + [72],
                "dates": fechas_habiles(30, True)}, {"estado": "ok", "n": 1}
    return parse_fng(http_json("https://api.alternative.me/fng/?limit=30")), {"estado": "ok", "n": 1}


_macro_cache = {"ts": 0.0, "data": None}


def fuente_macro(sim: bool):
    if sim:
        return {k: sorted([{"iso": i, "pais": PAISES[i], "valor": v, "anio": 2024} for i, v in d.items()],
                          key=lambda x: -x["valor"]) for k, d in MACRO_SIM.items()}, {"estado": "ok", "n": 3}
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


def ejecutar(nombre: str, fn, sim: bool, fuentes: dict):
    try:
        datos, estado = fn(sim)
    except Exception as e:
        previo = _ultimo_ok.get((nombre, sim))
        if previo is not None:
            fuentes[nombre] = {"estado": "parcial", "obsoleto": True,
                               "error": f"{_err(e)} · mostrando los últimos datos recibidos"}
            return previo
        fuentes[nombre] = {"estado": "error", "error": _err(e)}
        return None
    _ultimo_ok[(nombre, sim)] = datos
    fuentes[nombre] = estado
    return datos


# --------------------------------------------------------------------------
# Snapshot + caché
# --------------------------------------------------------------------------
def construir_snapshot(sim: bool = False) -> dict:
    fuentes: dict = {}
    tareas = {"yahoo": fuente_yahoo, "frankfurter": fuente_frankfurter, "mindicador": fuente_mindicador,
              "alternativeme": fuente_fng, "bancomundial": fuente_macro}
    with ThreadPoolExecutor(5) as ex:
        futs = {k: ex.submit(ejecutar, k, fn, sim, fuentes) for k, fn in tareas.items()}
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
        "mode": "simulado" if sim else "live",
        "fuentes": fuentes, "items": items, "fx_per_usd": per_usd,
        "feargreed": res["alternativeme"], "macro": res["bancomundial"],
        "ttl": TTL_MERCADO,
    }


_cache = {"ts": 0.0, "data": None, "sim": None}
_lock = threading.Lock()


def obtener_snapshot(sim: bool = False) -> dict:
    with _lock:
        ahora = time.time()
        if _cache["data"] and _cache["sim"] == sim and ahora - _cache["ts"] < TTL_MERCADO:
            return _cache["data"]
        data = construir_snapshot(sim)
        if all(f["estado"] == "error" for f in data["fuentes"].values()) and _cache["data"]:
            return {**_cache["data"], "stale": True}
        _cache.update(ts=ahora, data=data, sim=sim)
        return data


# --------------------------------------------------------------------------
# Servidor
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    simulado = False

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, rel: str):
        """Sirve archivos de /static sin permitir salir de esa carpeta (../)."""
        base = STATIC.resolve()
        archivo = (base / unquote(rel)).resolve()
        tipo = TIPOS.get(archivo.suffix.lower())
        if base not in archivo.parents or not archivo.is_file() or not tipo:
            return self._send(404, b"No encontrado", "text/plain; charset=utf-8")
        self._send(200, archivo.read_bytes(), tipo)

    def do_GET(self):
        ruta = urlparse(self.path).path
        if ruta in ("/", "/index.html"):
            self._send(200, (AQUI / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif ruta.startswith("/static/"):
            self._static(ruta[len("/static/"):])
        elif ruta == "/api/snapshot":
            body = json.dumps(obtener_snapshot(self.simulado), ensure_ascii=False, allow_nan=False).encode()
            self._send(200, body, "application/json; charset=utf-8")
        elif ruta == "/api/health":
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._send(404, b"No encontrado", "text/plain; charset=utf-8")

    def log_message(self, *args):
        pass


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
    ap.add_argument("--diagnostico", action="store_true", help="prueba cada API por separado y muestra el error exacto")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--simulado", action="store_true", help="datos sintéticos (demo sin internet)")
    ap.add_argument("--json", action="store_true", help="imprime un snapshot JSON y termina")
    ap.add_argument("--sin-navegador", action="store_true")
    args = ap.parse_args()

    if args.diagnostico:
        raise SystemExit(diagnostico())
    if args.json:
        print(json.dumps(obtener_snapshot(args.simulado), ensure_ascii=False, indent=2))
        return
        Handler.simulado = args.simulado
    puerto = int(os.environ.get("PORT", args.puerto))
    srv = ThreadingHTTPServer(("0.0.0.0", puerto), Handler)
    url = f"http://localhost:{puerto}"
    print(f"Pulso Global en {url}  ({'SIMULADO' if args.simulado else 'datos reales'})  ·  Ctrl+C para salir")
    print("Tip para grabar: abre", url + "/?tour=1&clean=1")
    if not args.sin_navegador:
        threading.Timer(0.8, webbrowser.open, args=[url]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nHasta luego")


if __name__ == "__main__":
    main()