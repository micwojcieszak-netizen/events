"""
event_fetcher.py
Calls the Anthropic Claude API (with web_search tool) to fetch real event data
for a list of venues/teams. Processes venues in small batches and parses JSON.
"""
import re
import json
import anthropic
from datetime import datetime, timedelta

# Use Haiku for low memory footprint (free tier compatible)
MODEL = "claude-sonnet-4-20250514"

class EventFetcher:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    # ── Public ─────────────────────────────────────────────────────────────────
    def fetch(self, venues: list[str], months: int = 3) -> list[dict]:
        """Fetch all events for the given venue/team list over the next N months."""
        from_date = datetime.now()
        to_date = from_date + timedelta(days=months * 30)
        prompt = self._build_prompt(venues, from_date, to_date)

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=4000,  # Reduced for memory optimization
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = "\n".join(
            block.text for block in response.content if block.type == "text"
        )
        return self._parse(raw_text)

    # ── Private ────────────────────────────────────────────────────────────────
    def _build_prompt(self, venues: list[str], from_date: datetime, to_date: datetime) -> str:
        venue_list = "\n".join(f"  {i+1}. {v}" for i, v in enumerate(venues))
        return f"""Today is {from_date.strftime('%Y-%m-%d')}. You are a professional event data researcher.

Use web search to find ALL upcoming events for the venues / sports teams listed below,
covering the period from {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}.

VENUES / TEAMS:
{venue_list}

WHAT TO FIND:
- HOME games only for sports teams (NFL, NBA, MLS, soccer – not away matches)
- ALL concerts, shows, and ticketed events at each venue
- Use official team/venue sites, Ticketmaster, SeatGeek, AXS, Live Nation

OUTPUT FORMAT:
Return ONLY a valid JSON array – no preamble, no markdown fences, no trailing text.
Each object must include ALL of the following keys:

  "venue_name"            – official name of venue / stadium
  "venue_address"         – full street address, city, state/country
  "event_name"            – full event name (e.g. "Detroit Lions vs. Green Bay Packers")
  "event_type"            – exactly one of: NFL / NBA / NHL / MLB / MLS / Soccer / Concert / Entertainment / Other
  "event_date"            – YYYY-MM-DD
  "event_time_local"      – HH:MM 24h local venue time, or "TBD"
  "event_time_gmt2"       – same time converted to GMT+2 (HH:MM 24h), or "TBD"
  "duration_scheduled"    – e.g. "3h30m", "2h", "TBD"
  "capacity_or_tickets"   – venue capacity + ticket status, e.g. "65,000 | On sale" or "Sold out"
  "source_url"            – URL where this event was found

Sort the array by event_date ascending.
Return ONLY the JSON array. Nothing else."""

    def _parse(self, text: str) -> list[dict]:
        """Extract a JSON array from Claude's text response."""
        # 1. Try ```json … ``` block
        m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # 2. Try the largest [...] span in the text
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        # 3. Return empty list so the caller can still aggregate other batches
        return []
