"""Tests de Pulso Global. No requieren internet: los parsers se prueban con
respuestas de ejemplo y el flujo completo se prueba con un http_json de prueba."""
import contextlib
import gzip
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

import pytest

import pulso_global as pg


@pytest.fixture(autouse=True)
def _limpiar_estado(monkeypatch, tmp_path):
    pg._ultimo_ok.clear()
    pg._macro_cache.update(ts=0.0, data=None)
    pg._cache.update(ts=0.0, data=None)
    monkeypatch.setattr(pg, "CACHE_CHILE", tmp_path / "cache" / "chile.json")   # no tocar el disco real
    monkeypatch.setattr(pg, "ESPERA_REINTENTO", 0)
    monkeypatch.setattr(pg, "PAUSA_CHILE", 0)
    pg.reiniciar_chile()
    yield


def envejecer_cache_chile(segundos):
    """Simula que pasó el tiempo desde la última descarga de Chile."""
    for k, (ts, dato) in list(pg._chile["datos"].items()):
        pg._chile["datos"][k] = (ts - segundos, dato)
    pg._chile["fallos"].clear()


# ---------- Respuestas de ejemplo con el formato de cada API ----------
def yahoo_payload(n=70, ultimo=None, mtime_offset=0):
    hoy = int(__import__("time").time())
    ts = [hoy - (n - 1 - i) * 86400 for i in range(n)]
    cierres = [100 + i * 0.1 for i in range(n)]
    cierres[5] = None  # Yahoo a veces entrega huecos
    return {"chart": {"result": [{"meta": {"regularMarketPrice": ultimo or cierres[-1],
                                           "regularMarketTime": ts[-1] + mtime_offset},
                                  "timestamp": ts, "indicators": {"quote": [{"close": cierres}]}}], "error": None}}


def frankfurter_payload():
    hoy = date.today()
    dias = [(hoy - timedelta(days=90 - i)).isoformat() for i in range(0, 91)]
    return {"base": "USD", "rates": {d: {"EUR": 0.86, "GBP": 0.75, "JPY": 150.0, "CNY": 7.1,
                                         "BRL": 5.4, "MXN": 18.5, "CHF": 0.8} for d in dias}}


def mindicador_serie(n=100, futuro=True):
    hoy = date.today()
    serie = [{"fecha": f"{(hoy - timedelta(days=i)).isoformat()}T03:00:00.000Z", "valor": 950 + i * 0.1} for i in range(n)]
    if futuro:
        serie.append({"fecha": f"{(hoy + timedelta(days=5)).isoformat()}T03:00:00.000Z", "valor": 99999})
    return {"serie": serie}


def worldbank_payload():
    return [{"page": 1}, [
        {"countryiso3code": "CHL", "country": {"value": "Chile"}, "date": "2024", "value": 3.9},
        {"countryiso3code": "USA", "country": {"value": "United States"}, "date": "2024", "value": 2.9},
        {"countryiso3code": "ARG", "country": {"value": "Argentina"}, "date": "2024", "value": None}]]


def fng_payload():
    return {"data": [{"value": str(60 - i), "value_classification": "Greed", "timestamp": str(1_760_000_000 - i * 86400)} for i in range(30)]}


# ---------- Parsers ----------
def test_parse_yahoo_ignora_huecos_y_usa_precio_en_vivo():
    fechas, vals = pg.parse_yahoo(yahoo_payload(ultimo=123.45))
    assert len(fechas) == len(vals) == 69          # se descartó el None
    assert vals[-1] == 123.45                       # la última vela usa el precio en vivo
    assert fechas == sorted(fechas)


def test_parse_yahoo_agrega_punto_si_la_ultima_vela_es_antigua():
    f, v = pg.parse_yahoo(yahoo_payload(ultimo=200.0, mtime_offset=3 * 86400))
    assert v[-1] == 200.0 and len(v) == 70


def test_parse_frankfurter_agrupa_por_moneda():
    por = pg.parse_frankfurter(frankfurter_payload())
    assert set(por) == {"EUR", "GBP", "JPY", "CNY", "BRL", "MXN", "CHF"}
    assert por["JPY"][1][-1] == 150.0


def test_parse_mindicador_descarta_fechas_futuras():
    fechas, vals = pg.parse_mindicador_serie(mindicador_serie())
    assert max(vals) < 99999 and fechas == sorted(fechas) and fechas[-1] <= date.today().isoformat()


def test_parse_worldbank_omite_nulos_y_traduce_paises():
    r = pg.parse_worldbank(worldbank_payload())
    assert [x["pais"] for x in r] == ["Chile", "EE.UU."] and r[0]["valor"] == 3.9


