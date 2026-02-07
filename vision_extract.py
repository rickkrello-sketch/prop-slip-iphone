import os
import json
import base64
from typing import List, Dict, Any

from openai import OpenAI

SYSTEM_PROMPT = """You extract sports prop card data from screenshots.

Return ONLY valid JSON: an array of objects, each object with keys:
- sport (string, e.g. "NBA", "SOCCER", "TENNIS")
- player (string)
- team (string or "")
- opponent (string or "")
- market (string, e.g. "Points", "Rebounds", "PRA", "Passes Attempted")
- line (number)  # the main line shown
- alt_line (number or null)  # if user selected an alternate line, else null
- is_demon (true/false)  # demon icon/red = true
- is_goblin (true/false)  # goblin/green = true
- game_time (string or "")  # if visible

Rules:
- If a field is not visible, use "" or null.
- Convert strings like "23.5" to number 23.5.
- If multiple props are visible in one screenshot, output multiple objects.
"""

def _b64_image(file_bytes: bytes) -> str:
    return base64.b64encode(file_bytes).decode("utf-8")

def extract_props_from_images(uploaded_files) -> List[Dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY", None)
    if not api_key:
        # Streamlit secrets
        import streamlit as st
        api_key = st.secrets.get("OPENAI_API_KEY", None)

    client = OpenAI(api_key=api_key)

    images_content = []
    for f in uploaded_files:
        img_bytes = f.getvalue()
        images_content.append({
            "type": "input_image",
            "image_url": f"data:image/png;base64,{_b64_image(img_bytes)}"
        })

    # Use a fast/cheap vision-capable model.
    # You can swap this later if you want higher accuracy.
    model = "gpt-4o-mini"

    resp = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "Extract all prop cards from these screenshots."}] + images_content,
            },
        ],
    )

    text = resp.output_text.strip()

    # Hard safety: ensure JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        return data
    except Exception:
        # If the model returns extra text, try to recover JSON block
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
        raise
