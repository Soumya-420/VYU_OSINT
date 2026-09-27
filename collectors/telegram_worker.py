import logging
import re
import requests
from typing import List, Dict, Any

logger = logging.getLogger("vyu.collectors.telegram")

PUBLIC_TELEGRAM_CHANNELS = [
    {"name": "OSINT Technical Feed", "channel": "osint_feed"},
    {"name": "Global Conflict Watch", "channel": "conflict_intel"},
    {"name": "Geopolitics Stream", "channel": "geopolitics_stream"}
]

class TelegramWorker:
    """Telegram Public Web Preview Collector (100% REAL LIVE TELEGRAM FEEDS)."""

    def __init__(self, pipeline=None):
        self.pipeline = pipeline

    def fetch_channel_messages(self) -> List[Dict[str, Any]]:
        logger.info("Ingesting REAL LIVE Telegram public channel feeds...")
        captured_docs = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        for ch in PUBLIC_TELEGRAM_CHANNELS:
            channel_name = ch["name"]
            channel_id = ch["channel"]
            url = f"https://t.me/s/{channel_id}"

            try:
                resp = requests.get(url, timeout=6, headers=headers)
                if resp.status_code == 200:
                    html = resp.text
                    messages = re.findall(r'<div class="tgme_widget_message_text[^">]*">(.*?)</div>', html, re.DOTALL)
                    
                    for i, msg_html in enumerate(messages[:3], 1):
                        clean_text = re.sub(r'<[^>]+>', ' ', msg_html).strip()
                        if len(clean_text) < 15:
                            continue
                        
                        title = f"Telegram [{channel_name}]: {clean_text[:70]}..."
                        full_text = (
                            f"REAL TELEGRAM PUBLIC CHANNEL CAPTURE\n"
                            f"Channel Name: {channel_name} (@{channel_id})\n"
                            f"Source URL: {url}\n"
                            f"--------------------------------------------------\n"
                            f"{clean_text}\n"
                            f"--------------------------------------------------\n"
                            f"Payload captured live from Telegram web preview channel."
                        )

                        item = {
                            "feed_type": "telegram",
                            "title": title,
                            "summary": clean_text[:250] + "..." if len(clean_text) > 250 else clean_text,
                            "full_text": full_text,
                            "url": f"{url}/{i}",
                            "location_name": f"Telegram @{channel_id}"
                        }

                        if self.pipeline:
                            captured_docs.append(self.pipeline.process_raw_item(item))
                        else:
                            captured_docs.append(item)
            except Exception as e:
                logger.warning(f"Error fetching live Telegram channel @{channel_id}: {e}")

        return captured_docs