def test_parse_fng_ordena_cronologicamente():
    r = pg.parse_fng(fng_payload())
    assert r["value"] == 60 and len(r["history"]) == 30 and r["history"][0] == 31


# ---------- Métricas y alertas ----------
def test_zscore_detecta_salto_y_serie_plana():
    base = [100 + (i % 2) * 0.1 for i in range(40)]
    assert abs(pg.zscore(base + [110])) > pg.UMBRAL_Z
    assert pg.zscore([100.0] * 40) == 0.0


def test_alerta_de_variacion_y_extremos():
    s = dict(id="x", sym="X", name="X", group="indices", unit="pts", dec=2)
    vals = [100.0 + i * 0.01 for i in range(60)] + [105.0]
    fechas = [(date.today() - timedelta(days=60 - i)).isoformat() for i in range(61)]
    it = pg.construir_item(s, fechas, vals, "test")
    tipos = {a["tipo"] for a in it["alerts"]}
    assert {"variacion", "atipico", "maximo"} <= tipos


def test_tasas_se_miden_en_puntos_base():
    s = dict(id="t", sym="T", name="T", group="riesgo", unit="%", dec=3, rate=True)
    vals = [4.0] * 60 + [4.15]
    fechas = [(date.today() - timedelta(days=60 - i)).isoformat() for i in range(61)]
    it = pg.construir_item(s, fechas, vals, "test")
    assert it["chg1u"] == "pb" and round(it["chg1"]) == 15
    assert any(a["tipo"] == "variacion" and a["unidad"] == "pb" for a in it["alerts"])


# ---------- Flujo completo con http_json de prueba ----------
def falso_http(url, timeout=12, reintentos=1):
    if "yahoo.com" in url:
        if "SOL-USD" in url:
            raise OSError("429 Too Many Requests")
        return yahoo_payload()
    if "frankfurter" in url:
        return frankfurter_payload()
    if "mindicador.cl/api/" in url:
        return mindicador_serie()
    if url.rstrip("/").endswith("mindicador.cl/api"):
        return {c: {"valor": 1.5, "fecha": "2026-10-01T03:00:00.000Z"} for c, *_ in pg.CHILE_STATS}
    if "worldbank" in url:
        return worldbank_payload()
    if "alternative.me" in url:
        return fng_payload()
    raise AssertionError("URL inesperada: " + url)


def http_todo_ok(url, **kw):
    return falso_http(url.replace("SOL-USD", "BTC-USD"))


def test_snapshot_completo_y_json_valido(monkeypatch):
    monkeypatch.setattr(pg, "http_json", http_todo_ok)
    s = pg.construir_snapshot()
    assert all(f["estado"] == "ok" for f in s["fuentes"].values())
    assert len(s["items"]) == len(pg.YAHOO) + len(pg.FX) + len(pg.CHILE_SERIES) + len(pg.CHILE_STATS)
    assert s["fx_per_usd"]["CLP"] > 0 and s["feargreed"]["value"] and set(s["macro"]) == {"inflacion", "pib", "desempleo"}
    assert "mode" not in s                       # ya no existe el modo simulado
    json.dumps(s, allow_nan=False)               # sin NaN/inf: el navegador podrá parsearlo


def test_snapshot_en_vivo_tolera_fallos_parciales(monkeypatch):
    monkeypatch.setattr(pg, "http_json", falso_http)
    pg._macro_cache.update(ts=0.0, data=None)
    s = pg.construir_snapshot()
    assert s["fuentes"]["yahoo"]["estado"] == "parcial" and "Solana" in s["fuentes"]["yahoo"]["fallidos"]
    assert all(s["fuentes"][k]["estado"] == "ok" for k in ("frankfurter", "mindicador", "alternativeme", "bancomundial"))
    assert not any(i["id"] == "sol" for i in s["items"])
    assert s["fx_per_usd"]["EUR"] == 0.86 and "CLP" in s["fx_per_usd"]
    eur = next(i for i in s["items"] if i["id"] == "eurusd")
    assert abs(eur["value"] - 1 / 0.86) < 1e-4       # EUR/USD está invertido respecto a la API


def test_una_fuente_caida_no_tumba_el_resto(monkeypatch):
    def http(url, **kw):
        if "frankfurter" in url:
            raise OSError("sin red")
        return falso_http(url)
    monkeypatch.setattr(pg, "http_json", http)
    s = pg.construir_snapshot()
    assert s["fuentes"]["frankfurter"]["estado"] == "error" and "sin red" in s["fuentes"]["frankfurter"]["error"]
    assert s["fuentes"]["yahoo"]["estado"] in ("ok", "parcial") and s["items"]


