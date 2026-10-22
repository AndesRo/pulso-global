# 🌐 Pulso Global

### Observatorio interactivo de mercados e indicadores macroeconómicos

[![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)](https://developer.mozilla.org/es/docs/Web/HTML)
[![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white)](https://developer.mozilla.org/es/docs/Web/CSS)
[![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=222222)](https://developer.mozilla.org/es/docs/Web/JavaScript)
[![GitHub](https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/AndesRo/pulso-global)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=for-the-badge&logo=render&logoColor=111111)](https://render.com/)

**Pulso Global** es una aplicación web de visualización financiera y macroeconómica que reúne indicadores, mercados y datos relevantes en una interfaz interactiva de estilo terminal financiero.

El proyecto combina un backend ligero en Python con tecnologías web nativas para presentar información mediante tarjetas de indicadores, gráficos, variaciones de mercado, herramientas de conversión y paneles temáticos.

🔗 **Demo en línea:** [Abrir Pulso Global](https://pulso-global.onrender.com/)

💻 **Repositorio:** [AndesRo/pulso-global](https://github.com/AndesRo/pulso-global)

---

## ✨ Características principales

- 📊 **Dashboard interactivo:** visualización organizada de indicadores y métricas.
- 📈 **Mercados financieros:** paneles para consultar índices, materias primas y otros instrumentos disponibles en la aplicación.
- 🌍 **Indicadores macroeconómicos:** información organizada en secciones temáticas.
- 🇨🇱 **Indicadores de Chile:** panel dedicado a métricas de interés nacional.
- ₿ **Criptomonedas:** tarjetas de información y visualizaciones de mercado.
- 💱 **Conversor:** herramienta interactiva para consultar conversiones entre monedas disponibles.
- 🔔 **Panel de alertas:** presentación visual de eventos y variaciones relevantes.
- 🔎 **Detalles de instrumentos:** panel con información ampliada y gráficos.
- ▶️ **Tour automático:** recorrido visual por las secciones de la interfaz.
- 📱 **Diseño responsive:** adaptación de la interfaz a diferentes tamaños de pantalla.

> La disponibilidad, actualización y cobertura de cada indicador dependen de las fuentes de datos y de la respuesta de los servicios correspondientes.

## 🛠️ Tecnologías utilizadas

| Tecnología | Aplicación en el proyecto |
|---|---|
| 🐍 Python | Servidor HTTP, lógica del backend y procesamiento de datos. |
| 🌐 HTML5 | Estructura de la interfaz web. |
| 🎨 CSS3 | Diseño visual, tema oscuro, animaciones y adaptación responsive. |
| ⚡ JavaScript | Interactividad, navegación, gráficos y comunicación con el backend. |
| 🔗 HTTP / JSON | Comunicación entre la interfaz y los endpoints del servidor. |
| 🧪 unittest | Pruebas automatizadas con las herramientas de testing de Python. |
| 🐙 Git y GitHub | Control de versiones y alojamiento del código fuente. |
| 🚀 Render | Despliegue de la aplicación web. |

**Enfoque técnico:** Python con biblioteca estándar, sin necesidad de instalar dependencias externas para la ejecución básica.

## 🏗️ Arquitectura

La aplicación utiliza una arquitectura ligera con un servidor Python y una interfaz web independiente en sus archivos principales.

```text
Pulso Global
│
├── pulso_global.py       # Servidor y lógica del backend
├── index.html            # Interfaz y comportamiento del frontend
├── styles.css            # Estilos y diseño responsive
├── static/               # Recursos estáticos
├── test_pulso_global.py  # Pruebas automatizadas
└── README.md             # Documentación
```

## 🚀 Ejecución local

### Requisitos

- Python 3 instalado.
- Git, si deseas clonar el repositorio.
- Un navegador web actualizado.

### 1. Clonar el repositorio

```bash
git clone https://github.com/AndesRo/pulso-global.git
cd pulso-global
```

### 2. Iniciar la aplicación

```bash
python pulso_global.py
```

Si tu instalación utiliza el comando `py` en Windows, también puedes ejecutar:

```powershell
py pulso_global.py
```

### 3. Abrir en el navegador

Utiliza la dirección local que indique el servidor al iniciarse. En la configuración local original, el puerto predeterminado es `8765`:

```text
http://127.0.0.1:8765
```

Si el puerto está ocupado o modificaste la configuración de inicio, utiliza el puerto que corresponda.

## 🧪 Pruebas

El proyecto incluye un archivo de pruebas con `unittest`, el framework de pruebas integrado en Python.

Para ejecutar las pruebas desde la raíz del proyecto:

```bash
python -m unittest -v
```

## ☁️ Despliegue

La aplicación está preparada para ejecutarse en Render utilizando el puerto proporcionado por el entorno de despliegue.

Configuración de referencia:

- **Repositorio:** `AndesRo/pulso-global`
- **Rama:** `main`
- **Build Command:** `echo "No external dependencies required"`
- **Start Command:** `python pulso_global.py`

Render proporciona la variable de entorno `PORT`, que el servidor utiliza para escuchar las conexiones en el entorno de producción.

## 🎯 Objetivo del proyecto

Pulso Global forma parte de un portafolio de desarrollo orientado a demostrar competencias prácticas en:

- Desarrollo de interfaces web.
- Integración entre frontend y backend.
- Diseño de dashboards y visualización de indicadores.
- Manejo de solicitudes HTTP y datos JSON.
- Diseño responsive y experiencia de usuario.
- Desarrollo y despliegue de aplicaciones web.

El objetivo es transformar información financiera y económica en una experiencia visual clara, navegable e intuitiva.

## 🔭 Mejoras futuras

- Incorporar indicadores adicionales y ampliar las fuentes de datos.
- Mejorar la trazabilidad de las fuentes y sus fechas de actualización.
- Añadir más pruebas automatizadas.
- Optimizar el rendimiento y el manejo de errores de los servicios externos.
- Continuar perfeccionando la experiencia móvil y la accesibilidad.

## 👨‍💻 Autor

**Andrés Romero Millaquén**  
Analista Programador Computacional | Desarrollo web y soluciones tecnológicas.

[![GitHub](https://img.shields.io/badge/GitHub-AndesRo-181717?style=flat&logo=github)](https://github.com/AndesRo)

---

*Desarrollado como proyecto de portafolio tecnológico.*
