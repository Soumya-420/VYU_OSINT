import pytest
from fastapi.testclient import TestClient
from api.main import app, pipeline, rag_engine
from collectors.rss_worker import RSSWorker
from collectors.gdelt_worker import GDELTWorker
from collectors.hazard_worker import HazardWorker
from collectors.weather_worker import WeatherWorker

client = TestClient(app)

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "ask_vyu_engine" in data["components"]


def test_live_document_capture_and_prediction():
    payload = {
        "title": "Unidentified Drone Reconnaissance Near Strategic Offshore Platform",
        "feed_type": "custom",
        "location_name": "North Sea Sector 4",
        "url": "https://vyu.internal/alerts/drone-recon-09",
        "full_text": "Naval watch command reported multiple unidentified autonomous aerial systems hovering near offshore energy platform Bravo-3. Defense countermeasures deployed; emergency security radius expanded."
    }

    response = client.post("/api/v1/evidence/capture", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "captured_document" in data
    doc = data["captured_document"]
    
    # Verify live document full text capture
    assert doc["title"] == payload["title"]
    assert doc["full_text"] == payload["full_text"]
    
    # Verify live predictions on captured document
    pred = doc["prediction"]
    assert "threat_level" in pred
    assert pred["threat_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert "escalation_probability" in pred
    assert 0.0 <= pred["escalation_probability"] <= 1.0
    assert "predicted_impact" in pred
    assert len(pred["forecast_scenarios"]) > 0


def test_ask_vyu_v2_rag_full_text_search():
    query_payload = {"query": "What security alerts occurred regarding SCADA grid vulnerabilities?"}
    response = client.post("/api/v1/ask", json=query_payload)
    assert response.status_code == 200
    data = response.json()
    
    assert "answer" in data
    assert "cited_sources" in data
    assert data["full_text_indexed"] is True
    assert data["searched_documents_count"] > 0


def test_collection_workers():
    r_worker = RSSWorker(pipeline)
    g_worker = GDELTWorker(pipeline)
    h_worker = HazardWorker(pipeline)
    w_worker = WeatherWorker(pipeline)

    rss_docs = r_worker.fetch_feeds()
    gdelt_docs = g_worker.fetch_events()
    hazard_docs = h_worker.fetch_hazards()
    weather_docs = w_worker.fetch_weather()

    assert len(rss_docs) > 0
    assert len(gdelt_docs) > 0
    assert len(hazard_docs) > 0
    assert len(weather_docs) > 0


def test_get_evidence_endpoint():
    response = client.get("/api/v1/evidence")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data
    assert data["count"] > 0
