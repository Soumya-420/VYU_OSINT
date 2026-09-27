-- VYU Database Schema Initialization
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Source Registry Table
CREATE TABLE IF NOT EXISTS source_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL, -- rss, gdelt, hazard, weather, telegram, twitter, web
    url VARCHAR(1024),
    status VARCHAR(50) DEFAULT 'ACTIVE', -- ACTIVE, LIMITED, PENDING, DORMANT
    last_fetched_at TIMESTAMP WITH TIME ZONE,
    error_count INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Evidence Documents (Full Live Document Capture)
CREATE TABLE IF NOT EXISTS evidence_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID REFERENCES source_registry(id) ON DELETE SET NULL,
    feed_type VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    full_text TEXT NOT NULL, -- Full captured live document text
    author VARCHAR(255),
    url VARCHAR(1024) UNIQUE,
    s3_raw_key VARCHAR(512), -- MinIO object reference
    location_name VARCHAR(255),
    geom GEOMETRY(Point, 4326),
    published_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    embedding vector(384) -- pgvector embeddings for full text RAG
);

-- Predictions & AI Analytics on Live Captured Documents
CREATE TABLE IF NOT EXISTS document_predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES evidence_documents(id) ON DELETE CASCADE,
    threat_level VARCHAR(50) NOT NULL DEFAULT 'LOW', -- LOW, MEDIUM, HIGH, CRITICAL
    escalation_probability FLOAT DEFAULT 0.0,
    predicted_impact TEXT NOT NULL,
    forecast_scenarios JSONB DEFAULT '[]'::jsonb,
    explainable_tone JSONB DEFAULT '{}'::jsonb, -- Sentiment, propaganda, bias metrics
    entities_extracted JSONB DEFAULT '[]'::jsonb, -- Orgs, Persons, Locations, Weapons, Targets
    predicted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Intelligence Reports
CREATE TABLE IF NOT EXISTS intelligence_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    key_takeaways JSONB DEFAULT '[]'::jsonb,
    cited_document_ids UUID[] DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- System Audit & Provenance Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    worker_name VARCHAR(100) NOT NULL,
    action VARCHAR(100) NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    logged_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Hidden Visitor IP Access Log (admin-only, not exposed to frontend)
CREATE TABLE IF NOT EXISTS visitor_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
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

-- Indices for performance & vector search
CREATE INDEX IF NOT EXISTS idx_evidence_docs_ingested ON evidence_documents(ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_docs_feed_type ON evidence_documents(feed_type);
CREATE INDEX IF NOT EXISTS idx_evidence_docs_geom ON evidence_documents USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_predictions_doc_id ON document_predictions(document_id);
CREATE INDEX IF NOT EXISTS idx_predictions_threat ON document_predictions(threat_level);

-- Initial default sources
INSERT INTO source_registry (name, source_type, url, status) VALUES
('BBC World News', 'rss', 'http://feeds.bbci.co.uk/news/world/rss.xml', 'ACTIVE'),
('GDELT Conflict Event Stream', 'gdelt', 'https://api.gdeltproject.org/api/v2/summary/summary', 'ACTIVE'),
('GDACS Hazards Collection', 'hazard', 'https://www.gdacs.org/xml/rss.xml', 'ACTIVE'),
('NASA EONET Events', 'hazard', 'https://eonet.gsfc.nasa.gov/api/v2.1/events', 'ACTIVE'),
('Open-Meteo Watchpoints', 'weather', 'https://api.open-meteo.com/v1/forecast', 'ACTIVE'),
('Telegram Channel Collector', 'telegram', 'https://t.me/s/osint_feed', 'PENDING'),
('X / Twitter Trend Board', 'twitter', 'manual_capture', 'LIMITED')
ON CONFLICT DO NOTHING;
