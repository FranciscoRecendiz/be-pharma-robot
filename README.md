<h1 align="center">🧬 BePharma AI Prospecting — v2.0</h1>

<p align="center">
  <b>Descubrimiento y validación automatizada de empresas farmacéuticas y healthcare</b><br>
  <i>Una solución interna desarrollada por BePharma Analytics (Nov 2025)</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue" />
  <img src="https://img.shields.io/badge/Docker-Compose-orange" />
  <img src="https://img.shields.io/badge/n8n-Orchestration-success" />
  <img src="https://img.shields.io/badge/Groq-LLM-purple" />
  <img src="https://img.shields.io/badge/Status-Stable-brightgreen" />
</p>

---

## 🚀 Propósito General

**BePharma AI Prospecting** es un sistema de inteligencia diseñado para automatizar la búsqueda, clasificación y enriquecimiento de empresas del sector farmacéutico y healthcare con potencial de alianzas (licenciamiento, distribución, CDMO/CMO).

Integra:
- 🤖 **LLMs (Groq / Llama 3.3)** para clasificación semántica.  
- 🌐 **DuckDuckGo Search (DDG)** para descubrimiento libre y reproducible.  
- ⚡ **Pipelines asincrónicos en Python** para scraping y validación.  
- 🧩 **n8n** para orquestación visual y notificaciones automáticas.  

---

## 🧱 Arquitectura del Proyecto

<details>
<summary>📂 Ver estructura completa del proyecto</summary>

