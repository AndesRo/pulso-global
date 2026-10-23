# 🌐 Pulso Global

### Dashboard global de mercados, divisas e indicadores económicos

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)](https://developer.mozilla.org/es/docs/Web/HTML)
[![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white)](https://developer.mozilla.org/es/docs/Web/CSS)
[![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=222222)](https://developer.mozilla.org/es/docs/Web/JavaScript)
[![GitHub](https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/AndesRo/pulso-global)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=for-the-badge&logo=render&logoColor=111111)](https://render.com/)

**Pulso Global** es una aplicación web responsiva para explorar mercados financieros, divisas, criptomonedas e indicadores macroeconómicos de Chile y el mundo.

Su backend, desarrollado en Python, consulta **cinco APIs públicas gratuitas sin requerir API keys**, consolida los datos mediante ingesta paralela, calcula métricas y alertas, mantiene una caché de información y entrega un snapshot a la interfaz web.

🔗 **Demo en producción:** [Abrir Pulso Global](https://pulso-global.onrender.com/)

💻 **Código fuente:** [AndesRo/pulso-global](https://github.com/AndesRo/pulso-global)

---

## 📸 Características principales

- 📊 **Dashboard global:** resumen de mercados e indicadores en una interfaz unificada.
- 📈 **Bolsas internacionales:** S&P 500, Nasdaq, Dow Jones, Euro Stoxx, FTSE, Nikkei, Hang Seng, Bovespa e IPSA.
- 🛢️ **Materias primas:** oro, plata, cobre, petróleo, gas y otros instrumentos disponibles.
- 💱 **Divisas:** cotizaciones frente al dólar y conversor interactivo.
- ₿ **Criptomonedas:** Bitcoin, Ethereum, Solana e índice Fear & Greed.
- 🇨🇱 **Indicadores de Chile:** dólar, UF, UTM, TPM, IPC, desempleo, IMACEC y cobre.
- 🌍 **Indicadores macroeconómicos:** comparación internacional de inflación, crecimiento del PIB y desempleo.
- 🚨 **Sistema de alertas:** detección de variaciones relevantes, movimientos atípicos y extremos recientes.
- 📉 **Análisis por instrumento:** gráficos interactivos, mínimos y máximos, medias móviles y z-score.
- 🔌 **Estado de las fuentes:** visibilidad de la disponibilidad de los servicios de datos.
- 💾 **Caché y recuperación:** conservación de los últimos datos válidos cuando una fuente falla.
- 📱 **Diseño responsivo:** interfaz adaptada a escritorio, tablet y teléfono móvil.

## 🏗️ Arquitectura

```text
┌───────────────────────────────┐
│       5 APIs públicas         │
│ Yahoo · Frankfurter ·         │
│ mindicador.cl · Banco Mundial │
│ · alternative.me              │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│        pulso_global.py        │
│ Ingesta paralela              │
│ Normalización y métricas      │
│ Alertas y caché               │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│         /api/snapshot         │
│ Snapshot consolidado en JSON  │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│          Frontend             │
│ HTML · CSS · JavaScript       │
│ Dashboard y gráficos          │
└───────────────────────────────┘
```

La arquitectura separa la consulta y consolidación de datos de la presentación visual. Las actualizaciones se gestionan en segundo plano y los visitantes reciben el último snapshot disponible.

## 🛠️ Stack tecnológico

| Tecnología | Función |
|---|---|
| 🐍 **Python 3.10+** | Backend, ingesta de datos, métricas, alertas y servidor HTTP. |
| 🌐 **HTML5** | Estructura de la interfaz. |
| 🎨 **CSS3** | Diseño visual, animaciones y adaptación responsive. |
| ⚡ **JavaScript** | Navegación, interactividad, gráficos y consumo de datos. |
| 🔗 **HTTP / JSON** | Comunicación entre el backend y la interfaz. |
| 🧵 **ThreadingHTTPServer** | Servidor HTTP concurrente de la biblioteca estándar. |
| 🧪 **pytest** | Ejecución de pruebas automatizadas. |
| 🐙 **Git / GitHub** | Control de versiones y repositorio del proyecto. |
| 🚀 **Render** | Despliegue de la aplicación. |

**Dependencias de ejecución:** el backend utiliza la biblioteca estándar de Python, por lo que no necesita paquetes externos para su funcionamiento básico. `pytest` se utiliza para ejecutar la suite de pruebas indicada.

## 📁 Estructura del proyecto

```text
Pulso Global/
├── pulso_global.py          # Backend, APIs, métricas y servidor HTTP
├── index.html               # Estructura principal de la interfaz
├── static/
│   ├── css/
│   │   └── styles.css       # Estilos y diseño responsive
│   ├── js/
│   │   └── app.js           # Lógica de la interfaz
│   └── img/
│       └── favicon.svg      # Icono de la aplicación
├── cache/                   # Caché local de datos de Chile
├── test_pulso_global.py     # Pruebas del backend sin internet
├── monitor_indicadores.py   # Monitor de indicadores por consola
├── test_monitor.py          # Pruebas del monitor de consola
└── README.md                # Documentación
```

La carpeta `cache/` se crea automáticamente. Sus archivos locales, como `cache/chile.json`, no deben subirse al repositorio.

## 🌍 Fuentes de datos

Pulso Global integra cinco fuentes públicas para obtener información de mercados e indicadores económicos.

| Fuente | Información utilizada |
|---|---|
| [Yahoo Finance](https://finance.yahoo.com/) | Índices bursátiles, VIX, bono estadounidense a 10 años, DXY, materias primas y criptomonedas. |
| [Frankfurter](https://www.frankfurter.app/) | Tipos de cambio para EUR, GBP, JPY, CNY, BRL, MXN y CHF frente al USD. |
| [mindicador.cl](https://mindicador.cl/) | Indicadores económicos de Chile: dólar, UF, UTM, cobre, TPM, IPC, desempleo e IMACEC. |
| [Banco Mundial](https://data.worldbank.org/) | Inflación, crecimiento del PIB y desempleo de diez países. |
| [Alternative.me](https://alternative.me/crypto/fear-and-greed-index/) | Índice Fear & Greed para medir el sentimiento del mercado cripto. |

Las fuentes se consultan sin API keys en la implementación descrita. La disponibilidad, frecuencia y cobertura dependen de cada proveedor.

## 🖥️ Interfaz y navegación

La aplicación está organizada en siete secciones:

| Sección | Contenido |
|---|---|
| **Resumen** | Indicadores destacados y estado de las fuentes. |
| **Mercados** | Bolsas, materias primas y otros instrumentos. |
| **Divisas** | Tipos de cambio y conversor. |
| **Cripto** | Criptomonedas y sentimiento del mercado. |
| **Chile** | Indicadores económicos nacionales. |
| **Macro** | Comparaciones macroeconómicas entre países. |
| **Alertas** | Variaciones relevantes y movimientos atípicos. |

Cada sección dispone de navegación directa mediante rutas hash, por ejemplo `/#/divisas` y `/#/alertas`.

### Diseño adaptativo

- **Escritorio:** cuadrículas de varias columnas y panel de detalle lateral.
- **Tablet:** distribución flexible según el ancho disponible.
- **Móvil:** una o dos columnas, navegación inferior y detalle mediante una hoja deslizable.

### Análisis de instrumentos

El panel de detalle incorpora:

- Gráficos con intervalos de 1 y 3 meses.
- Mínimos y máximos del período.
- Medias móviles.
- Z-score del último retorno.
- Indicadores de variación y alertas disponibles.

La interfaz incluye también un conversor de divisas, un medidor Fear & Greed y barras comparativas por país.

## 🚨 Sistema de alertas

El sistema combina umbrales de variación diaria, detección estadística de movimientos atípicos y nuevos extremos de tres meses.

| Categoría | Umbral de variación diaria |
|---|---:|
| Bolsas | 2 % |
| Materias primas | 3 % |
| Criptomonedas | 6 % |
| Divisas | 1 % |
| VIX | 8 % |
| Bono estadounidense a 10 años | 10 puntos básicos |
| Indicadores de Chile | 1,5 % |

**Reglas adicionales:**

- **Movimiento atípico:** z-score del último retorno frente a 30 días igual o superior a 2.
- **Extremos:** detección de un nuevo máximo o mínimo de tres meses.

Las alertas son señales informativas generadas por reglas programadas; no constituyen predicciones de mercado.

## ⚙️ Ejecución local

### Requisitos

- Python 3.10 o superior.
- Git, opcional para clonar el repositorio.
- Conexión a internet para consultar las APIs externas.

### 1. Clonar el repositorio

```bash
git clone https://github.com/AndesRo/pulso-global.git
cd pulso-global
```

### 2. Iniciar el servidor

```bash
python pulso_global.py
```

La dirección local predeterminada es:

```text
http://127.0.0.1:8765
```

### 3. Comandos disponibles

```bash
# Iniciar el servidor local
python pulso_global.py

# Escuchar en todas las interfaces de red
python pulso_global.py --host 0.0.0.0

# Imprimir un snapshot y finalizar
python pulso_global.py --json

# Diagnosticar las APIs individualmente
python pulso_global.py --diagnostico

# Ejecutar las pruebas
pytest -q
```

También se pueden configurar opciones mediante las variables de entorno `HOST`, `PORT` y `LOG_LEVEL`.

> Ejecutar el servidor con `--host 0.0.0.0` permite que escuche en otras interfaces de red. Utiliza esta opción únicamente en redes y entornos de confianza, con las medidas de seguridad correspondientes.

## ☁️ Despliegue y operación

La aplicación está desplegada en Render y el servidor utiliza el puerto configurado por el entorno cuando corresponde.

### Características del backend

- **Servidor concurrente:** `ThreadingHTTPServer` de Python.
- **Compresión:** respuestas gzip.
- **Validación de caché HTTP:** cabeceras `ETag`.
- **Cabeceras de seguridad:** política CSP, `X-Frame-Options`, `nosniff` y otras configuraciones del servidor.
- **Cierre ordenado:** gestión de `SIGTERM`.
- **Precarga:** primer snapshot al iniciar el servicio.
- **Actualización compartida:** los datos se actualizan como máximo una vez por minuto, independientemente de la cantidad de visitantes.
- **Logs:** salida estándar y configuración del nivel mediante `--log` o `LOG_LEVEL`.

### Endpoint de salud

```http
GET /healthz
```

Devuelve un objeto JSON con el estado del servicio y la antigüedad del snapshot, por ejemplo:

```json
{
  "ok": true,
  "snapshot_edad_s": 12
}
```

El valor numérico es ilustrativo; la respuesta real depende del momento de la consulta.

### HTTPS

El servidor de la aplicación sirve HTTP. Para publicarlo en un entorno propio, el tráfico HTTPS debe terminar en un proxy inverso o servicio de infraestructura que gestione TLS, como Nginx, Caddy o Cloudflare.

## 🛡️ Resiliencia y manejo de errores

La aplicación prioriza conservar la última información válida cuando una fuente externa deja de responder.

- Los estados de las fuentes se muestran en el Resumen.
- Los errores de consulta se registran para facilitar el diagnóstico.
- Los datos de Chile se consultan como máximo cada 15 minutos, individualmente y con pausas.
- Cuando falla una consulta de Chile, se contempla un nuevo intento a los dos minutos.
- La caché local `cache/chile.json` puede conservar los últimos datos válidos durante un máximo de tres días.
- Yahoo Finance se utiliza como respaldo para el dólar.

Los datos antiguos pueden seguir disponibles mientras se recupera una fuente. Por ello, es importante considerar su antigüedad y el estado de actualización mostrado en la aplicación.

## ⚠️ Limitaciones conocidas

### mindicador.cl

El servicio puede presentar lentitud, interrupciones o errores HTTP 500. La consulta espaciada y la caché ayudan a reducir el impacto, pero no garantizan disponibilidad continua.

### Yahoo Finance

Yahoo Finance no ofrece una API oficial gratuita para esta implementación. El endpoint público utilizado no está documentado oficialmente y puede cambiar, limitar las consultas o estar sujeto a condiciones de uso. Para un servicio comercial se recomienda evaluar un proveedor con licencia y condiciones contractuales adecuadas.

### Retraso y frecuencia de los datos

- Las cotizaciones bursátiles pueden tener hasta 15 minutos de retraso.
- Los indicadores macroeconómicos del Banco Mundial tienen frecuencia anual y reflejan el último año disponible por país.
- La disponibilidad y la actualización dependen de los proveedores externos.

## 🧪 Pruebas

El proyecto incorpora pruebas para comprobar el comportamiento del backend sin depender de una conexión a internet.

Desde la raíz del proyecto:

```bash
pytest -q
```

Las pruebas de la suite principal están diseñadas para ejecutarse sin internet. Si se incorporan pruebas de integración con proveedores reales, conviene distinguirlas de las pruebas unitarias.

## 🔭 Posibles mejoras futuras

- Incorporar nuevas fuentes oficiales y proveedores con API documentada.
- Añadir mayor trazabilidad de fechas, unidades y frecuencia de actualización.
- Ampliar las pruebas automatizadas y de integración.
- Mejorar la observabilidad y el monitoreo de disponibilidad.
- Seguir optimizando el rendimiento y la accesibilidad de la interfaz.
- Incorporar más indicadores y herramientas de análisis.

## 👨‍💻 Autor

**Andrés Romero Millaquén**  
Analista Programador Computacional

Desarrollo web · Automatización · Integración de datos

[![GitHub](https://img.shields.io/badge/GitHub-AndesRo-181717?style=flat&logo=github&logoColor=white)](https://github.com/AndesRo)

**Proyecto:** [Pulso Global en GitHub](https://github.com/AndesRo/pulso-global)

---

*Pulso Global es un proyecto de portafolio tecnológico. La información presentada tiene fines informativos y no constituye asesoría financiera.*

