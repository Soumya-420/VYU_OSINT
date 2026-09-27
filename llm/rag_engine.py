import logging
import requests
import feedparser
import re
import time
from typing import List, Dict, Any, Optional, Set, Tuple
from llm.provider import get_llm_provider

logger = logging.getLogger("vyu.rag")

WEATHER_CODES = {
    0: "Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing Rime Fog",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    56: "Light Freezing Drizzle",
    57: "Dense Freezing Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    66: "Light Freezing Rain",
    67: "Heavy Freezing Rain",
    71: "Slight Snow Fall",
    73: "Moderate Snow Fall",
    75: "Heavy Snow Fall",
    77: "Snow Grains",
    80: "Slight Rain Showers",
    81: "Moderate Rain Showers",
    82: "Violent Rain Showers",
    85: "Slight Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm with Slight Hail",
    99: "Thunderstorm with Heavy Hail"
}


def _geocode_place(place_name: str) -> Optional[Tuple[float, float, str]]:
    """
    Multi-provider geocoder. Tries Open-Meteo first, then Nominatim/OpenStreetMap.
    Returns (lat, lon, display_name) or None.
    """
    headers_om = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    headers_nom = {"User-Agent": "VYU-OSINT-Platform/2.0 (contact@vyu.internal)"}

    # Try 1: Open-Meteo Geocoding API
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(place_name)}&count=1&language=en&format=json"
        resp = requests.get(url, headers=headers_om, timeout=5)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                r = results[0]
                city = r.get("name", place_name)
                admin1 = r.get("admin1", "")
                country = r.get("country", "")
                display = ", ".join(filter(None, [city, admin1, country]))
                return (r["latitude"], r["longitude"], display)
    except Exception as e:
        logger.warning(f"Open-Meteo geocoding failed for '{place_name}': {e}")

    # Try 2: Nominatim / OpenStreetMap Geocoding (catches all small towns, villages, etc.)
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(place_name)}&format=json&limit=1&accept-language=en"
        resp = requests.get(url, headers=headers_nom, timeout=5)
        if resp.status_code == 200:
            results = resp.json()
            if results:
                r = results[0]
                lat = float(r["lat"])
                lon = float(r["lon"])
                display = r.get("display_name", place_name)
                # Shorten display_name to first 3 parts
                parts = [p.strip() for p in display.split(",")]
                short_display = ", ".join(parts[:3])
                return (lat, lon, short_display)
    except Exception as e:
        logger.warning(f"Nominatim geocoding failed for '{place_name}': {e}")

    return None