# ---------- Resistencia de la fuente de Chile ----------
def test_mindicador_usa_host_alternativo(monkeypatch):
    def http(url, **kw):
        if url.startswith("https://mindicador.cl"):
            raise OSError("timed out")
        return falso_http(url)
    monkeypatch.setattr(pg, "http_json", http)
    items, estado = pg.fuente_mindicador()
    assert estado["estado"] == "ok" and {"usdclp", "uf", "cobre", "tpm"} <= {i["id"] for i in items}


def test_chile_parcial_si_falla_una_serie(monkeypatch):
    def http(url, **kw):
        if "libra_cobre" in url:
            raise OSError("500 Internal Server Error")
        return falso_http(url)
    monkeypatch.setattr(pg, "http_json", http)
    items, estado = pg.fuente_mindicador()
    ids = {i["id"] for i in items}
    assert {"usdclp", "uf", "tpm", "utm"} <= ids and "cobre" not in ids
    assert estado["estado"] == "parcial" and "Cobre" in estado["error"] and "500" in estado["error"]


def test_dolar_de_respaldo_via_yahoo_si_cae_mindicador(monkeypatch):
    def http(url, **kw):
        if "mindicador" in url:
            raise OSError("CERTIFICATE_VERIFY_FAILED")
        return falso_http(url)
    monkeypatch.setattr(pg, "http_json", http)
    items, estado = pg.fuente_mindicador()
    assert [i["id"] for i in items] == ["usdclp"] and items[0]["source"] == "Yahoo Finance (respaldo)"
    assert estado["estado"] == "parcial" and "CERTIFICATE_VERIFY_FAILED" in estado["error"]


def test_sin_ninguna_respuesta_el_error_es_legible(monkeypatch):
    monkeypatch.setattr(pg, "http_json", lambda url, **kw: (_ for _ in ()).throw(OSError("sin red")))
    s = pg.construir_snapshot()
    assert s["fuentes"]["mindicador"]["estado"] == "error" and "sin red" in s["fuentes"]["mindicador"]["error"]


def test_se_conservan_los_ultimos_datos_si_la_fuente_cae(monkeypatch):
    monkeypatch.setattr(pg, "http_json", falso_http)
    ok = pg.construir_snapshot()
    assert any(i["id"] == "uf" for i in ok["items"])

    def caido(url, **kw):
        if "mindicador" in url:
            raise OSError("sin red")
        return falso_http(url)
    monkeypatch.setattr(pg, "http_json", caido)
    envejecer_cache_chile(pg.TTL_CHILE + 1)
    s = pg.construir_snapshot()
    f = s["fuentes"]["mindicador"]
    assert f["estado"] == "parcial" and "datos anteriores" in f["error"]
    assert {"uf", "tpm", "utm"} <= {i["id"] for i in s["items"]}      # se conservan
    assert next(i for i in s["items"] if i["id"] == "usdclp")["source"] == "Yahoo Finance (respaldo)"


def llamadas_a_mindicador(monkeypatch, fallar=False):
    contador = []

    def http(url, **kw):
        if "mindicador" in url:
            contador.append(url)
            if fallar:
                raise OSError("RemoteDisconnected: Remote end closed connection without response")
        return falso_http(url)
    monkeypatch.setattr(pg, "http_json", http)
    return contador


def test_chile_usa_cache_y_no_vuelve_a_pedir_cada_minuto(monkeypatch):
    llamadas = llamadas_a_mindicador(monkeypatch)
    pg.fuente_mindicador()
    primera = len(llamadas)
    assert primera == 4                                  # 1 snapshot + 3 series, sin paralelismo extra
    items, estado = pg.fuente_mindicador()          # dentro del TTL: cero peticiones nuevas
    assert len(llamadas) == primera and estado["estado"] == "ok" and len(items) == 8
    envejecer_cache_chile(pg.TTL_CHILE + 1)
    pg.fuente_mindicador()
    assert len(llamadas) == primera * 2                  # vencido el TTL se vuelve a pedir


def test_tras_un_fallo_no_se_martilla_al_servidor(monkeypatch):
    llamadas = llamadas_a_mindicador(monkeypatch, fallar=True)
    pg.fuente_mindicador()
    n = len(llamadas)
    assert n > 0
    _, estado = pg.fuente_mindicador()              # fallo reciente: espera antes de reintentar
    assert len(llamadas) == n and "RemoteDisconnected" in estado["error"]
    pg._chile["fallos"].clear()                          # pasada la espera, reintenta
    pg.fuente_mindicador()
    assert len(llamadas) > n


