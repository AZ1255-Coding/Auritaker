import requests
import json
from config import GEMINI_API_KEY, MODEL


def build_contents(messages):
    contents = []

    for m in messages:
        role = "user"
        if m["role"] == "assistant":
            role = "model"

        contents.append({
            "role": role,
            "parts": [{"text": m["content"]}]
        })

    return contents


def call_gemini(contents, system_prompt):
    try:
        res = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": contents,
                "systemInstruction": {
                    "parts": [{"text": system_prompt}]
                }
            },
            timeout=25
        )

        data = res.json()

        return data["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        return f"AI error: {str(e)}"
