import os
import logging
import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, Body, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncpg
import asyncio

from pipeline.evidence_pipeline import EvidencePipeline
from llm.rag_engine import AskVYURAGEngine
from collectors.rss_worker import RSSWorker
from collectors.gdelt_worker import GDELTWorker
from collectors.hazard_worker import HazardWorker
from collectors.weather_worker import WeatherWorker
from collectors.telegram_worker import TelegramWorker
from collectors.twitter_worker import TwitterWorker
from collectors.personal_worker import PersonalTrackerWorker
from collectors.scheduler import BackgroundCollectorScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vyu.api")

# ── Admin Secret Key (set VYU_ADMIN_KEY in your .env / environment) ──────────
# This key protects the hidden visitor log endpoint.  Never expose it publicly.
ADMIN_SECRET_KEY: str = os.environ.get("VYU_ADMIN_KEY", "changeme-set-in-dotenv")

# PostgreSQL Database Connection URL
# Uses docker-compose defaults if not provided in environment
DB_URL = os.environ.get(
    "DATABASE_URL", 
    "postgresql://vyu_admin:securepassword123@vyu-postgres:5432/vyu_evidence"
)

app = FastAPI(
    title="VYU — Continuous OSINT & Personal Intelligence Platform API",
    description="Backend service for VYU OSINT evidence store, full-text Ask VYU LLM RAG engine, personal source trackers, and continuous live data collection.",
    version="2.2.0"
)