class AskVYURAGEngine:
    """
    Ask VYU v2.0 RAG Engine.
    Operates strictly on 100% REAL LIVE INTERNET DATA.
    Uses multi-provider geocoding (Open-Meteo + Nominatim/OpenStreetMap)
    to resolve ANY place on Earth including small towns and villages.
    """

    def __init__(self, db_connection=None):
        self.db = db_connection
        self.llm = get_llm_provider()

    def query(self, user_query: str, evidence_docs: Optional[List[Dict[str, Any]]] = None, pipeline=None) -> Dict[str, Any]:
        logger.info(f"Ask VYU RAG Query: {user_query}")

        # Extract URL if present in query
        url_match = re.search(r'(https?://[^\s]+)', user_query)
        scraped_url_doc = None
        if url_match:
            target_url = url_match.group(1)
            logger.info(f"Detected URL in query, attempting live scrape: {target_url}")
            try:
                resp = requests.get(target_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=8)
                if resp.status_code == 200:
                    raw_html = resp.text
                    # Simple heuristic HTML stripping
                    clean_text = re.sub(r'<style[^>]*>.*?</style>', ' ', raw_html, flags=re.DOTALL|re.IGNORECASE)
                    clean_text = re.sub(r'<script[^>]*>.*?</script>', ' ', clean_text, flags=re.DOTALL|re.IGNORECASE)
                    clean_text = re.sub(r'<[^>]+>', ' ', clean_text)
                    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                    
                    doc_item = {
                        "feed_type": "direct_url",
                        "title": f"Live Web Page Scrape",
                        "summary": clean_text[:250],
                        "full_text": clean_text[:5000], # Limit context window
                        "url": target_url,
                        "location_name": "Direct Link",
                        "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    }
                    if pipeline:
                        processed = pipeline.process_raw_item(doc_item)
                        if processed:
                            scraped_url_doc = processed
                    else:
                        scraped_url_doc = doc_item
            except Exception as e:
                logger.warning(f"Failed to scrape URL {target_url}: {e}")
        
        # Extract place name from query (removing the URL first so it doesn't mess up place extraction)
        query_without_url = user_query.replace(target_url, "") if url_match else user_query
        raw_place = re.sub(
            r'\b(weather|temperature|temp|forecast|climate|rain|humidity|news|alerts?|update|updation|updatation|live|report|in|for|at|of|the|today|now|current|real|time|data)\b',
            '', query_without_url, flags=re.IGNORECASE
        ).strip()
        raw_place = re.sub(r'\s+', ' ', raw_place).strip()
        if not raw_place or len(raw_place) < 2:
            raw_place = query_without_url.strip()

        # Collect real live place-specific documents (weather + news)
        live_place_docs = []
        if raw_place and len(raw_place) >= 2:
            logger.info(f"Collecting REAL live weather & news for: '{raw_place}'")
            live_place_docs = self._collect_real_place_documents(raw_place, pipeline)

        # Build response from place-specific docs ONLY (strict relevance)
        if live_place_docs:
            top_docs = live_place_docs[:5]
        else:
            # Fallback: keyword search across all evidence
            docs_to_search = list(evidence_docs or [])
            query_words = [w.lower() for w in user_query.split() if len(w) >= 2]
            scored = []
            for doc in docs_to_search:
                text = (doc.get("title","") + " " + doc.get("summary","") + " " +
                        doc.get("full_text","") + " " + doc.get("location_name","")).lower()
                score = sum(1 for w in query_words if w in text)
                if score > 0:
                    doc["relevance_score"] = score
                    scored.append(doc)
            scored.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            top_docs = scored[:5]

        # Deduplicate
        unique_docs = []
        seen = set()
        
        # Always inject the directly scraped URL first if we found one
        if scraped_url_doc:
            unique_docs.append(scraped_url_doc)
            seen.add(scraped_url_doc.get("url", "").strip().lower())

        for d in top_docs:
            key = (d.get("url") or d.get("title","")).strip().lower()
            if key not in seen:
                seen.add(key)
                unique_docs.append(d)

        # Build clean structured sources list
        sources = []
        for d in unique_docs:
            pred = d.get("prediction", {})
            sources.append({
                "id": str(d.get("id", "")),
                "title": d.get("title", "Untitled"),
                "url": d.get("url", "#"),
                "feed_type": d.get("feed_type", "live").upper(),
                "location": d.get("location_name", "Global"),
                "summary": d.get("summary", "")[:250],
                "threat_level": pred.get("threat_level", "LOW"),
                "escalation_probability": pred.get("escalation_probability", 0.1),
                "predicted_impact": pred.get("predicted_impact", ""),
            })

        # Generate AI summary
        if unique_docs:
            context_text = "\n\n".join([
                f"Document {i+1}:\nTitle: {d.get('title')}\nSource: {d.get('feed_type','live').upper()}\nLocation: {d.get('location_name','Global')}\nContent: {d.get('full_text', d.get('summary',''))[:800]}"
                for i, d in enumerate(unique_docs)
            ])
            prompt = f"""User Question: {user_query}

Retrieved Live Documents:
{context_text}

Instructions: Based ONLY on the retrieved documents above, write a clear, concise, friendly 3-5 sentence paragraph that directly answers the User Question. Focus on the most important facts. Do NOT include markdown, raw URLs, or document numbers."""
            system_prompt = "You are VYU AI, a professional intelligence analyst. Give clear human-readable answers."
            summary_text = self.llm.generate_text(prompt, system_prompt)
        else:
            summary_text = "No relevant documents were found in the current live feed for this query. The system is continuously collecting data — please try again in a moment or rephrase your question."

        return {
            "query": user_query,
            "summary": summary_text,
            "sources": sources,
            "sources_count": len(sources),
            "searched_documents_count": len(unique_docs),
            "full_text_indexed": True
        }

    def _collect_real_place_documents(self, place_query: str, pipeline=None) -> List[Dict[str, Any]]:
        """
        Geocodes any place (using Open-Meteo + Nominatim fallback),
        fetches REAL satellite weather from Open-Meteo,
        and fetches REAL news from Google News RSS.
        """
        collected = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        # 1. Geocode the place
        geo = _geocode_place(place_query)
        if not geo:
            logger.warning(f"Could not geocode place: '{place_query}'")
        
        # 2. Fetch Real Satellite Weather if geocoded
        if geo:
            lat, lon, display_name = geo
            try:
                weather_url = (
                    f"https://api.open-meteo.com/v1/forecast?"
                    f"latitude={lat}&longitude={lon}"
                    f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
                    f"precipitation,weather_code,surface_pressure,wind_speed_10m,wind_direction_10m"
                )
                w_resp = requests.get(weather_url, headers=headers, timeout=6)

                if w_resp.status_code == 200:
                    curr = w_resp.json().get("current", {})
                    temp = curr.get("temperature_2m")
                    feels = curr.get("apparent_temperature", temp)
                    humidity = curr.get("relative_humidity_2m")
                    precip = curr.get("precipitation", 0.0)
                    code = curr.get("weather_code", 0)
                    pressure = curr.get("surface_pressure")
                    wind = curr.get("wind_speed_10m")
                    wind_dir = curr.get("wind_direction_10m")
                    cond = WEATHER_CODES.get(code, f"WMO Code {code}")
                    obs_time = curr.get("time", "")

                    title = f"Real-Time Weather: {display_name} - {temp} C, {cond}, Humidity {humidity}%"
                    full_text = (
                        f"LIVE SATELLITE WEATHER REPORT\n"
                        f"Location: {display_name}\n"
                        f"Coordinates: {lat} N, {lon} E\n"
                        f"Observation Time: {obs_time}\n"
                        f"---\n"
                        f"Temperature: {temp} C (Feels Like: {feels} C)\n"
                        f"Humidity: {humidity}%\n"
                        f"Condition: {cond} (WMO Code: {code})\n"
                        f"Precipitation: {precip} mm\n"
                        f"Pressure: {pressure} hPa\n"
                        f"Wind: {wind} km/h, Direction: {wind_dir} degrees\n"
                        f"---\n"
                        f"Data Source: Open-Meteo Satellite API (real-time)"
                    )

                    item = {
                        "feed_type": "weather",
                        "title": title,
                        "summary": f"Live weather for {display_name}: {temp} C, {cond}, Humidity {humidity}%, Wind {wind} km/h",
                        "full_text": full_text,
                        "url": f"https://open-meteo.com/en/docs#latitude={lat}&longitude={lon}",
                        "location_name": display_name,
                        "published_at": obs_time
                    }
                    if pipeline:
                        processed = pipeline.process_raw_item(item)
                        if processed:
                            collected.append(processed)
                    else:
                        collected.append(item)
                    logger.info(f"Weather captured for {display_name}: {temp} C, {cond}")
                else:
                    logger.warning(f"Open-Meteo weather API returned status {w_resp.status_code}")
            except Exception as e:
                logger.warning(f"Weather fetch error for '{display_name}': {e}")

        # 3. Fetch Real Live News from Google News RSS
        try:
            news_url = f"https://news.google.com/rss/search?q={requests.utils.quote(place_query)}&hl=en-US&gl=US&ceid=US:en"
            n_resp = requests.get(news_url, headers=headers, timeout=6)
            if n_resp.status_code == 200:
                parsed = feedparser.parse(n_resp.content)
                for entry in parsed.entries[:3]:
                    title = getattr(entry, "title", "").strip()
                    if not title:
                        continue
                    raw_sum = getattr(entry, "summary", "") or getattr(entry, "description", "")
                    clean_sum = re.sub(r'<[^>]+>', ' ', raw_sum).strip()
                    link = getattr(entry, "link", "#")
                    pub = getattr(entry, "published", "")

                    full_text = (
                        f"LIVE NEWS for {place_query.upper()}\n"
                        f"Title: {title}\n"
                        f"URL: {link}\n"
                        f"Published: {pub}\n"
                        f"---\n"
                        f"{clean_sum}\n"
                        f"---\n"
                        f"Source: Google News RSS"
                    )

                    doc_item = {
                        "feed_type": "rss",
                        "title": title,
                        "summary": clean_sum[:250],
                        "full_text": full_text,
                        "url": link,
                        "location_name": place_query,
                        "published_at": pub
                    }
                    if pipeline:
                        processed = pipeline.process_raw_item(doc_item)
                        if processed:
                            collected.append(processed)
                    else:
                        collected.append(doc_item)
        except Exception as e:
            logger.warning(f"News fetch error for '{place_query}': {e}")

        return collected
