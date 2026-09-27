import logging
import requests
from typing import List, Dict, Any

logger = logging.getLogger("vyu.collectors.gdelt")

class GDELTWorker:
    """15-minute cycle Live GDELT Conflict Event Stream Collector (100% REAL LIVE DATA ONLY)."""

    def __init__(self, pipeline=None):
        self.pipeline = pipeline

    def fetch_events(self) -> List[Dict[str, Any]]:
        logger.info("Fetching LIVE GDELT 2.0 Global Conflict Event API...")
        captured_docs = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        url = "https://api.gdeltproject.org/api/v2/doc/doc?query=conflict%20OR%20security%20OR%20defense&mode=artlist&maxrecords=5&format=json"

        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                articles = data.get("articles", [])
                for art in articles:
                    title = art.get("title", "GDELT Live Conflict Signal").strip()
                    art_url = art.get("url", "#")
                    domain = art.get("domain", "GDELT Stream")
                    seendate = art.get("seendate", "")
                    country = art.get("sourcecountry", "Global")

                    full_text = (
                        f"REAL GDELT 2.0 LIVE CONFLICT TELEMETRY\n"
                        f"Article Title: {title}\n"
                        f"Domain Source: {domain} (Country Code: {country})\n"
                        f"Source URL: {art_url}\n"
                        f"Captured Date: {seendate}\n"
                        f"--------------------------------------------------\n"
                        f"Live GDELT Global Knowledge Graph conflict event signal indexed directly from real-time news stream."
                    )

                    doc_item = {
                        "feed_type": "gdelt",
                        "title": f"GDELT Signal: {title}",
                        "summary": f"GDELT 2.0 Conflict Stream captured live article from {domain} ({country}). Title: {title}",
                        "full_text": full_text,
                        "url": art_url,
                        "location_name": f"{country} Sector",
                        "published_at": seendate
                    }

                    if self.pipeline:
                        captured_docs.append(self.pipeline.process_raw_item(doc_item))
                    else:
                        captured_docs.append(doc_item)
        except Exception as e:
            logger.warning(f"Error fetching live GDELT API: {e}")

        return captured_docs