def test_presupuesto_de_tiempo_corta_los_reintentos(monkeypatch):
    monkeypatch.setattr(pg, "PRESUPUESTO_CHILE", -1)     # presupuesto ya agotado
    llamadas = llamadas_a_mindicador(monkeypatch)
    _, estado = pg.fuente_mindicador()
    assert llamadas == [] and "tiempo máximo" in estado["error"]


def test_cache_en_disco_sirve_tras_reiniciar(monkeypatch):
    llamadas_a_mindicador(monkeypatch)
    pg.fuente_mindicador()
    assert pg.CACHE_CHILE.exists()
    pg.reiniciar_chile()                                 # como arrancar de nuevo el programa
    llamadas = llamadas_a_mindicador(monkeypatch, fallar=True)
    envejecer_cache_chile(0)
    items, estado = pg.fuente_mindicador()          # datos recientes del disco: sin red
    assert llamadas == [] and estado["estado"] == "ok" and {"uf", "tpm"} <= {i["id"] for i in items}


def test_cache_en_disco_vencida_se_muestra_como_datos_anteriores(monkeypatch):
    llamadas_a_mindicador(monkeypatch)
    pg.fuente_mindicador()
    pg.reiniciar_chile()
    llamadas_a_mindicador(monkeypatch, fallar=True)
    pg._cargar_disco()
    envejecer_cache_chile(pg.TTL_CHILE + 3600)           # ~1 h de antigüedad
    items, estado = pg.fuente_mindicador()
    assert estado["estado"] == "parcial" and "datos anteriores" in estado["error"] and "hace" in estado["error"]
    assert {"uf", "tpm", "cobre"} <= {i["id"] for i in items}


def test_cache_en_disco_muy_vieja_se_ignora(monkeypatch):
    llamadas_a_mindicador(monkeypatch)
    pg.fuente_mindicador()
    pg.reiniciar_chile()
    crudo = json.loads(pg.CACHE_CHILE.read_text(encoding="utf-8"))
    for v in crudo.values():
        v[0] -= pg.EDAD_MAX_DISCO + 10
    pg.CACHE_CHILE.write_text(json.dumps(crudo), encoding="utf-8")
    pg._cargar_disco()
    assert pg._chile["datos"] == {}


