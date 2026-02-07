import os
import json
import base64
from typing import List, Dict, Any
from openai import OpenAI

SYSTEM_PROMPT = """
You extract PrizePicks prop card data from screenshots.

Return ONLY valid JSON: an array of objects. Each object MUST contain:
- sport: string (NBA, SOCCER, TENNIS, etc.) or ""
- player: string
- team: string or ""
- opponent: string or ""
- market: string (Points, Rebounds, Assists, PRA, Passes Attempted, Shots, Shots on Target, Goalie Saves, etc.)
- line: number (main line shown)
- offered_sides: array of strings from ["MORE","LESS"] depending on what is available on the card
- last5: array of 5 numbers if the last-5 bars/numbers are visible, else []
- is_demon: boolean (true if demon indicator is visible)
- is_goblin: boolean (true if goblin/green alt line is visible)
- game_time: string or ""

Rules:
- If any field is not visible, use "" or [].
- line must be a number.
- last5 must be exactly 5 numbers when present; otherwise [].
- If multiple props are visible in one screenshot, output multiple objects.
"""

def _b64_image(file_bytes: bytes) -> str:
    return base64.b64encode(file_bytes).decode("utf-8")

def extract_props_from_images(uploaded_files) -> List[Dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY", None)
    if not api_key:
        import streamlit as st
        api_key = st.secrets.get("OPENAI_API_KEY", None)

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found. Add it in Streamlit Secrets.")

    client = OpenAI(api_key=api_key)
    model = "gpt-4o-mini"  # fast + cost-effective for screenshots

    images_content = []
    for f in uploaded_files:
        img_bytes = f.getvalue()
        images_content.append({
            "type": "input_image",
            "image_url": f"data:image/png;base64,{_b64_image(img_bytes)}"
        })

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Extract the prop cards from these screenshots as JSON only."}] + images_content
            },
        ],
    )

    text = resp.output_text.strip()

    # Robust JSON recovery
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        return data
    except Exception:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
        raise