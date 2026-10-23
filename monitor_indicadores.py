"""
Monitor automatizado de indicadores económicos de Chile.

Pipeline: ingesta (API pública mindicador.cl) -> análisis estadístico ->
reglas de alerta -> reporte HTML + JSON.  Sin API key.

Uso:
    python monitor_indicadores.py              # datos reales (requiere internet)
    python monitor_indicadores.py --simulado   # datos sintéticos reproducibles
"""
import argparse
import base64
import io
import json
import random
import statistics
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

API = "https://mindicador.cl/api/{codigo}/{anio}"
INDICADORES = {
    "dolar": "Dólar observado",
    "euro": "Euro",
    "uf": "Unidad de Fomento",
    "utm": "UTM",
}
UMBRAL_VAR_DIARIA = 1.5   # % de variación diaria que dispara alerta
UMBRAL_ZSCORE = 2.0       # desviaciones estándar que disparan alerta
DIAS = 90


# ---------- 1. Ingesta ----------
def descargar_serie(codigo: str, dias: int = DIAS) -> list[tuple[date, float]]:
    """Descarga la serie desde mindicador.cl (orden cronológico ascendente)."""
    url = API.format(codigo=codigo, anio=date.today().year)
    with urllib.request.urlopen(url, timeout=10) as resp:
        datos = json.load(resp)["serie"]
    serie = [(datetime.fromisoformat(d["fecha"][:10]).date(), float(d["valor"]))
             for d in datos]
    return sorted(serie)[-dias:]


def simular_serie(codigo: str, dias: int = DIAS) -> list[tuple[date, float]]:
    """Serie sintética reproducible (caminata aleatoria). Inyecta un salto
    en el dólar para demostrar el sistema de alertas."""
    rng = random.Random(sum(map(ord, codigo)))
    base = {"dolar": 950, "euro": 1050, "uf": 39000, "utm": 68000}[codigo]
    vol, drift = (0.0001, 0.0002) if codigo in ("uf", "utm") else (0.007, 0.0)
    valor, hoy, serie = base, date.today(), []
    for i in range(dias):
        valor *= 1 + drift + rng.gauss(0, vol)
        if codigo == "dolar" and i == dias - 1:
            valor *= 1.024  # shock simulado
        serie.append((hoy - timedelta(days=dias - 1 - i), valor))
    return serie


def obtener_serie(codigo: str, simulado: bool):
    if simulado:
        return simular_serie(codigo), "simulado"
    try:
        return descargar_serie(codigo), "api"
    except Exception as e:  # red caída, API cambiada, etc.
        print(f"[aviso] {codigo}: API no disponible ({e}). Usando datos simulados.")
        return simular_serie(codigo), "simulado (fallback)"


# ---------- 2. Análisis ----------
@dataclass
class Resultado:
    codigo: str
    nombre: str
    fuente: str
    ultimo: float
    var_1d: float
    var_30d: float
    sma7: float
    sma30: float
    zscore: float
    alertas: list = field(default_factory=list)
    serie: list = field(default_factory=list, repr=False)


def sma(valores: list[float], n: int) -> float:
    return statistics.fmean(valores[-n:])


def zscore_ultimo_retorno(valores: list[float], ventana: int = 30) -> float:
    ret = [b / a - 1 for a, b in zip(valores, valores[1:])]
    historico, ultimo = ret[-ventana - 1:-1], ret[-1]
    sd = statistics.stdev(historico)
    return (ultimo - statistics.fmean(historico)) / sd if sd else 0.0


def analizar(codigo: str, serie, fuente: str) -> Resultado:
    v = [x for _, x in serie]
    r = Resultado(
        codigo=codigo, nombre=INDICADORES[codigo], fuente=fuente,
        ultimo=v[-1],
        var_1d=(v[-1] / v[-2] - 1) * 100,
        var_30d=(v[-1] / v[-31] - 1) * 100,
        sma7=sma(v, 7), sma30=sma(v, 30),
        zscore=zscore_ultimo_retorno(v),
        serie=[(d.isoformat(), x) for d, x in serie],
    )
    r.alertas = evaluar_alertas(r)
    return r


