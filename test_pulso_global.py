"""Tests de Pulso Global. No requieren internet: los parsers se prueban con
respuestas de ejemplo y la ruta "en vivo" se prueba con http_json simulado."""
import json
import threading
import urllib.request
from datetime import date, timedelta
from http.server import ThreadingHTTPServer

import pytest

import pulso_global as pg


@pytest.fixture(autouse=True)
def _limpiar_estado():
    pg._ultimo_ok.clear()
    pg._macro_cache.update(ts=0.0, data=None)
    yield


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


# ---------- Snapshot simulado y JSON válido ----------
def test_snapshot_simulado_completo_y_reproducible():
    a, b = pg.construir_snapshot(True), pg.construir_snapshot(True)
    assert all(f["estado"] == "ok" for f in a["fuentes"].values())
    assert len(a["items"]) == len(pg.YAHOO) + len(pg.FX) + len(pg.CHILE_SERIES) + len(pg.CHILE_STATS)
    assert [i["value"] for i in a["items"]] == [i["value"] for i in b["items"]]
    assert a["fx_per_usd"]["CLP"] > 0 and a["feargreed"]["value"] and set(a["macro"]) == {"inflacion", "pib", "desempleo"}
    json.dumps(a, allow_nan=False)           # sin NaN/inf: el navegador podrá parsearlo


# ---------- Ruta "en vivo" con http_json simulado ----------
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


def test_snapshot_en_vivo_tolera_fallos_parciales(monkeypatch):
    monkeypatch.setattr(pg, "http_json", falso_http)
    pg._macro_cache.update(ts=0.0, data=None)
    s = pg.construir_snapshot(False)
    assert s["mode"] == "live"
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
    s = pg.construir_snapshot(False)
    assert s["fuentes"]["frankfurter"]["estado"] == "error" and "sin red" in s["fuentes"]["frankfurter"]["error"]
    assert s["fuentes"]["yahoo"]["estado"] in ("ok", "parcial") and s["items"]


# ---------- Resistencia de la fuente de Chile ----------
def test_mindicador_usa_host_alternativo(monkeypatch):
    def http(url, **kw):
        if url.startswith("https://mindicador.cl"):
            raise OSError("timed out")
        return falso_http(url)
    monkeypatch.setattr(pg, "http_json", http)
    items, estado = pg.fuente_mindicador(False)
    assert estado["estado"] == "ok" and {"usdclp", "uf", "cobre", "tpm"} <= {i["id"] for i in items}


def test_chile_parcial_si_falla_una_serie(monkeypatch):
    def http(url, **kw):
        if "libra_cobre" in url:
            raise OSError("500 Internal Server Error")
        return falso_http(url)
    monkeypatch.setattr(pg, "http_json", http)
    items, estado = pg.fuente_mindicador(False)
    ids = {i["id"] for i in items}
    assert {"usdclp", "uf", "tpm", "utm"} <= ids and "cobre" not in ids
    assert estado["estado"] == "parcial" and "Cobre" in estado["error"] and "500" in estado["error"]


def test_dolar_de_respaldo_via_yahoo_si_cae_mindicador(monkeypatch):
    def http(url, **kw):
        if "mindicador" in url:
            raise OSError("CERTIFICATE_VERIFY_FAILED")
        return falso_http(url)
    monkeypatch.setattr(pg, "http_json", http)
    items, estado = pg.fuente_mindicador(False)
    assert [i["id"] for i in items] == ["usdclp"] and items[0]["source"] == "Yahoo Finance (respaldo)"
    assert estado["estado"] == "parcial" and "CERTIFICATE_VERIFY_FAILED" in estado["error"]


def test_sin_ninguna_respuesta_el_error_es_legible(monkeypatch):
    monkeypatch.setattr(pg, "http_json", lambda url, **kw: (_ for _ in ()).throw(OSError("sin red")))
    s = pg.construir_snapshot(False)
    assert s["fuentes"]["mindicador"]["estado"] == "error" and "sin red" in s["fuentes"]["mindicador"]["error"]


def test_se_conservan_los_ultimos_datos_si_la_fuente_cae(monkeypatch):
    monkeypatch.setattr(pg, "http_json", falso_http)
    ok = pg.construir_snapshot(False)
    assert any(i["id"] == "uf" for i in ok["items"])

    def caido(url, **kw):
        if "mindicador" in url:
            raise OSError("sin red")
        return falso_http(url)
    monkeypatch.setattr(pg, "http_json", caido)
    s = pg.construir_snapshot(False)
    f = s["fuentes"]["mindicador"]
    assert f["estado"] == "parcial" and "datos anteriores" in f["error"]
    assert {"uf", "tpm", "utm"} <= {i["id"] for i in s["items"]}      # se conservan
    assert next(i for i in s["items"] if i["id"] == "usdclp")["source"] == "Yahoo Finance (respaldo)"


# ---------- Servidor ----------
def test_servidor_entrega_interfaz_y_api():
    pg.Handler.simulado = True
    pg._cache.update(ts=0.0, data=None, sim=None)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), pg.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        html = urllib.request.urlopen(base + "/").read().decode()
        assert "Pulso Global" in html
        data = json.load(urllib.request.urlopen(base + "/api/snapshot"))
        assert data["mode"] == "simulado" and data["items"]
        try:
            urllib.request.urlopen(base + "/nada")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        srv.shutdown()


def test_estaticos_se_sirven_y_no_se_puede_salir_de_static():
    import urllib.error
    pg.Handler.simulado = True
    srv = ThreadingHTTPServer(("127.0.0.1", 0), pg.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def get(ruta):
        try:
            r = urllib.request.urlopen(base + ruta)
            return r.status, r.headers.get("Content-Type"), r.read()
        except urllib.error.HTTPError as e:
            return e.code, None, b""
    try:
        html = get("/")[2].decode()
        assert "/static/css/styles.css" in html and "<style>" not in html
        estado, tipo, cuerpo = get("/static/css/styles.css")
        assert estado == 200 and tipo.startswith("text/css") and b"#stage" in cuerpo
        for malo in ("/static/../pulso_global.py", "/static/%2e%2e/pulso_global.py",
                     "/static/css", "/static/css/no-existe.css", "/static/..%2fREADME.md"):
            assert get(malo)[0] == 404, malo
    finally:
        srv.shutdown()
