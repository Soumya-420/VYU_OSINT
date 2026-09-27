import logging
import requests
import feedparser
import re
from typing import List, Dict, Any, Optional
from llm.rag_engine import _geocode_place, WEATHER_CODES

logger = logging.getLogger("vyu.collectors.personal")


class PersonalTrackerWorker:
    """
    Personal Tracker Worker.
    For each user-added tracker (city, topic, or RSS URL), this worker:
    1. Geocodes cities -> fetches real satellite weather from Open-Meteo
    2. Fetches real live news from Google News RSS for any topic/city
    3. Fetches custom RSS feed URLs directly
    All data is injected into the shared evidence pipeline.
    """

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def collect_for_tracker(self, tracker: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Collect live data for a single personal tracker entry.
        tracker = {"name": "Dankuni", "source_type": "topic", "url_or_query": "Dankuni"}
        """
        name = tracker.get("name", "Unknown")
        source_type = tracker.get("source_type", "topic")
        query = tracker.get("url_or_query", name)

        logger.info(f"Personal Tracker collecting live data for: '{name}' (type={source_type})")
        collected = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        # ── Custom RSS URL ──────────────────────────────────────────────────────
        if source_type == "rss" and query.startswith("http"):
            try:
                resp = requests.get(query, headers=headers, timeout=6)
                parsed = feedparser.parse(resp.content)
                for entry in parsed.entries[:5]:
                    title = getattr(entry, "title", "").strip()
                    if not title:
                        continue
                    raw_sum = getattr(entry, "summary", "") or getattr(entry, "description", "")
                    clean_sum = re.sub(r'<[^>]+>', ' ', raw_sum).strip()
                    link = getattr(entry, "link", query)
                    pub = getattr(entry, "published", "")
                    item = {
                        "feed_type": "personal_rss",
                        "title": f"[{name}] {title}",
                        "summary": clean_sum[:300],
                        "full_text": f"PERSONAL TRACKER: {name}\nTitle: {title}\nURL: {link}\nPublished: {pub}\n---\n{clean_sum}",
                        "url": link,
                        "location_name": name,
                        "published_at": pub
                    }
                    processed = self.pipeline.process_raw_item(item)
                    if processed:
                        collected.append(processed)
            except Exception as e:
                logger.warning(f"Personal RSS fetch failed for '{name}': {e}")
            return collected

        # ── City / Topic ────────────────────────────────────────────────────────

        # 1. Try geocoding to get real satellite weather
        geo = _geocode_place(query)
        if geo:
            lat, lon, display_name = geo
            try:
                weather_url = (
                    f"https://api.open-meteo.com/v1/forecast?"
                    f"latitude={lat}&longitude={lon}"
                    f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
                    f"precipitation,weather_code,surface_pressure,wind_speed_10m,wind_direction_10m"
                )
                wr = requests.get(weather_url, headers=headers, timeout=6)
                if wr.status_code == 200:
                    curr = wr.json().get("current", {})
                    temp = curr.get("temperature_2m", "N/A")
                    feels = curr.get("apparent_temperature", temp)
                    humidity = curr.get("relative_humidity_2m", "N/A")
                    precip = curr.get("precipitation", 0.0)
                    code = curr.get("weather_code", 0)
                    pressure = curr.get("surface_pressure", "N/A")
                    wind = curr.get("wind_speed_10m", "N/A")
                    wind_dir = curr.get("wind_direction_10m", "N/A")
                    cond = WEATHER_CODES.get(code, f"WMO Code {code}")
                    obs_time = curr.get("time", "")

                    title = f"[PERSONAL TRACKER] Live Weather: {display_name} - {temp}C, {cond}, Humidity {humidity}%"
                    full_text = (
                        f"PERSONAL TRACKER LIVE WEATHER REPORT\n"
                        f"Tracker: {name}\n"
                        f"Location: {display_name}\n"
                        f"Coordinates: {lat}N, {lon}E\n"
                        f"Observation Time: {obs_time}\n"
                        f"---\n"
                        f"Temperature: {temp}C (Feels Like: {feels}C)\n"
                        f"Humidity: {humidity}%\n"
                        f"Condition: {cond} (WMO Code: {code})\n"
                        f"Precipitation: {precip} mm\n"
                        f"Pressure: {pressure} hPa\n"
                        f"Wind Speed: {wind} km/h  |  Wind Direction: {wind_dir} degrees\n"
                        f"---\n"
                        f"Data Source: Open-Meteo Satellite API (100% real-time, no cache)"
                    )
                    item = {
                        "feed_type": "personal_weather",
                        "title": title,
                        "summary": f"Live weather for {display_name}: {temp}C, {cond}, Humidity {humidity}%, Wind {wind} km/h",
                        "full_text": full_text,
                        "url": f"https://open-meteo.com/en/docs#latitude={lat}&longitude={lon}",
                        "location_name": display_name,
                        "published_at": obs_time
                    }
                    processed = self.pipeline.process_raw_item(item)
                    if processed:
                        collected.append(processed)
                    logger.info(f"Personal Tracker weather captured: {display_name} {temp}C {cond}")
            except Exception as e:
                logger.warning(f"Personal Tracker weather fetch failed for '{display_name}': {e}")

        # 2. Always fetch live news from Google News RSS for the topic/city
        try:
            news_url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
            nr = requests.get(news_url, headers=headers, timeout=6)
            if nr.status_code == 200:
                parsed = feedparser.parse(nr.content)
                for entry in parsed.entries[:4]:
                    title = getattr(entry, "title", "").strip()
                    if not title:
                        continue
                    raw_sum = getattr(entry, "summary", "") or getattr(entry, "description", "")
                    clean_sum = re.sub(r'<[^>]+>', ' ', raw_sum).strip()
                    link = getattr(entry, "link", "#")
                    pub = getattr(entry, "published", "")

                    item = {
                        "feed_type": "personal_news",
                        "title": f"[PERSONAL TRACKER: {name}] {title}",
                        "summary": clean_sum[:300],
                        "full_text": (
                            f"PERSONAL TRACKER LIVE NEWS\n"
                            f"Tracker: {name}\n"
                            f"Title: {title}\n"
                            f"URL: {link}\n"
                            f"Published: {pub}\n"
                            f"---\n"
                            f"{clean_sum}\n"
                            f"---\n"
                            f"Source: Google News RSS (real-time)"
                        ),
                        "url": link,
                        "location_name": query,
                        "published_at": pub
                    }
                    processed = self.pipeline.process_raw_item(item)
                    if processed:
                        collected.append(processed)
                logger.info(f"Personal Tracker news: {len(parsed.entries)} articles fetched for '{query}'")
        except Exception as e:
            logger.warning(f"Personal Tracker news fetch failed for '{query}': {e}")

        return collected

    def collect_all(self, trackers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run collection for all registered personal trackers."""
        all_docs = []
        for tracker in trackers:
            docs = self.collect_for_tracker(tracker)
            all_docs.extend(docs)
        return all_docs