# ---------- 3. Reglas de alerta ----------
def evaluar_alertas(r: Resultado) -> list[str]:
    alertas = []
    if abs(r.var_1d) >= UMBRAL_VAR_DIARIA:
        alertas.append(f"Variación diaria de {r.var_1d:+.2f}% (umbral {UMBRAL_VAR_DIARIA}%)")
    if abs(r.zscore) >= UMBRAL_ZSCORE:
        alertas.append(f"Movimiento atípico: z-score {r.zscore:+.1f}")
    if r.ultimo > r.sma7 > r.sma30 and r.var_30d > 3:
        alertas.append("Tendencia alcista sostenida (precio > SMA7 > SMA30)")
    return alertas


# ---------- 4. Reporte ----------
def grafico_base64(resultados: list[Resultado]) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    fig, ejes = plt.subplots(len(resultados), 1, figsize=(9, 2.6 * len(resultados)))
    ejes = [ejes] if len(resultados) == 1 else ejes
    for ax, r in zip(ejes, resultados):
        fechas = [datetime.fromisoformat(d) for d, _ in r.serie]
        vals = [x for _, x in r.serie]
        ax.plot(fechas, vals, label=r.nombre, color="#0A66C2", lw=1.8)
        ax.plot(fechas[6:], [statistics.fmean(vals[i - 6:i + 1]) for i in range(6, len(vals))],
                label="SMA7", color="#F59E0B", lw=1)
        ax.set_title(r.nombre, loc="left", fontsize=10, fontweight="bold")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def generar_html(resultados: list[Resultado]) -> str:
    filas = ""
    for r in resultados:
        estado = "🔴 " + "; ".join(r.alertas) if r.alertas else "🟢 Normal"
        filas += (f"<tr><td>{r.nombre}</td><td>{r.ultimo:,.2f}</td>"
                  f"<td>{r.var_1d:+.2f}%</td><td>{r.var_30d:+.2f}%</td>"
                  f"<td>{r.zscore:+.1f}</td><td>{estado}</td></tr>")
    img = grafico_base64(resultados)
    img_html = f'<img src="data:image/png;base64,{img}" style="max-width:100%">' if img else ""
    n_alertas = sum(bool(r.alertas) for r in resultados)
    return f"""<!doctype html><html lang="es"><meta charset="utf-8">
<title>Monitor de indicadores</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1f2937}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:.5rem;border-bottom:1px solid #e5e7eb;text-align:left;font-size:.9rem}}
th{{background:#f3f4f6}}.kpi{{background:#eff6ff;padding:1rem;border-radius:8px;margin:1rem 0}}</style>
<h1>📊 Monitor de indicadores económicos — Chile</h1>
<p>Generado: {datetime.now():%Y-%m-%d %H:%M} · Fuente: {resultados[0].fuente}</p>
<div class="kpi"><b>{n_alertas}</b> de {len(resultados)} indicadores con alertas activas</div>
<table><tr><th>Indicador</th><th>Último</th><th>Var 1d</th><th>Var 30d</th><th>z-score</th><th>Estado</th></tr>{filas}</table>
{img_html}</html>"""


# ---------- 5. Orquestación ----------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simulado", action="store_true", help="usar datos sintéticos")
    ap.add_argument("--salida", default="reporte", help="carpeta de salida")
    args = ap.parse_args()

    resultados = []
    for codigo in INDICADORES:
        serie, fuente = obtener_serie(codigo, args.simulado)
        resultados.append(analizar(codigo, serie, fuente))

    out = Path(args.salida)
    out.mkdir(exist_ok=True)
    (out / "reporte.html").write_text(generar_html(resultados), encoding="utf-8")
    (out / "resumen.json").write_text(
        json.dumps([{k: v for k, v in asdict(r).items() if k != "serie"} for r in resultados],
                   ensure_ascii=False, indent=2), encoding="utf-8")

    for r in resultados:
        print(f"{'🔴' if r.alertas else '🟢'} {r.nombre:<18} {r.ultimo:>12,.2f}  {r.var_1d:+.2f}% (1d)")
        for a in r.alertas:
            print(f"     ⚠ {a}")
    print(f"\nReporte: {out / 'reporte.html'}")


if __name__ == "__main__":
    main()