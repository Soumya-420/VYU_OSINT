import logging
import requests
import feedparser
import re
from typing import List, Dict, Any

logger = logging.getLogger("vyu.collectors.twitter")

class TwitterWorker:
    """X / Twitter Real Live Trend & Curated OSINT Capture Worker."""

    def __init__(self, pipeline=None):
        self.pipeline = pipeline

    def fetch_tweets(self) -> List[Dict[str, Any]]:
        logger.info("Ingesting REAL LIVE X / Twitter OSINT feeds...")
        captured_docs = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        # Fetch real live Twitter/X posts via Google News Twitter Index & Nitter RSS
        twitter_rss_url = "https://news.google.com/rss/search?q=site:x.com+OR+site:twitter.com+OSINT+security&hl=en-US&gl=US&ceid=US:en"

        try:
            resp = requests.get(twitter_rss_url, headers=headers, timeout=6)
            if resp.status_code == 200:
                parsed = feedparser.parse(resp.content)
                for entry in parsed.entries[:4]:
                    title = getattr(entry, "title", "X / Twitter Post").strip()
                    raw_sum = getattr(entry, "summary", "") or getattr(entry, "description", "")
                    clean_sum = re.sub(r'<[^>]+>', ' ', raw_sum).strip()
                    link = getattr(entry, "link", "#")
                    pub = getattr(entry, "published", "")

                    full_text = (
                        f"REAL X / TWITTER OSINT CAPTURE\n"
                        f"Title: {title}\n"
                        f"Source URL: {link}\n"
                        f"Published Date: {pub}\n"
                        f"--------------------------------------------------\n"
                        f"{clean_sum}\n"
                        f"--------------------------------------------------\n"
                        f"Live OSINT post indexed from X/Twitter feed."
                    )

                    doc_item = {
                        "feed_type": "twitter",
                        "title": f"X/Twitter Post: {title}",
                        "summary": clean_sum[:250] + "..." if len(clean_sum) > 250 else clean_sum,
                        "full_text": full_text,
                        "url": link,
                        "location_name": "X / Twitter Network",
                        "published_at": pub
                    }

                    if self.pipeline:
                        captured_docs.append(self.pipeline.process_raw_item(doc_item))
                    else:
                        captured_docs.append(doc_item)
        except Exception as e:
            logger.warning(f"Error fetching live X/Twitter RSS feed: {e}")

        return captured_docs