```text
bp-analytics/
├── docker-compose.yml               ← Configuración contenedor n8n + Python
├── Dockerfile                       ← Imagen base con dependencias
├── requirements.txt                 ← Librerías principales
├── agent_requirements.txt           ← Librerías específicas para agentes LLM
├── setup_project.py                 ← Inicialización del entorno local
├── .gitignore                       ← Exclusiones de datos y entornos
│
├── src/
│   ├── pipelines/
│   │   ├── find_companies_daily.py      ← Descubrimiento y scoring Groq + DDG
│   │   ├── resolve_sites_post.py        ← Validación de sitios oficiales
│   │   └── extract_contacts_from_sites.py (en desarrollo)
│   └── utils/
│       └── site_resolver.py             ← Lógica de resolución y verificación web
│
├── data/
│   ├── raw/             ← Listas ICP (país × giro)
│   ├── processed/       ← Resultados por país
│   ├── cache/           ← Cache LLM + DDG
│   ├── registry/        ← Registro persistente (anti-duplicado)
│   ├── logs/            ← Bitácoras de uso de tokens
│   ├── interim/         ← Archivos intermedios
│   ├── staging/         ← Resultados previos a integración
│   └── external/        ← Archivos externos cargados manualmente
│
├── CRM_EMPRESAS/        ← CRM interno de compañías verificadas
├── models/              ← Clasificadores y embeddings entrenados
├── reports/             ← Dashboards y resúmenes analíticos
├── docs/                ← Documentación técnica
├── n8n_data/            ← Persistencia de flujos n8n (volumen Docker)
├── notebooks/           ← Exploraciones y validaciones
└── tests/               ← Pruebas unitarias e integración
</details>
⚙️ Stack Tecnológico
Componente	Descripción
🐍 Python 3.12	Base principal de pipelines
🧠 LangChain + Groq	LLM para clasificación y scoring
🌍 DuckDuckGo Search	Motor libre de descubrimiento web
🐳 Docker Compose	Contenedores reproducibles
🧩 n8n	Orquestación visual y notificaciones
📊 Pandas / Asyncio / Tenacity	Procesamiento asíncrono y control de errores

🧩 Módulos Principales
Archivo	Función
find_companies_daily.py	Descubrimiento de empresas (Groq + DDG)
resolve_sites_post.py	Validación asincrónica de sitios oficiales
site_resolver.py	Motor de resolución y limpieza de dominios
icp_targets.csv	Input: combinaciones país × giro
companies_seen.csv	Registro persistente de empresas vistas
empresas_final.csv	Resultado final enriquecido y verificado

🐳 Docker Compose
Archivo: docker-compose.yml

yaml
Copiar código
version: '3.8'

services:
  n8n:
    build: .
    container_name: n8n-bepharma
    ports:
      - "5678:5678"
    environment:
      - N8N_HOST=localhost
      - N8N_PORT=5678
      - N8N_PROTOCOL=http
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=admin
      - N8N_BASIC_AUTH_PASSWORD=TuPasswordFuerte123
      - GENERIC_TIMEZONE=America/Mexico_City
      - GROQ_API_KEY=${GROQ_API_KEY}
      - PYTHONUNBUFFERED=1
      - LANGCHAIN_TRACING_V2=false
    volumes:
      - "D:/bp-analytics:/project"
      - "D:/bp-analytics/n8n_data:/home/node/.n8n"
    restart: unless-stopped

volumes:
  n8n_data:
⚠️ Nota: define todas las credenciales y API Keys en un archivo .env (no se sube al repo).

🧱 Instalación Rápida
bash
Copiar código
# 1️⃣ Clonar el proyecto
git clone https://github.com/FranciscoRecendiz/be-pharma-robot.git
cd bp-analytics

# 2️⃣ Configurar entorno
cp .env.example .env
# (Agrega tu GROQ_API_KEY y credenciales n8n)

# 3️⃣ Construir e iniciar
docker compose up -d --build

# 4️⃣ Verificar contenedor
docker ps
Luego:

bash
Copiar código
docker exec -it n8n-bepharma bash
🔄 Flujo General de Ejecución
<details> <summary>Ver descripción del pipeline completo</summary>
1️⃣ Descubrimiento de empresas
bash
Copiar código
docker exec -it n8n-bepharma python3 -m src.pipelines.find_companies_daily \
  --country "México" \
  --model "llama-3.3-70b-versatile" \
  --daily-limit-combos 100 \
  --batch-size 10 \
  --ddg-max 20
Salida:

swift
Copiar código
/data/processed/mexico/empresas_raw.csv
/data/logs/mexico/daily_token_usage.json
2️⃣ Resolución de sitios
bash
Copiar código
docker exec -it n8n-bepharma python3 -m src.pipelines.resolve_sites_post
Salida:

swift
Copiar código
/data/processed/mexico/empresas_final.csv
3️⃣ Extracción de contactos (en desarrollo)
extract_contacts_from_sites.py → buscará e-mails y cargos de decisión.

</details>
🧩 Orquestación con n8n
Paso	Acción	Frecuencia
1	Trigger programado	Cada 12 h
2	Ejecuta find_companies_daily.py	Bash Node
3	Espera 5 min	Wait Node
4	Ejecuta resolve_sites_post.py	Bash Node
5	Envía resumen (Slack / Email)	Notifier Node

📄 Resumen diario generado:

Nuevas empresas detectadas

Sitios verificados

Tokens usados (Groq)

% de duplicados

📊 Métricas de Control
Indicador	Fuente	Meta
Repetición de empresas	registry	≤ 5 %
Sitios web verificados	empresas_final.csv	≥ 90 %
Tokens diarios Groq	logs	≤ 80 % del límite
Empresas nuevas / corrida	processed	100–200

🧭 Roadmap Técnico
Versión	Objetivo	Estado
v2.0	Descubrimiento + validación de sitios	✅
v2.1	Extracción de contactos + clasificador BD	🟡
v2.2	Dashboard Metabase / Grafana	🟡
v2.3	Registry SQLite + queries por fecha	🕓
v3.0	Integración CRM_EMPRESAS + scoring avanzado	🚧

🔒 Seguridad y Buenas Prácticas
🔑 Ninguna API key se guarda en logs.

🧱 .gitignore protege carpetas sensibles (data/, CRM_EMPRESAS/, models/, .env, etc.).

🐋 Configuración de n8n persistente en n8n_data/.

🔁 Los datos se deduplican automáticamente y se almacenan por país.

👥 Equipo Responsable
BePharma — Área Data & IA

Desarrollo y Arquitectura: Francisco Recendiz

Actualización: Noviembre 2025

<p align="center"> <b>BePharma Analytics</b> — Inteligencia de mercado farmacéutica impulsada por IA.<br> <i>"Transformando datos en alianzas estratégicas."</i> </p> ``