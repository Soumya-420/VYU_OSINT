import logging
import feedparser
import requests
import re
from typing import List, Dict, Any

logger = logging.getLogger("vyu.collectors.rss")

LIVE_RSS_FEEDS = [
    {"name": "BBC World News", "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Al Jazeera English", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "Google World News", "url": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"},
    {"name": "CISA Cyber Alerts", "url": "https://www.cisa.gov/uscert/ncas/alerts.xml"}
]

class RSSWorker:
    """5-minute cycle Live RSS Collection Worker (100% REAL LIVE DATA ONLY)."""

    def __init__(self, pipeline=None):
        self.pipeline = pipeline

    def fetch_feeds(self, feeds: List[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        target_feeds = feeds or LIVE_RSS_FEEDS
        captured_docs = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        for feed in target_feeds:
            feed_name = feed["name"]
            feed_url = feed["url"]
            try:
                logger.info(f"Fetching LIVE RSS feed: {feed_name} ({feed_url})")
                resp = requests.get(feed_url, headers=headers, timeout=8)
                if resp.status_code == 200:
                    parsed = feedparser.parse(resp.content)
                    entries = parsed.entries[:5] if parsed.entries else []
                    
                    for entry in entries:
                        title = getattr(entry, "title", "Untitled Feed Item").strip()
                        raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
                        clean_summary = re.sub(r'<[^>]+>', ' ', raw_summary).strip()
                        link = getattr(entry, "link", "#")
                        pub_date = getattr(entry, "published", "")

                        full_article = f"REAL LIVE RSS NEWS CAPTURE ({feed_name.upper()})\nTitle: {title}\nPublished Date: {pub_date}\nSource URL: {link}\n\nClean Summary Content:\n{clean_summary}\n\nPayload ingested directly from live internet RSS feed."

                        doc_item = {
                            "feed_type": "rss",
                            "title": title,
                            "summary": clean_summary[:250] + "..." if len(clean_summary) > 250 else clean_summary,
                            "full_text": full_article,
                            "url": link,
                            "published_at": pub_date,
                            "location_name": f"{feed_name} Global Stream"
                        }

                        if self.pipeline:
                            processed = self.pipeline.process_raw_item(doc_item)
                            captured_docs.append(processed)
                        else:
                            captured_docs.append(doc_item)
            except Exception as e:
                logger.warning(f"Error fetching live RSS feed {feed_name}: {e}")

        return captured_docs