# Enable CORS for Analyst Interface Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.on_event("startup")
async def startup_db_pool():
    try:
        app.state.db_pool = await asyncpg.create_pool(DB_URL)
        async with app.state.db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS visitor_logs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    ip_address VARCHAR(64) NOT NULL,
                    method VARCHAR(10),
                    path TEXT,
                    user_agent TEXT,
                    referer TEXT,
                    country_hint VARCHAR(4),
                    visited_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_visitor_logs_ip ON visitor_logs(ip_address);
                CREATE INDEX IF NOT EXISTS idx_visitor_logs_time ON visitor_logs(visited_at DESC);
            """)
        logger.info("Connected to PostgreSQL Database for Permanent Logging (Table Verified).")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        app.state.db_pool = None

@app.on_event("shutdown")
async def shutdown_db_pool():
    if getattr(app.state, "db_pool", None):
        await app.state.db_pool.close()

# ── Silent Visitor IP Capture Middleware ──────────────────────────────────────
# Runs on every request but is invisible to the frontend.
@app.middleware("http")
async def _capture_visitor_ip(request: Request, call_next):
    skip_paths = ("/favicon.ico", "/robots.txt")
    if request.method != "OPTIONS" and not request.url.path.startswith("/static"):
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        if request.url.path not in skip_paths:
            # Run the insert asynchronously without blocking the request
            if getattr(request.app.state, "db_pool", None):
                try:
                    async with request.app.state.db_pool.acquire() as conn:
                        await conn.execute(
                            """
                            INSERT INTO visitor_logs (ip_address, method, path, user_agent, referer)
                            VALUES ($1, $2, $3, $4, $5)
                            """,
                            ip,
                            request.method,
                            request.url.path,
                            request.headers.get("user-agent", ""),
                            request.headers.get("referer", "")
                        )
                except Exception as e:
                    logger.error(f"Failed to save visitor log to DB: {e}")

    response = await call_next(request)
    return response

# Global pipeline and RAG instances
pipeline = EvidencePipeline()
rag_engine = AskVYURAGEngine()

# Collection Workers
rss_worker = RSSWorker(pipeline)
gdelt_worker = GDELTWorker(pipeline)
hazard_worker = HazardWorker(pipeline)
weather_worker = WeatherWorker(pipeline)
telegram_worker = TelegramWorker(pipeline)
twitter_worker = TwitterWorker(pipeline)
personal_worker = PersonalTrackerWorker(pipeline)

# In-memory User Personal Sources Registry
user_personal_sources: List[Dict[str, Any]] = []

# Start Continuous Background Collector Loop (every 45 seconds)
scheduler = BackgroundCollectorScheduler(
    rss_worker, gdelt_worker, hazard_worker, weather_worker,
    telegram_worker, twitter_worker,
    personal_worker=personal_worker,
    personal_sources_ref=user_personal_sources,
    interval_seconds=45
)

@app.on_event("startup")
def on_startup():
    logger.info("Initializing VYU OSINT application and starting background continuous scheduler...")
    # Fetch initial cycle
    rss_worker.fetch_feeds()
    gdelt_worker.fetch_events()
    hazard_worker.fetch_hazards()
    weather_worker.fetch_weather()
    telegram_worker.fetch_channel_messages()
    twitter_worker.fetch_tweets()
    # Start background polling
    scheduler.start()


# ── Request Models ──────────────────────────────────────────────────────────

class AskQueryRequest(BaseModel):
    query: str


class DocumentCaptureRequest(BaseModel):
    title: str
    full_text: str
    feed_type: str = "custom"
    url: Optional[str] = None
    summary: Optional[str] = None
    location_name: Optional[str] = "Specified Region"


class PersonalSourceAddRequest(BaseModel):
    name: str
    source_type: str = "topic"  # topic, rss
    url_or_query: str


# ── API Endpoints ───────────────────────────────────────────────────────────

@app.get("/api/v1/health")
def get_health():
    """Returns operational architecture health metrics."""
    return {
        "status": "healthy",
        "system": "VYU Continuous OSINT & Personal Intelligence Engine v2.2",
        "background_collector": "ACTIVE (Continuous 45s Polling Loop)",
        "total_indexed_documents": len(pipeline.get_all_documents()),
        "user_personal_trackers": len(user_personal_sources),
        "components": {
            "collectors": {
                "rss_worker": "ACTIVE",
                "gdelt_worker": "ACTIVE",
                "hazard_worker": "ACTIVE",
                "weather_worker": "ACTIVE",
                "telegram_worker": "ACTIVE",
                "x_twitter_worker": "ACTIVE",
                "personal_tracker_worker": f"ACTIVE ({len(user_personal_sources)} trackers)"
            },
            "ask_vyu_engine": "v2.2 (Multi-provider geocoding + Live document prediction)"
        }
    }


@app.get("/api/v1/evidence")
def get_evidence_documents(feed_type: Optional[str] = None):
    """Retrieves all captured live documents along with their live predictions."""
    docs = pipeline.get_all_documents()
    if feed_type:
        docs = [d for d in docs if d.get("feed_type") == feed_type.lower()]
    return {
        "count": len(docs),
        "documents": docs
    }


@app.post("/api/v1/evidence/capture")
def capture_live_document(payload: DocumentCaptureRequest):
    """Captures a live document and immediately generates AI risk predictions on it."""
    doc_item = {
        "feed_type": payload.feed_type,
        "title": payload.title,
        "summary": payload.summary or (payload.full_text[:250] + "..."),
        "full_text": payload.full_text,
        "url": payload.url,
        "location_name": payload.location_name
    }
    processed = pipeline.process_raw_item(doc_item)
    return {
        "message": "Live document successfully captured and predicted.",
        "captured_document": processed
    }


@app.post("/api/v1/ask")
def ask_vyu(request: AskQueryRequest):
    """
    Ask VYU v2.0 LLM RAG Query Endpoint.
    Searches full text, retrieves live prediction context, and outputs cited sources.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query string cannot be empty.")

    docs = pipeline.get_all_documents()
    result = rag_engine.query(user_query=request.query, evidence_docs=docs, pipeline=pipeline)
    return result


@app.get("/api/v1/sources/user")
def get_user_personal_sources():
    """Retrieves all personal sources added by the user."""
    return {
        "count": len(user_personal_sources),
        "sources": user_personal_sources
    }


@app.post("/api/v1/sources/user")
def add_user_personal_source(payload: PersonalSourceAddRequest):
    """
    Allows any user to add their personal RSS feed, city/location watchpoint,
    or topic to continuously track. Immediately fetches live data and returns it.
    """
    # Avoid duplicate trackers
    for existing in user_personal_sources:
        if existing["url_or_query"].lower() == payload.url_or_query.lower():
            return {
                "message": f"Tracker '{payload.name}' already exists.",
                "source": existing,
                "captured_documents": []
            }

    source_entry = {
        "id": f"user-src-{len(user_personal_sources) + 1}",
        "name": payload.name,
        "source_type": payload.source_type,
        "url_or_query": payload.url_or_query,
        "added_at": "Just Now"
    }
    user_personal_sources.append(source_entry)

    # Immediately fetch live data for the new tracker
    captured = personal_worker.collect_for_tracker(source_entry)
    logger.info(f"Personal tracker '{payload.name}' added. Captured {len(captured)} live documents immediately.")

    return {
        "message": f"Personal tracker '{payload.name}' added! {len(captured)} live documents captured immediately.",
        "source": source_entry,
        "captured_documents": captured
    }