# ---------- Servidor ----------
@contextlib.contextmanager
def servidor(monkeypatch, http=http_todo_ok):
    monkeypatch.setattr(pg, "http_json", http)
    srv = pg.Servidor(("127.0.0.1", 0), pg.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def pedir(base, ruta, metodo="GET", cabeceras=None):
    req = urllib.request.Request(base + ruta, method=metodo, headers=cabeceras or {})
    try:
        r = urllib.request.urlopen(req)
        return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def test_servidor_entrega_interfaz_y_api(monkeypatch):
    with servidor(monkeypatch) as base:
        estado, _, cuerpo = pedir(base, "/")
        assert estado == 200 and b"Pulso Global" in cuerpo
        estado, h, cuerpo = pedir(base, "/api/snapshot")
        data = json.loads(cuerpo)
        assert estado == 200 and data["items"] and "mode" not in data
        assert "max-age" in h["Cache-Control"]
        assert pedir(base, "/nada")[0] == 404


def test_html_sin_estilos_ni_scripts_en_linea_ni_modo_demo():
    html = (pg.AQUI / "index.html").read_text(encoding="utf-8")
    assert "<style" not in html and 'style="' not in html            # CSP estricta: nada en línea
    assert "/static/css/styles.css" in html and "/static/js/app.js" in html
    assert "<script>" not in html                                      # solo scripts externos
    for archivo in ("index.html", "static/js/app.js", "static/css/styles.css", "pulso_global.py"):
        texto = (pg.AQUI / archivo).read_text(encoding="utf-8").lower()
        for prohibido in ("tour", "simulado", "modo demo", "clean=1"):
            assert prohibido not in texto, f"{prohibido!r} sigue en {archivo}"


def test_estaticos_se_sirven_y_no_se_puede_salir_de_static(monkeypatch):
    with servidor(monkeypatch) as base:
        estado, h, cuerpo = pedir(base, "/static/css/styles.css")
        assert estado == 200 and h["Content-Type"].startswith("text/css") and b"--side" in cuerpo
        estado, h, _ = pedir(base, "/static/js/app.js")
        assert estado == 200 and h["Content-Type"].startswith("text/javascript")
        assert pedir(base, "/static/img/favicon.svg")[0] == 200
        for malo in ("/static/../pulso_global.py", "/static/%2e%2e/pulso_global.py", "/static/css",
                     "/static/css/no-existe.css", "/static/..%2fREADME.md", "/static/%2e%2e%2fcache/chile.json"):
            assert pedir(base, malo)[0] == 404, malo


def test_cabeceras_de_seguridad(monkeypatch):
    with servidor(monkeypatch) as base:
        for ruta in ("/", "/static/css/styles.css", "/api/snapshot", "/nada"):
            _, h, _ = pedir(base, ruta)
            assert "script-src 'self'" in h["Content-Security-Policy"] and "frame-ancestors 'none'" in h["Content-Security-Policy"]
            assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
            assert "Server" not in h or "Python" not in h["Server"]


def test_gzip_etag_y_head(monkeypatch):
    with servidor(monkeypatch) as base:
        _, h, cuerpo = pedir(base, "/static/js/app.js", cabeceras={"Accept-Encoding": "gzip"})
        assert h["Content-Encoding"] == "gzip" and h["Vary"] == "Accept-Encoding"
        assert gzip.decompress(cuerpo) == (pg.AQUI / "static/js/app.js").read_bytes()
        _, h, cuerpo = pedir(base, "/static/js/app.js")
        assert "Content-Encoding" not in h and len(cuerpo) == (pg.AQUI / "static/js/app.js").stat().st_size
        etag = h["ETag"]
        estado, _, cuerpo = pedir(base, "/static/js/app.js", cabeceras={"If-None-Match": etag})
        assert estado == 304 and cuerpo == b""
        estado, h, cuerpo = pedir(base, "/", metodo="HEAD")
        assert estado == 200 and cuerpo == b"" and int(h["Content-Length"]) > 0


def test_health_y_error_controlado(monkeypatch):
    with servidor(monkeypatch) as base:
        estado, _, cuerpo = pedir(base, "/api/health")
        assert estado == 200 and json.loads(cuerpo)["ok"] is True
        monkeypatch.setattr(pg, "obtener_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("secreto interno")))
        estado, _, cuerpo = pedir(base, "/api/snapshot")
        assert estado == 503 and b"secreto" not in cuerpo           # no se filtran detalles internos


def test_todas_las_fuentes_caidas_no_rompen_la_api(monkeypatch):
    def caido(url, **kw):
        raise OSError("sin red")
    with servidor(monkeypatch, caido) as base:
        estado, _, cuerpo = pedir(base, "/api/snapshot")
        data = json.loads(cuerpo)
        assert estado == 200 and data["items"] == []
        assert all(f["estado"] == "error" for f in data["fuentes"].values())


# ---------- Caché del snapshot ----------
def test_snapshot_vigente_no_se_reconstruye(monkeypatch):
    llamadas = []
    monkeypatch.setattr(pg, "construir_snapshot", lambda: llamadas.append(1) or {"fuentes": {"x": {"estado": "ok"}}, "items": [], "n": len(llamadas)})
    a, b = pg.obtener_snapshot(), pg.obtener_snapshot()
    assert a is b and len(llamadas) == 1


def test_snapshot_vencido_se_sirve_al_instante_y_se_actualiza_atras(monkeypatch):
    monkeypatch.setattr(pg, "construir_snapshot", lambda: {"fuentes": {"x": {"estado": "ok"}}, "items": [], "n": 1})
    primero = pg.obtener_snapshot()
    pg._cache["ts"] -= pg.TTL_MERCADO + 1                           # expira
    liberar, empezo = threading.Event(), threading.Event()

    def lento():
        empezo.set()
        liberar.wait(5)
        return {"fuentes": {"x": {"estado": "ok"}}, "items": [], "n": 2}
    monkeypatch.setattr(pg, "construir_snapshot", lento)
    t0 = time.time()
    viejo = pg.obtener_snapshot()
    assert viejo is primero and time.time() - t0 < 1                 # no esperó a las APIs
    assert empezo.wait(2)                                           # la actualización arrancó en segundo plano
    liberar.set()
    for _ in range(50):
        if pg._cache["data"]["n"] == 2:
            break
        time.sleep(0.05)
    assert pg.obtener_snapshot()["n"] == 2


def test_si_todas_las_fuentes_fallan_se_conservan_los_ultimos_datos(monkeypatch):
    bueno = {"fuentes": {"x": {"estado": "ok"}}, "items": [1], "n": 1}
    monkeypatch.setattr(pg, "construir_snapshot", lambda: bueno)
    pg.obtener_snapshot()
    pg._cache["ts"] -= pg.TTL_MERCADO + 1
    monkeypatch.setattr(pg, "construir_snapshot", lambda: {"fuentes": {"x": {"estado": "error"}}, "items": []})
    assert pg._refrescar().get("stale") is True and pg._refrescar()["items"] == [1]
