import asyncio
import os
import re
import time
import webbrowser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx


@dataclass
class SkillResult:
    # What AMANE should say (split-friendly). Keep these short for low latency.
    sentences: list[str]

    # Optional UI/side-effect actions.
    # Example: {"type":"open_url","url":"https://..."}
    actions: list[dict[str, Any]]


class SkillRouter:
    def __init__(self, *, workspace_dir: Path):
        self.workspace_dir = workspace_dir
        self.notes_dir = workspace_dir / "notes"
        self.notes_file = self.notes_dir / "notes.md"

    async def try_handle(self, user_text: str) -> SkillResult | None:
        text = (user_text or "").strip()
        if not text:
            return None

        # Make commands resilient to wake words and politeness.
        text = re.sub(r"^(?:hey|hi|hello)\s+", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"^amane\b[\s,]*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"^please\b[\s,]*", "", text, flags=re.IGNORECASE).strip()

        lowered = text.lower().strip()

        # --- help ---
        if re.fullmatch(r"(help|commands|skills|what can you do\??|what can you do for me\??)", lowered):
            return SkillResult(
                sentences=[
                    "Here are some things I can do without any paid subscriptions.",
                    "Say: time, date, weather in Chennai, forecast in Chennai, news, note buy milk, show notes.",
                    "You can also say: open Media, read somefile dot pdf, email to someone at example dot com colon your message.",
                    "And: timer 5 minutes, or cancel timers.",
                ],
                actions=[],
            )

        # --- time/date ---
        if re.fullmatch(r"(time|what(\s+is|'s)\s+the\s+time\??)", lowered):
            now = datetime.now()
            return SkillResult(
                sentences=[f"It is {now.strftime('%I:%M %p').lstrip('0')}."] ,
                actions=[],
            )

        if re.fullmatch(r"(date|what(\s+is|'s)\s+the\s+date\??|day\??)", lowered):
            now = datetime.now()
            return SkillResult(
                sentences=[f"Today is {now.strftime('%A, %B %d')}."],
                actions=[],
            )

        # --- notes ---
        notes_word = re.search(r"\bnotes?\b", lowered) is not None
        notes_read_verb = re.search(r"\b(show|read|open|list|latest)\b", lowered) is not None
        notes_write_verb = re.search(r"\b(add|write|put|save|remember|note)\b", lowered) is not None
        notes_prefix = re.match(r"^(?:notes?|in\s+(?:my\s+)?notes?)\b", lowered) is not None
        notes_has_container_phrase = re.search(r"\b(?:to|in|into)\s+(?:my\s+)?notes?\b", lowered) is not None
        notes_has_colon = re.search(r"\bnotes?\s*[:\-–—]", text, flags=re.IGNORECASE) is not None
        word_count = len(re.findall(r"[a-z0-9']+", lowered))

        # Only treat casual mentions of "notes" as a command when it's short or strongly command-like.
        notes_command_like = bool(
            notes_word
            and (
                word_count <= 14
                or notes_prefix
                or notes_read_verb
                or notes_write_verb
                or notes_has_container_phrase
                or notes_has_colon
            )
        )

        # Read notes: accept a wide variety of phrasing.
        if notes_command_like and (
            notes_read_verb
            or re.fullmatch(r"(?:my\s+)?notes?\??", lowered)
            or re.search(r"\bwhat(?:'s|\s+is)?\s+in\s+(?:my\s+)?notes?\b", lowered)
        ):
            last_lines = await asyncio.to_thread(self._read_last_notes, 10)
            if not last_lines:
                return SkillResult(sentences=["Your notes are empty."], actions=[])
            spoken = "Here are your latest notes. " + " ".join(last_lines[-5:])
            return SkillResult(sentences=[spoken], actions=[])

        # Notes trigger (like weather trigger): if user says "...notes..." we try hard
        # to treat it as a notes command even if the phrase isn't at the start.
        if notes_command_like and (notes_write_verb or notes_prefix or notes_has_container_phrase or notes_has_colon):
            content: str | None = None

            patterns = [
                r"^(?:notes?)\s*[:\-–—]\s*(.*)$",
                r"\badd\b\s+(.*?)\s+\b(?:to|in|into)\s+notes?\b",
                r"\bwrite\b\s+(.*?)\s+\b(?:to|in|into)\s+notes?\b",
                r"\bput\b\s+(.*?)\s+\b(?:to|in|into)\s+notes?\b",
                r"\bsave\b\s+(.*?)\s+\b(?:to|in|into)\s+notes?\b",
                r"\badd\b\s+(.*?)\s+\b(?:to|in|into)\s+(?:my\s+)?notes?\b",
                r"\bwrite\b\s+(.*?)\s+\b(?:to|in|into)\s+(?:my\s+)?notes?\b",
                r"\bput\b\s+(.*?)\s+\b(?:to|in|into)\s+(?:my\s+)?notes?\b",
                r"\bsave\b\s+(.*?)\s+\b(?:to|in|into)\s+(?:my\s+)?notes?\b",
                r"\b(?:to|in|into)\s+(?:my\s+)?notes?\b[\s,:;\-–—]*?(.*)$",
                r"^(?:notes?|in\s+(?:my\s+)?notes?)\b[\s,:;\-–—]*?(.*)$",
            ]

            for pat in patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    content = (m.group(1) or "").strip()
                    break

            # If we couldn't confidently extract content, ask instead of writing junk.
            if content is None:
                return SkillResult(sentences=["What should I write in your notes?"], actions=[])

            content = (content or "").strip().lstrip(":-–—,; ")
            content = self._clean_note_content(content)
            if not content:
                return SkillResult(sentences=["What should I write in your notes?"], actions=[])

            await asyncio.to_thread(self._append_note, content)
            return SkillResult(sentences=[f"Okay. Noted: {content}."], actions=[])

        if notes_command_like and notes_word:
            # The user said "notes" but we can't tell if they meant read or write.
            return SkillResult(sentences=["Do you want me to read your notes, or write a new note?"], actions=[])

        note_match = re.match(
            r"^(?:note|note that|take(?: a)? note|write(?: a)? note|add(?: this)? to notes|remember(?: this)?|write this down)\b[\s,:;\-–—]*?(.*)$",
            text,
            re.IGNORECASE,
        )
        if note_match:
            content = note_match.group(1).strip()
            content = content.lstrip(" ").lstrip(":-–—,; ")
            if not content:
                return SkillResult(sentences=["Tell me what you want me to write in your notes."], actions=[])

            await asyncio.to_thread(self._append_note, content)
            return SkillResult(
                sentences=[f"Okay. Noted: {content}."],
                actions=[],
            )

        # --- open url / search ---
        open_url_match = re.match(r"^(?:open|go to)\s+(https?://\S+)$", text, re.IGNORECASE)
        if open_url_match:
            url = open_url_match.group(1)
            await asyncio.to_thread(webbrowser.open, url)
            return SkillResult(sentences=["Okay."], actions=[])

        search_match = re.match(r"^(?:search for|google)\s+(.+)$", text, re.IGNORECASE)
        if search_match:
            query = search_match.group(1).strip()
            if not query:
                return SkillResult(sentences=["What should I search for?"], actions=[])
            url = "https://www.google.com/search?q=" + quote_plus(query)
            await asyncio.to_thread(webbrowser.open, url)
            return SkillResult(sentences=["Searching."], actions=[])

        # --- draft email (opens your mail app; no subscriptions/keys) ---
        if re.match(r"^(email|mail|draft email|write an email)\b", lowered):
            # Accept both real emails and spoken emails like: "karthik at gmail dot com"
            remainder = re.sub(r"^(email|mail|draft email|write an email)\s*(to\s+)?", "", text, flags=re.IGNORECASE).strip()
            if remainder:
                # Split on ':' or '-' if present for the body.
                parts = re.split(r"\s*[:\-]\s*", remainder, maxsplit=1)
                address_raw = parts[0].strip()
                body = parts[1].strip() if len(parts) > 1 else ""

                address = self._spoken_email_to_email(address_raw)
                if address and self._looks_like_email(address):
                    mailto = f"mailto:{address}?body={quote_plus(body)}"
                    await asyncio.to_thread(webbrowser.open, mailto)
                    return SkillResult(sentences=["Okay. I opened an email draft."], actions=[])

            return SkillResult(
                sentences=["Tell me the email like: email to name at gmail dot com colon your message."],
                actions=[],
            )

        # --- open file/folder ---
        open_path_match = re.match(r"^(?:open)\s+(?:file|folder)?\s*(.+)$", text, re.IGNORECASE)
        if open_path_match and lowered.startswith("open"):
            path_raw = open_path_match.group(1).strip().strip('"')
            if path_raw:
                path_raw = self._spoken_path_to_path(path_raw)
                resolved = self._resolve_user_path(path_raw)
                if resolved is None:
                    return SkillResult(
                        sentences=["I can only open files and folders inside your workspace for safety."],
                        actions=[],
                    )

                if not resolved.exists():
                    return SkillResult(sentences=["I can't find that path."], actions=[])

                if resolved.is_file() and resolved.suffix.lower() in {".exe", ".bat", ".cmd", ".ps1", ".msi"}:
                    return SkillResult(sentences=["I won't run executable files."], actions=[])

                await asyncio.to_thread(os.startfile, str(resolved))
                return SkillResult(sentences=["Opened."], actions=[])

        # --- read pdf ---
        read_pdf_match = re.match(r"^(?:read)\s+(.+?)(?:\.pdf|\s+pdf|\s+dot\s+pdf)$", text, re.IGNORECASE)
        if read_pdf_match:
            pdf_raw = read_pdf_match.group(1).strip().strip('"')
            pdf_raw = self._spoken_path_to_path(pdf_raw)
            # If user said "read file name pdf" we need to add extension.
            if not pdf_raw.lower().endswith(".pdf"):
                pdf_raw += ".pdf"
            resolved = self._resolve_user_path(pdf_raw)
            if resolved is None or not resolved.exists() or not resolved.is_file():
                return SkillResult(sentences=["I can't find that PDF in your workspace."], actions=[])

            text_out = await asyncio.to_thread(self._extract_pdf_text, resolved, 2)
            if not text_out:
                return SkillResult(sentences=["I couldn't read any text from that PDF."], actions=[])

            # Keep spoken output short by default.
            snippet = " ".join(text_out.split())
            snippet = snippet[:1200]
            return SkillResult(
                sentences=["Okay. Here is what it says. " + snippet],
                actions=[],
            )

        # --- timers/reminders ---
        timer_match = re.match(r"^(?:set\s+)?(?:a\s+)?(?:timer|remind me)(?:\s+for|\s+in)?\s+(.+)$", lowered)
        if timer_match:
            spec = timer_match.group(1).strip()
            seconds = self._parse_duration_seconds(spec)
            if seconds is None or seconds <= 0:
                return SkillResult(
                    sentences=["Tell me a duration like: timer 5 minutes."],
                    actions=[],
                )

            pretty = self._format_duration(seconds)
            return SkillResult(
                sentences=[f"Okay. Starting a {pretty} timer."],
                actions=[{"type": "timer_set", "seconds": seconds, "label": pretty}],
            )

        if re.fullmatch(r"(cancel timers|cancel all timers|stop timers)", lowered):
            return SkillResult(
                sentences=["Okay. Cancelled all timers."],
                actions=[{"type": "timer_cancel_all"}],
            )

        # --- weather / forecast (accept natural questions) ---
        if re.search(r"\bforecast\b", lowered) or re.search(r"\bweather\s+forecast\b", lowered):
            m = re.search(r"\b(?:weather\s+forecast|forecast)\b(?:\s+in|\s+for)?\s+(.*)$", text, re.IGNORECASE)
            city = (m.group(1) if m else "").strip()
            city = self._clean_city(city)
            if not city:
                return SkillResult(sentences=["Which city? Say: forecast in Chennai."], actions=[])

            forecast = await self._get_forecast(city, days=3)
            if forecast is None:
                return SkillResult(sentences=["Sorry, I couldn't fetch the forecast right now."], actions=[])

            return SkillResult(sentences=forecast, actions=[])

        if re.search(r"\bweather\b", lowered) or re.search(r"\btemperature\b", lowered):
            m = re.search(r"\bweather\b(?:\s+in|\s+for)?\s+(.*)$", text, re.IGNORECASE)
            city = (m.group(1) if m else "").strip()
            city = self._clean_city(city)
            if not city:
                # Allow just "weather" as a prompt.
                if re.fullmatch(r"(weather|temperature)", lowered):
                    return SkillResult(sentences=["Which city? Say: weather in Chennai."], actions=[])
                return None

            report = await self._get_weather(city)
            if report is None:
                return SkillResult(sentences=["Sorry, I couldn't fetch the weather right now."], actions=[])
            return SkillResult(sentences=[report], actions=[])

        # --- news (headlines) ---
        if re.fullmatch(r"(news|latest news|headlines)", lowered):
            headlines = await self._get_headlines()
            if not headlines:
                return SkillResult(sentences=["Sorry, I couldn't fetch the news right now."], actions=[])

            # Speak only a few.
            top = headlines[:5]
            speak = "Here are the latest headlines. " + " ".join(
                f"{i+1}. {h['title']}." for i, h in enumerate(top)
            )
            return SkillResult(sentences=[speak], actions=[{"type": "headlines", "items": top}])

        # --- simple calculator ---
        calc_match = re.match(r"^(?:calculate|what is)\s+([0-9\s\+\-\*/\(\)\.]+)$", lowered)
        if calc_match:
            expr = calc_match.group(1)
            value = self._safe_calc(expr)
            if value is None:
                return SkillResult(sentences=["I couldn't calculate that."], actions=[])
            return SkillResult(sentences=[f"The answer is {value}."], actions=[])

        return None

    def _append_note(self, content: str) -> None:
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.notes_file.open("a", encoding="utf-8") as f:
            f.write(f"- [{ts}] {content}\n")

    def _clean_note_content(self, raw: str) -> str:
        s = (raw or "").strip()
        if not s:
            return ""

        # Strip common command/filler phrases so we store the *note*, not the request.
        s = re.sub(r"^(?:please\s+)?(?:can|could|would|will)\s+you\s+", "", s, flags=re.IGNORECASE)
        s = re.sub(r"^(?:i\s+)?(?:want|need|have)\s+to\s+", "", s, flags=re.IGNORECASE)
        s = re.sub(r"^(?:remember\s+to|remind\s+me\s+to)\s+", "", s, flags=re.IGNORECASE)
        s = re.sub(r"^(?:that\s+)?", "", s, flags=re.IGNORECASE)

        s = " ".join(s.split()).strip()
        s = s.strip(" \t\r\n-–—:;,.?!\"")
        return s

    def _read_last_notes(self, max_lines: int) -> list[str]:
        if not self.notes_file.exists():
            return []
        lines = self.notes_file.read_text(encoding="utf-8").splitlines()
        # Strip timestamps for nicer TTS.
        cleaned: list[str] = []
        for line in lines[-max_lines:]:
            cleaned.append(re.sub(r"^[-*]\s*\[[^\]]+\]\s*", "", line).strip())
        return [c for c in cleaned if c]

    def _resolve_user_path(self, raw: str) -> Path | None:
        raw = raw.strip()
        if not raw:
            return None

        # Allow relative paths under workspace.
        p = Path(raw)
        if not p.is_absolute():
            p = (self.workspace_dir / p).resolve()
        else:
            p = p.resolve()

        try:
            # Safety: only inside workspace.
            p.relative_to(self.workspace_dir)
        except Exception:
            return None

        return p

    def _clean_city(self, raw: str) -> str:
        s = (raw or "").strip()
        if not s:
            return ""

        # Remove trailing fillers that often appear in speech.
        s = re.sub(r"\b(right now|now|today|currently|please|outside)\b", "", s, flags=re.IGNORECASE)
        s = s.strip(" \t\r\n,.?!")
        s = " ".join(s.split())
        return s

    def _spoken_path_to_path(self, raw: str) -> str:
        s = (raw or "").strip()
        # Common STT tokens.
        s = re.sub(r"\s+dot\s+", ".", s, flags=re.IGNORECASE)
        s = re.sub(r"\s+slash\s+", "/", s, flags=re.IGNORECASE)
        s = re.sub(r"\s+back\s*slash\s+", "/", s, flags=re.IGNORECASE)
        s = " ".join(s.split())
        return s

    def _spoken_email_to_email(self, raw: str) -> str | None:
        s = (raw or "").strip().lower()
        if not s:
            return None
        s = re.sub(r"\s+at\s+", "@", s)
        s = re.sub(r"\s+dot\s+", ".", s)
        s = s.replace(" ", "")
        return s

    def _looks_like_email(self, email: str) -> bool:
        return bool(re.fullmatch(r"[\w.\-+]+@[\w\-]+(?:\.[\w\-]+)+", email.strip()))

    async def _get_weather(self, city: str) -> str | None:
        async with httpx.AsyncClient(
            timeout=10,
            follow_redirects=True,
            headers={"User-Agent": "AMANE/1.0"},
        ) as client:
            geo = await self._geocode(client, city)
            if geo is None:
                return None
            lat, lon, name, admin1, country = geo

            where_parts = [name]
            if admin1:
                where_parts.append(admin1)
            if country:
                where_parts.append(country)
            where = ", ".join(where_parts)

            # Prefer wttr.in for "actual-feeling" current temps; it needs no key.
            try:
                wttr = await client.get(f"https://wttr.in/{lat:.5f},{lon:.5f}?format=j1")
                if wttr.status_code == 200:
                    data = wttr.json()
                    cc = (data.get("current_condition") or [{}])[0]
                    temp_c = float(cc.get("temp_C"))
                    feels_c = float(cc.get("FeelsLikeC"))
                    wind_kmph = float(cc.get("windspeedKmph"))
                    desc_list = cc.get("weatherDesc") or []
                    desc = (desc_list[0].get("value") if desc_list and isinstance(desc_list[0], dict) else None) or "current conditions"

                    # If it's night locally, avoid saying "sunny".
                    try:
                        local_str = str(cc.get("localObsDateTime") or "").strip()
                        local_dt = datetime.strptime(local_str, "%Y-%m-%d %I:%M %p") if local_str else None

                        weather0 = (data.get("weather") or [{}])[0]
                        astronomy = weather0.get("astronomy") or []
                        astro0 = astronomy[0] if isinstance(astronomy, list) and astronomy else {}
                        sunrise_str = str(astro0.get("sunrise") or "").strip()
                        sunset_str = str(astro0.get("sunset") or "").strip()

                        is_day = None
                        if local_dt and sunrise_str and sunset_str:
                            sunrise_t = datetime.strptime(sunrise_str, "%I:%M %p").time()
                            sunset_t = datetime.strptime(sunset_str, "%I:%M %p").time()
                            sunrise_dt = datetime.combine(local_dt.date(), sunrise_t)
                            sunset_dt = datetime.combine(local_dt.date(), sunset_t)
                            is_day = sunrise_dt <= local_dt <= sunset_dt
                        elif local_dt:
                            # Fallback heuristic.
                            is_day = 6 <= local_dt.hour <= 18

                        if is_day is False and re.search(r"\bsunny\b", desc, re.IGNORECASE):
                            desc = "Clear"
                    except Exception:
                        pass

                    return (
                        f"Weather in {where}: {desc}. {temp_c:.0f} degrees Celsius, feels like {feels_c:.0f}. "
                        f"Wind {wind_kmph:.0f} kilometers per hour."
                    )
            except Exception:
                pass

            # Fallback: Open-Meteo.
            weather = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
                    "timezone": "auto",
                    "temperature_unit": "celsius",
                    "wind_speed_unit": "kmh",
                },
            )
            if weather.status_code != 200:
                return None
            w = weather.json().get("current") or {}
            temp = float(w.get("temperature_2m"))
            feels = float(w.get("apparent_temperature"))
            wind = float(w.get("wind_speed_10m"))
            code = int(w.get("weather_code") or 0)
            desc = self._weather_code_to_text(code)

            return (
                f"Weather in {where}: {desc}. {temp:.0f} degrees Celsius, feels like {feels:.0f}. "
                f"Wind {wind:.0f} kilometers per hour."
            )

    async def _get_forecast(self, city: str, *, days: int) -> list[str] | None:
        days = max(1, min(int(days), 7))

        async with httpx.AsyncClient(timeout=10) as client:
            geo = await self._geocode(client, city)
            if geo is None:
                return None
            lat, lon, name, admin1, country = geo

            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                    "timezone": "auto",
                    "forecast_days": days,
                },
            )
            if resp.status_code != 200:
                return None

            daily = resp.json().get("daily") or {}
            times = daily.get("time") or []
            tmax = daily.get("temperature_2m_max") or []
            tmin = daily.get("temperature_2m_min") or []
            pop = daily.get("precipitation_probability_max") or []
            codes = daily.get("weather_code") or []

            if not times:
                return None

            where_parts = [name]
            if admin1:
                where_parts.append(admin1)
            if country:
                where_parts.append(country)
            where = ", ".join(where_parts)
            sentences: list[str] = [f"Forecast for {where}."]
            for i in range(min(days, len(times), len(tmax), len(tmin))):
                label = "Today" if i == 0 else ("Tomorrow" if i == 1 else None)
                if label is None:
                    try:
                        dt = datetime.strptime(times[i], "%Y-%m-%d")
                        label = dt.strftime("%A")
                    except Exception:
                        label = times[i]

                code = int(codes[i]) if i < len(codes) and codes[i] is not None else 0
                desc = self._weather_code_to_text(code)
                hi = float(tmax[i])
                lo = float(tmin[i])
                rain = None
                if i < len(pop) and pop[i] is not None:
                    try:
                        rain = float(pop[i])
                    except Exception:
                        rain = None

                if rain is None:
                    sentences.append(f"{label}: {desc}. High {hi:.0f} Celsius, low {lo:.0f}.")
                else:
                    sentences.append(f"{label}: {desc}. High {hi:.0f} Celsius, low {lo:.0f}. Rain chance {rain:.0f} percent.")

            return sentences

    async def _geocode(self, client: httpx.AsyncClient, city: str) -> tuple[float, float, str, str, str] | None:
        geo = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 8, "language": "en", "format": "json"},
        )
        if geo.status_code != 200:
            return None
        data = geo.json()
        results = data.get("results") or []
        if not results:
            return None

        # Prefer the most prominent match.
        best = max(results, key=lambda x: x.get("population") or 0)

        lat = float(best["latitude"])
        lon = float(best["longitude"])
        name = str(best.get("name") or city)
        admin1 = str(best.get("admin1") or "")
        country = str(best.get("country") or "")
        return lat, lon, name, admin1, country

    def _weather_code_to_text(self, code: int) -> str:
        mapping = {
            0: "clear sky",
            1: "mainly clear",
            2: "partly cloudy",
            3: "overcast",
            45: "fog",
            48: "depositing rime fog",
            51: "light drizzle",
            53: "drizzle",
            55: "dense drizzle",
            61: "slight rain",
            63: "rain",
            65: "heavy rain",
            71: "slight snow",
            73: "snow",
            75: "heavy snow",
            80: "rain showers",
            81: "heavy rain showers",
            82: "violent rain showers",
            95: "thunderstorm",
        }
        return mapping.get(code, "mixed conditions")

    async def _get_headlines(self) -> list[dict[str, str]]:
        # Use a free RSS feed (no key). You can swap this later.
        feeds = [
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
        ]

        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers={"User-Agent": "AMANE/1.0"}) as client:
            for url in feeds:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    items = self._parse_rss_items(resp.text)
                    if items:
                        return items
                except Exception:
                    continue
        return []

    def _parse_rss_items(self, xml_text: str) -> list[dict[str, str]]:
        try:
            root = ET.fromstring(xml_text)
        except Exception:
            return []

        items: list[dict[str, str]] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if title:
                items.append({"title": title, "link": link})
            if len(items) >= 10:
                break
        return items

    def _safe_calc(self, expr: str) -> str | None:
        # Very small safe calculator: allow only digits and operators.
        expr = expr.strip()
        if not expr:
            return None
        if re.search(r"[^0-9\s\+\-\*/\(\)\.]", expr):
            return None

        try:
            # Disable builtins.
            val = eval(expr, {"__builtins__": {}}, {})
        except Exception:
            return None

        if isinstance(val, (int, float)):
            if isinstance(val, float):
                return f"{val:.4g}"
            return str(val)
        return None

    def _parse_duration_seconds(self, spec: str) -> int | None:
        spec = (spec or "").strip().lower()
        if not spec:
            return None

        total = 0.0

        # Accept forms like: "5 minutes", "1 hour 20 minutes", "90 seconds"
        pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)")
        matches = list(pattern.finditer(spec))
        if not matches:
            # Bare number defaults to minutes.
            if re.fullmatch(r"\d+(?:\.\d+)?", spec):
                return int(float(spec) * 60)
            return None

        for m in matches:
            value = float(m.group(1))
            unit = m.group(2)
            if unit.startswith("h"):
                total += value * 3600
            elif unit.startswith("m"):
                total += value * 60
            else:
                total += value

        return int(total)

    def _format_duration(self, seconds: int) -> str:
        seconds = max(0, int(seconds))
        if seconds < 60:
            return f"{seconds} seconds"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} minutes"
        hours = minutes // 60
        minutes = minutes % 60
        if minutes == 0:
            return f"{hours} hours"
        return f"{hours} hours {minutes} minutes"

    def _extract_pdf_text(self, path: Path, max_pages: int) -> str:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        out: list[str] = []
        pages = reader.pages[: max_pages]
        for p in pages:
            try:
                out.append(p.extract_text() or "")
            except Exception:
                continue
        return "\n".join(out).strip()
