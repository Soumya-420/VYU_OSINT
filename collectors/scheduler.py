import time
import threading
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("vyu.scheduler")


class BackgroundCollectorScheduler:
    """
    Continuous Background Collector Scheduler.
    Every interval_seconds, polls:
    - Live RSS Feeds
    - Live GDELT Conflict Stream API
    - Live NASA EONET & GDACS Hazards
    - Live Open-Meteo Weather Watchpoints
    - Live Telegram & Twitter OSINT Feeds
    - ALL User Personal Trackers (cities, topics, custom RSS)
    """

    def __init__(
        self,
        rss_worker,
        gdelt_worker,
        hazard_worker,
        weather_worker,
        telegram_worker,
        twitter_worker,
        personal_worker=None,
        personal_sources_ref: Optional[List[Dict[str, Any]]] = None,
        interval_seconds: int = 45
    ):
        self.rss_worker = rss_worker
        self.gdelt_worker = gdelt_worker
        self.hazard_worker = hazard_worker
        self.weather_worker = weather_worker
        self.telegram_worker = telegram_worker
        self.twitter_worker = twitter_worker
        self.personal_worker = personal_worker
        # Keep a live reference to the list — mutations are visible here
        self.personal_sources_ref = personal_sources_ref if personal_sources_ref is not None else []
        self.interval = interval_seconds
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info(f"Background Continuous Collector Scheduler started (polling every {self.interval}s).")

    def stop(self):
        self.running = False

    def _run_loop(self):
        while self.running:
            try:
                logger.info("Executing continuous background live data collection cycle...")

                # Standard workers
                self.rss_worker.fetch_feeds()
                self.gdelt_worker.fetch_events()
                self.hazard_worker.fetch_hazards()
                self.weather_worker.fetch_weather()
                self.telegram_worker.fetch_channel_messages()
                self.twitter_worker.fetch_tweets()

                # Personal trackers — polls ALL registered trackers every cycle
                if self.personal_worker and self.personal_sources_ref:
                    n = len(self.personal_sources_ref)
                    logger.info(f"Polling {n} personal tracker(s) for live updates...")
                    docs = self.personal_worker.collect_all(self.personal_sources_ref)
                    logger.info(f"Personal trackers collected {len(docs)} new documents this cycle.")

            except Exception as e:
                logger.error(f"Error in background collector loop: {e}", exc_info=True)

            time.sleep(self.interval)
