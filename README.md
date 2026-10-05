# VYU — Continuous OSINT & Personal Intelligence Platform

<div align="center">

![VYU OSINT](https://img.shields.io/badge/VYU-OSINT%20Platform-blue?style=for-the-badge&logo=satellite&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-green?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Status](https://img.shields.io/badge/Status-🔴%20LIVE-red?style=for-the-badge)

**🌐 Live Demo → [vyu-production.up.railway.app](https://vyu-production.up.railway.app/)**

</div>

---

## What is VYU?

VYU is a 24/7 autonomous **Open Source Intelligence (OSINT) platform** that continuously ingests global news, conflict streams, natural hazard alerts, real-time weather data, and social signals — then surfaces everything through a live analyst dashboard with an AI-powered RAG chatbot.

No manual refreshes. No static data. Everything is live.

---

## Features

### Live Data Collectors (45-second polling loop)
- **RSS Worker** — BBC World, Al Jazeera, Google News, CISA Cyber Alerts
- **GDELT Worker** — Real-time GDELT 2.0 global conflict event stream
- **Hazard Worker** — GDACS & NASA EONET natural disaster alerts
- **Weather Worker** — Open-Meteo satellite weather for tracked locations
- **Twitter/X Worker** — Trending signals and keyword tracking
- **Telegram Worker** — Public channel intelligence collection
- **Personal Tracker** — Add any city, topic, or RSS URL to track live

### Ask VYU — RAG Intelligence Chatbot
- Answers questions using exclusively real-time collected data
- Multi-provider geocoding (Open-Meteo + Nominatim/OSM) for any place on Earth
- Fetches live weather and news on-demand per query
- Cites all sources with threat level and escalation probability

### Evidence Pipeline (4-Stage)
1. **Ingest** — Deduplication by URL and title hash
2. **Normalise** — HTML stripping, text cleaning
3. **Enrich** — LLM-driven NER entity extraction, AI risk prediction, geolocation
4. **Index** — Full-text in-memory store with vector-ready structure

### Analyst Dashboard
- Live geospatial intelligence map (Leaflet.js)
- Document inspection panel with AI threat predictions and escalation index
- Feed-type filters (RSS, GDELT, Hazards, Weather, X/Twitter, Personal)
- Instant collection trigger and manual document capture

### Infrastructure
- PostgreSQL 16 + PostGIS for permanent evidence and visitor log storage
- Redis for cache and worker coordination
- MinIO for report artifact S3 storage
- Nginx reverse proxy for frontend serving
- Admin endpoint with IP-level visitor logging (hidden, key-protected)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI 0.111 + Uvicorn |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| Cache | Redis (Alpine) |
| Object Storage | MinIO |
| Frontend | Vanilla JS + Leaflet.js |
| Reverse Proxy | Nginx |
| Containerisation | Docker + Docker Compose |
| Deployment | Railway / Self-hosted |

---

## Quick Start

### Prerequisites
- Docker and Docker Compose installed
- (Optional) `.env` file for secrets

### 1. Clone the repository

```bash
git clone https://github.com/your-username/vyu.git
cd vyu
```

### 2. Configure environment

Key variables:

```env
DATABASE_URL=postgresql://vyu_admin:yourpassword@vyu-postgres:5432/vyu_evidence
DB_PASSWORD=yourpassword
MINIO_PASSWORD=yourminiopassword
VYU_ADMIN_KEY=your-secret-admin-key
```

### 3. Start with Docker Compose

```bash
docker-compose up --build
```

Services start on:
- Frontend: `http://localhost:8080`
- Backend API: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`

### 4. Run locally (without Docker)

```bash
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## API Reference

All endpoints are prefixed with `/api/v1`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | System health and collector status |
| `GET` | `/evidence` | All indexed documents (filterable by `feed_type`) |
| `POST` | `/evidence/capture` | Manually capture a document with AI prediction |
| `POST` | `/ask` | Ask VYU AI chatbot (RAG query) |
| `GET` | `/sources/user` | List personal trackers |
| `POST` | `/sources/user` | Add a personal tracker |
| `DELETE` | `/sources/user/{id}` | Remove a personal tracker |
| `POST` | `/collect` | Trigger an instant collection cycle |
| `GET` | `/admin/visitors` | View visitor IP log (admin key required) |

Interactive docs available at `/docs` (Swagger UI) and `/redoc`.

---

## Deployment

### Railway

The `railway.json` is pre-configured with Nixpacks builder and auto-restart on failure.

### Self-hosted (Linux systemd)

A `vyu.service` systemd unit file is included. Copy it to `/etc/systemd/system/` and enable:

```bash
sudo systemctl enable vyu
sudo systemctl start vyu
```

---

## Project Structure

```
vyu/
├── api/
│   └── main.py               # FastAPI application, routes, middleware
├── collectors/
│   ├── rss_worker.py         # RSS feed collector
│   ├── gdelt_worker.py       # GDELT 2.0 conflict stream
│   ├── hazard_worker.py      # GDACS + EONET hazard alerts
│   ├── weather_worker.py     # Open-Meteo weather collector
│   ├── telegram_worker.py    # Telegram channel collector
│   ├── twitter_worker.py     # X/Twitter signals
│   ├── personal_worker.py    # User-defined topic/RSS trackers
│   └── scheduler.py          # Background 45s polling loop
├── pipeline/
│   └── evidence_pipeline.py  # 4-stage ingest → normalise → enrich → index
├── llm/
│   ├── provider.py           # LLM provider abstraction
│   └── rag_engine.py         # Ask VYU RAG engine + geocoding
├── frontend/
│   ├── index.html            # Analyst dashboard
│   ├── app.js                # Dashboard logic
│   └── styles.css            # UI styles
├── docker/
│   ├── nginx/nginx.conf      # Nginx reverse proxy config
│   └── postgres/init.sql     # DB schema initialisation
├── tests/
│   └── test_system.py        # System tests
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
├── render.yaml               # Render deployment config
├── railway.json              # Railway deployment config
└── requirements.txt
```

---


## License

MIT License — use freely, attribution appreciated.

---

<div align="center">

Built with 🛰️ by the VYU team · **[Live Demo](vyu-production.up.railway.app)**

</div>
