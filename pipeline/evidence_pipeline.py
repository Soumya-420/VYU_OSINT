import logging
import hashlib
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from llm.provider import get_llm_provider

logger = logging.getLogger("vyu.pipeline")

class EvidencePipeline:
    """
    4-Stage Evidence Pipeline for VYU with Strict Deduplication:
    1. Ingest: Raw evidence payload collection & canonical hash deduplication
    2. Normalise: Clean text, strip tags, extract canonical URL
    3. Enrich: Dynamic LLM NER entity extraction, PostGIS geotagging, unique AI risk prediction
    4. Index: Full article text storage, vector embedding, unique evidence store index
    """

    def __init__(self):
        self.llm = get_llm_provider()
        self.in_memory_store: List[Dict[str, Any]] = []
        self.seen_urls: Set[str] = set()
        self.seen_titles: Set[str] = set()

    def process_raw_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Executes complete 4-stage pipeline with strict deduplication.
        If title or URL already processed, returns existing record without duplicating.
        """
        title = item.get("title", "Untitled Live Capture").strip()
        url = item.get("url") or f"https://vyu.internal/doc/{hashlib.md5(title.encode()).hexdigest()[:10]}"
        
        # Deduplication Check
        norm_title = re.sub(r'[^a-zA-Z0-9]', '', title).lower()
        if url in self.seen_urls or (norm_title and norm_title in self.seen_titles):
            # Find existing doc
            for d in self.in_memory_store:
                if d.get("url") == url or re.sub(r'[^a-zA-Z0-9]', '', d.get("title", "")).lower() == norm_title:
                    return d
            return None

        raw_text = item.get("full_text") or item.get("summary") or title
        feed_type = item.get("feed_type", "rss")

        # Stage 1: Ingest
        raw_s3_key = f"evidence/raw/{feed_type}/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(url.encode()).hexdigest()[:8]}.json"
        
        # Stage 2: Normalise
        cleaned_text = self._clean_text(raw_text)
        summary = item.get("summary") or (cleaned_text[:250] + "...")

        # Stage 3: Enrich & Predict (Generate Unique Live Document Prediction using LLM)
        prediction = self.llm.predict_document_risk(cleaned_text, title)

        loc_name = item.get("location_name", "")
        if not loc_name or "Global" in loc_name or "Watchpoint" in loc_name:
            loc_name = self._extract_location(title + " " + cleaned_text[:500]) or "Global"

        # Stage 4: Index Unique Document
        document_record = {
            "id": f"doc-{len(self.in_memory_store) + 1}",
            "feed_type": feed_type,
            "title": title,
            "summary": summary,
            "full_text": cleaned_text,
            "url": url,
            "s3_raw_key": raw_s3_key,
            "location_name": loc_name,
            "published_at": item.get("published_at") or datetime.utcnow().isoformat(),
            "ingested_at": datetime.utcnow().isoformat(),
            "prediction": prediction
        }

        self.seen_urls.add(url)
        if norm_title:
            self.seen_titles.add(norm_title)
            
        self.in_memory_store.append(document_record)
        logger.info(f"Successfully processed UNIQUE live document '{title}' (Total Unique: {len(self.in_memory_store)})")
        return document_record

    def get_all_documents(self) -> List[Dict[str, Any]]:
        return self.in_memory_store

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        clean = re.sub(r'<[^>]+>', '', text)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()

    def _extract_location(self, text: str) -> Optional[str]:
        """Extract the most prominent location from document text."""
        # Ordered priority list: more specific wins
        known_locations = [
            # Specific geopolitical hotspots first
            "Strait of Hormuz", "Gaza Strip", "West Bank", "South China Sea",
            "Korean Peninsula", "Taiwan Strait",
            # Countries
            "Ukraine", "Russia", "Israel", "Iran", "China", "North Korea",
            "Pakistan", "Afghanistan", "Syria", "Lebanon", "Yemen", "Sudan",
            "Myanmar", "Ethiopia", "Haiti", "Venezuela", "Cuba",
            "United States", "United Kingdom", "Germany", "France", "India",
            "Japan", "South Korea", "Australia", "Canada", "Brazil",
            "Turkey", "Saudi Arabia", "Egypt", "Nigeria", "Kenya", "Indonesia",
            # Major cities
            "Washington", "London", "Moscow", "Beijing", "Tel Aviv", "Kyiv",
            "Tehran", "Kabul", "Baghdad", "Damascus", "Beirut", "Sanaa",
            "New Delhi", "Mumbai", "Kolkata", "Dhaka", "Karachi",
            "Tokyo", "Seoul", "Taipei", "Hong Kong",
            "Paris", "Berlin", "Rome", "Brussels", "Geneva", "Vienna",
            "New York", "Los Angeles", "Chicago",
            "Ankara", "Cairo", "Riyadh", "Dubai", "Islamabad",
            "Nairobi", "Lagos", "Pretoria", "Addis Ababa",
        ]
        for loc in known_locations:
            if re.search(r'\b' + re.escape(loc) + r'\b', text, re.IGNORECASE):
                return loc
        return None
