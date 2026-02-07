import os
import json
import base64
import time
from typing import List, Dict, Any

import streamlit as st
from openai import OpenAI
from openai import RateLimitError, APIError, APIConnectionError

SYSTEM_PROMPT = """
You extract PrizePicks prop card data from a SINGLE screenshot.

Return ONLY valid JSON: either
- an object (single prop), OR
- an array of objects (if multiple props visible).

Each object MUST contain:
- sport: string (NBA, SOCCER, TENNIS, etc.) or ""
- player: string
- team: string or ""
- opponent: string or ""
- market: string (Points, Rebounds, Assists, PRA, Passes Attempted, Shots, Shots on Target, Goalie Saves, etc.)
- line: number
- offered_sides: array of strings from ["MORE","LESS"]
- last5: array of 5 numbers if visible else []
- is_demon: boolean
- is_goblin: boolean
- game_time: string or ""

Rules:
- If not visible, use "" or [].
- line must be a number.
- last5 must be exactly 5 numbers when present; otherwise [].
"""

def _b64_image(file_bytes: bytes) -> str:
    return base64.b64encode(file_bytes).decode("utf-8")

def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", None) or st.secrets.get("OPENAI_API_KEY", None)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found. Add it in Streamlit Secrets.")
    return OpenAI(api_key=api_key)

def _parse_json_loose(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        # recover bracketed json
        if "[" in text and "]" in text:
            start = text.find("[")
            end = text.rfind("]")
            return json.loads(text[start:end+1])
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}")
            return json.loads(text[start:end+1])
        raise

@st.cache_data(show_spinner=False)
def extract_props_from_one_image_cached(image_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Cached per image to avoid re-charging + re-hitting rate limits when you rerun the app.
    """
    client = _get_client()
    model = "gpt-4o-mini"

    img_content = [{
        "type": "input_image",
        "image_url": f"data:image/png;base64,{_b64_image(image_bytes)}"
    }]

    # Retry with exponential backoff for rate limits / transient errors
    last_err = None
    for attempt in range(6):  # ~ up to ~1+2+4+8+16+32 sec waits
        try:
            resp = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
                    {"role": "user", "content": [{"type": "input_text", "text": "Extract props as JSON only."}] + img_content},
                ],
            )
            data = _parse_json_loose(resp.output_text)
            if isinstance(data, dict):
                data = [data]
            return data

        except RateLimitError as e:
            last_err = e
            wait = min(2 ** attempt, 20)  # cap waits at 20s
            time.sleep(wait)

        except (APIError, APIConnectionError) as e:
            last_err = e
            wait = min(2 ** attempt, 10)
            time.sleep(wait)

    # If we exhausted retries:
    raise RuntimeError(
        "Rate limit hit repeatedly. Try fewer uploads (1–3), wait 60 seconds, "
        "or increase your OpenAI API limits/billing."
    ) from last_err

def extract_props_from_images(uploaded_files) -> List[Dict[str, Any]]:
    """
    Process images ONE BY ONE to avoid rate limit spikes.
    """
    all_props: List[Dict[str, Any]] = []
    for f in uploaded_files:
        image_bytes = f.getvalue()
        props = extract_props_from_one_image_cached(image_bytes)
        all_props.extend(props)
        # small pacing delay helps a lot for low-tier keys
        time.sleep(0.6)
    return all_props