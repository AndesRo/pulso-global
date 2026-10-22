# 📊 Pulso Global · indicadores económicos del mundo

App local en Python + interfaz web vertical (9:16) que agrega **5 APIs públicas gratuitas, sin API key**, calcula métricas y alertas, y muestra todo en una interfaz interactiva pensada para grabar demos en video.

```
APIs públicas ──► pulso_global.py (ingesta paralela · métricas · alertas · caché) ──► /api/snapshot ──► index.html
```

## Estructura

```
Pulso Global/
├── pulso_global.py          # backend: APIs, métricas, alertas y servidor local
├── index.html               # marcado de la interfaz y su script
├── static/
│   └── css/
│       └── styles.css       # estilos (servidos en /static/...)
├── test_pulso_global.py     # tests (sin internet)
├── monitor_indicadores.py   # versión de consola
├── test_monitor.py
└── README.md
```

## Fuentes

| Fuente | Qué aporta |
|---|---|
| Yahoo Finance (chart) | 9 bolsas (S&P 500, Nasdaq, Dow, Euro Stoxx, FTSE, Nikkei, Hang Seng, Bovespa, IPSA), VIX, bono 10Y EE.UU., DXY, oro, plata, WTI, Brent, cobre, gas, Bitcoin, Ethereum, Solana |
| Frankfurter (BCE) | EUR, GBP, JPY, CNY, BRL, MXN, CHF vs. USD |
| mindicador.cl | Chile: dólar, UF, UTM, cobre, TPM, IPC, desempleo, IMACEC |
| Banco Mundial | Inflación, crecimiento del PIB y desempleo de 10 países |
| alternative.me | Índice Fear & Greed (sentimiento cripto) |

## Ejecutar

```bash
python pulso_global.py              # datos reales, abre http://localhost:8765
python pulso_global.py --simulado   # datos sintéticos, sin internet (muestra un cintillo de aviso)
python pulso_global.py --json       # imprime un snapshot y termina
python pulso_global.py --diagnostico  # prueba cada API por separado y muestra el error exacto
pytest -q                           # 20 tests, sin internet
```

Solo usa la librería estándar de Python (3.10+).

## Interfaz

7 secciones: **Resumen · Mercados · Divisas · Cripto · Chile · Macro · Alertas**. Toca cualquier instrumento para abrir su detalle (gráfico interactivo 1M/3M, mínimos/máximos, medias móviles, z-score). Incluye conversor de divisas, medidor Fear & Greed y barras comparativas por país.

Estado de cada fuente visible en el Resumen (verde = ok, ámbar = parcial, rojo = caída). Nunca se inventan datos: si una API falla, se muestra como caída.

## Grabar el video vertical

1. `python pulso_global.py --sin-navegador`
2. Abre `http://localhost:8765/?tour=1&clean=1` (`tour=1` inicia el recorrido automático, `clean=1` oculta el botón y el cursor).
3. El tour dura ~1 minuto y se repite en bucle. Teclas: `T` iniciar/detener, `Esc` cerrar detalle.

**Mejor calidad (1080×1920 exactos):** en OBS agrega una fuente *Navegador* con esa URL, ancho 1080 y alto 1920, con lienzo 1080×1920.
**Rápido:** Chrome → F12 → modo dispositivo → 540×960 → graba la pantalla (Win+Alt+R / Cmd+Shift+5).

## Reglas de alerta

| Regla | Umbral |
|---|---|
| Variación diaria | Bolsas 2 % · materias primas 3 % · cripto 6 % · divisas 1 % · VIX 8 % · bono 10Y 10 pb · Chile 1,5 % |
| Movimiento atípico | z-score del último retorno vs. 30 días ≥ 2 |
| Extremos | Nuevo máximo o mínimo de 3 meses |

## Notas y límites

- Yahoo Finance no tiene API oficial gratuita: el endpoint es público pero no documentado y puede cambiar o limitar peticiones. Úsalo para demos y proyectos personales.
- Los precios de bolsas pueden llevar hasta 15 minutos de retraso.
- Los datos macro del Banco Mundial son anuales (el último año disponible por país).
- El servidor escucha solo en `127.0.0.1`.

## Primer proyecto de la carpeta

`monitor_indicadores.py` es la versión de consola (dólar, euro, UF y UTM) que genera un reporte HTML estático.