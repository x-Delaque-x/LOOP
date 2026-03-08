"""
Gemini AI Tagger - Categorizes events using Google Gemini API.

Supports both single-event and batch tagging. Batch mode sends up to 15
events in one API call, cutting Gemini requests by ~90%.
"""
import json
import logging
from typing import List, Dict

from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL, MASTER_TAGS, AGE_TAGS

log = logging.getLogger("enrichment.tagger")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

SYSTEM_PROMPT = f"""You are an event categorization engine for a family activity finder called LOOP.
Given event titles and descriptions, return tags for each event.

Category tags (pick ALL that apply): {', '.join(MASTER_TAGS)}

Age group tags (pick the MOST SPECIFIC one): {', '.join(AGE_TAGS)}

Rules:
- Include at least one category tag per event
- Include exactly one age group tag per event — use "All Ages" only if the event truly has no age restriction
- If the title/description mentions babies, toddlers, or ages 0-2 → Baby (0-2)
- If it mentions preschool, storytime for young children, ages 3-5 → Preschool (3-5)
- If it mentions kids, children, elementary, ages 6-12 → Kids (6-12)
- If it mentions teens, young adults, grades 6-12, ages 13-17 → Teens (13-17)
- If the event appears to be free, include "Free"
- Do not invent tags outside the lists above
"""

BATCH_PROMPT = """Tag each event below. Return a JSON array with one entry per event.
Each entry is a string of comma-separated tags.

Events:
{events_text}

Return ONLY a JSON array of strings like: ["Arts, Kids (6-12), Free", "STEM, Teens (13-17)"]"""

SINGLE_PROMPT = """Tag this event. Return ONLY comma-separated tags, nothing else.

Title: {title}
Description: {description}

Example output: Education, STEM, Kids (6-12), Free"""

BATCH_SIZE = 15


def tag_event(title: str, description: str) -> str:
    """Return comma-separated tags for one event."""
    if not client:
        return "Social, All Ages"

    prompt = SINGLE_PROMPT.format(title=title, description=description or "")

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"system_instruction": SYSTEM_PROMPT},
        )
        tags = response.text.strip().strip('"\'')
        log.debug(f"Tagged '{title}' -> {tags}")
        return tags
    except Exception as e:
        log.warning(f"Gemini tagging failed for '{title}': {e}")
        return "Social, All Ages"


def tag_events_batch(events: List[Dict]) -> List[str]:
    """Tag multiple events in one API call. Returns list of tag strings."""
    if not client:
        return ["Social, All Ages"] * len(events)

    if not events:
        return []

    results = []

    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i:i + BATCH_SIZE]

        # Build the events text block
        lines = []
        for idx, ev in enumerate(batch):
            title = ev.get("title", "")
            desc = (ev.get("description", "") or "")[:200]
            lines.append(f"{idx + 1}. Title: {title}\n   Description: {desc}")

        events_text = "\n".join(lines)
        prompt = BATCH_PROMPT.format(events_text=events_text)

        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={"system_instruction": SYSTEM_PROMPT},
            )
            raw = response.text.strip()

            # Extract JSON array from response
            # Handle cases where Gemini wraps in ```json ... ```
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            tags_list = json.loads(raw)

            if isinstance(tags_list, list) and len(tags_list) == len(batch):
                results.extend(tags_list)
                log.info(f"  Batch tagged {len(batch)} events")
            else:
                # Length mismatch — fall back to individual tagging
                log.warning(f"Batch returned {len(tags_list)} tags for {len(batch)} events, falling back")
                for ev in batch:
                    results.append(tag_event(ev.get("title", ""), ev.get("description", "")))

        except (json.JSONDecodeError, Exception) as e:
            log.warning(f"Batch tagging failed ({e}), falling back to individual")
            for ev in batch:
                results.append(tag_event(ev.get("title", ""), ev.get("description", "")))

    return results
