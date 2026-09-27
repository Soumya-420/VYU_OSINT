import logging
import requests
import feedparser
import re
from typing import List, Dict, Any

logger = logging.getLogger("vyu.collectors.hazard")

class HazardWorker:
    """15-minute NASA EONET & GDACS Live Hazard Collector (100% REAL LIVE DATA ONLY)."""

    def __init__(self, pipeline=None):
        self.pipeline = pipeline

    def fetch_hazards(self) -> List[Dict[str, Any]]:
        logger.info("Fetching LIVE NASA EONET & GDACS hazard feeds...")
        captured_docs = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        # 1. Fetch NASA EONET Live Natural Events API
        try:
            eonet_url = "https://eonet.gsfc.nasa.gov/api/v2.1/events?limit=5"
            resp = requests.get(eonet_url, headers=headers, timeout=8)
            if resp.status_code == 200:
                events = resp.json().get("events", [])
                for ev in events:
                    title = ev.get("title", "NASA EONET Event")
                    categories = [c.get("title") for c in ev.get("categories", [])]
                    cat_str = ", ".join(categories) if categories else "Natural Hazard"
                    geometries = ev.get("geometries", [])
                    coords = geometries[0].get("coordinates") if geometries else ["Unknown"]
                    date_str = geometries[0].get("date") if geometries else ""
                    event_id = ev.get("id", "")

                    full_text = (
                        f"REAL NASA EONET SATELLITE HAZARD REPORT\n"
                        f"Event ID: {event_id}\n"
                        f"Event Title: {title}\n"
                        f"Hazard Categories: {cat_str}\n"
                        f"Geospatial Coordinates (Lon, Lat): {coords}\n"
                        f"Date Recorded: {date_str}\n"
                        f"--------------------------------------------------\n"
                        f"Satellite imagery and sensor telemetry recorded by NASA Earth Observatory Natural Event Tracker."
                    )

                    doc_item = {
                        "feed_type": "hazard",
                        "title": f"NASA EONET Hazard: {title} ({cat_str})",
                        "summary": f"NASA Earth Observatory recorded active {cat_str} hazard: {title}. Coordinates: {coords}",
                        "full_text": full_text,
                        "url": ev.get("link", f"https://eonet.gsfc.nasa.gov/api/v2.1/events/{event_id}"),
                        "location_name": f"Coordinates {coords}",
                        "published_at": date_str
                    }

                    if self.pipeline:
                        captured_docs.append(self.pipeline.process_raw_item(doc_item))
                    else:
                        captured_docs.append(doc_item)
        except Exception as e:
            logger.warning(f"Error fetching NASA EONET API: {e}")

        # 2. Fetch GDACS Live RSS Alert Feed
        try:
            gdacs_url = "https://www.gdacs.org/xml/rss.xml"
            resp = requests.get(gdacs_url, headers=headers, timeout=8)
            if resp.status_code == 200:
                parsed = feedparser.parse(resp.content)
                for entry in parsed.entries[:3]:
                    title = getattr(entry, "title", "GDACS Disaster Alert")
                    summary = re.sub(r'<[^>]+>', ' ', getattr(entry, "summary", "")).strip()
                    link = getattr(entry, "link", "https://www.gdacs.org")
                    pub = getattr(entry, "published", "")

                    doc_item = {
                        "feed_type": "hazard",
                        "title": f"GDACS Alert: {title}",
                        "summary": summary[:250] + "..." if len(summary) > 250 else summary,
                        "full_text": f"REAL GDACS DISASTER ALERT REPORT\nTitle: {title}\nPublished Date: {pub}\nSource URL: {link}\n\nClean Summary:\n{summary}",
                        "url": link,
                        "location_name": "Global GDACS Sector",
                        "published_at": pub
                    }

                    if self.pipeline:
                        captured_docs.append(self.pipeline.process_raw_item(doc_item))
                    else:
                        captured_docs.append(doc_item)
        except Exception as e:
            logger.warning(f"Error fetching GDACS RSS feed: {e}")

        return captured_docs