@app.delete("/api/v1/sources/user/{source_id}")
def remove_user_personal_source(source_id: str):
    """Remove a personal tracker by its ID."""
    global user_personal_sources
    before = len(user_personal_sources)
    user_personal_sources = [s for s in user_personal_sources if s["id"] != source_id]
    if len(user_personal_sources) < before:
        return {"message": f"Tracker '{source_id}' removed."}
    raise HTTPException(status_code=404, detail="Tracker not found.")


@app.post("/api/v1/collect")
def trigger_collection_cycle():
    """Triggers an instant collection cycle across all active workers including personal trackers."""
    d1 = rss_worker.fetch_feeds()
    d2 = gdelt_worker.fetch_events()
    d3 = hazard_worker.fetch_hazards()
    d4 = weather_worker.fetch_weather()
    d5 = telegram_worker.fetch_channel_messages()
    d6 = twitter_worker.fetch_tweets()
    d7 = personal_worker.collect_all(user_personal_sources)

    total_new = len(d1) + len(d2) + len(d3) + len(d4) + len(d5) + len(d6) + len(d7)
    return {
        "status": "success",
        "collected_documents_count": total_new,
        "personal_tracker_documents": len(d7),
        "total_indexed_documents": len(pipeline.get_all_documents())
    }


# ── Hidden Admin: Visitor IP Log (NOT in public API docs) ────────────────────
# Access:  GET /api/v1/admin/visitors
# Header:  X-Admin-Key: <your VYU_ADMIN_KEY value>
# Returns: Full IP access log sorted newest-first.
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/admin/visitors", include_in_schema=False)
async def get_visitor_log(
    request: Request,
    x_admin_key: Optional[str] = Header(default=None),
    limit: int = Query(default=200, le=5000),
    ip_filter: Optional[str] = Query(default=None),
):
    """
    Hidden admin endpoint — returns captured visitor IP log from Permanent PostgreSQL DB.
    Requires X-Admin-Key header matching VYU_ADMIN_KEY env variable.
    Not visible in /docs or /redoc.
    """
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden.")

    if not getattr(request.app.state, "db_pool", None):
        return {"error": "Database not connected. Logs are unavailable."}
        
    async with request.app.state.db_pool.acquire() as conn:
        if ip_filter:
            records = await conn.fetch(
                "SELECT * FROM visitor_logs WHERE ip_address = $1 ORDER BY visited_at DESC LIMIT $2",
                ip_filter, limit
            )
        else:
            records = await conn.fetch(
                "SELECT * FROM visitor_logs ORDER BY visited_at DESC LIMIT $1",
                limit
            )
            
        total_captured = await conn.fetchval("SELECT COUNT(*) FROM visitor_logs")

    logs = [dict(r) for r in records]
    # Convert datetime objects to string for JSON serialization
    for log in logs:
        if "visited_at" in log and log["visited_at"]:
            log["visited_at"] = log["visited_at"].isoformat()

    return {
        "total_captured": total_captured,
        "returned": len(logs),
        "visitor_log": logs,
    }


@app.delete("/api/v1/admin/visitors", include_in_schema=False)
async def clear_visitor_log(request: Request, x_admin_key: Optional[str] = Header(default=None)):
    """Clears the permanent visitor log from PostgreSQL. Requires admin key."""
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden.")
        
    if not getattr(request.app.state, "db_pool", None):
        return {"error": "Database not connected."}

    async with request.app.state.db_pool.acquire() as conn:
        count = await conn.execute("DELETE FROM visitor_logs")
        
    return {"message": f"Visitor log cleared from database. {count.replace('DELETE ', '')} entries removed."}


# Mount frontend static files to root (must be after all API routes)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
