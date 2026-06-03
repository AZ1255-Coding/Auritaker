from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
from flask_cors import CORS
from tavily import TavilyClient
import requests, os, json, re

# ---------------- APP SETUP ---------------- #

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "auritaker_secret")

CORS(app, supports_credentials=True, origins=[
    "https://az1255-coding.github.io"
])

MAX_MEMORY = 20

# ---------------- CONFIG ---------------- #

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

MODEL = "gemini-3.1-flash"

SYSTEM_ROLE = """
You are Auritaker AI.

RULES:
- Use ONLY provided real-time context if given
- Never invent facts
- If info is missing say: "Not available in sources."
- Be concise and factual
"""

BAD_DOMAINS = ["quora.com", "reddit.com", "medium.com"]

# ---------------- TAVILY ---------------- #

tavily = None
if TAVILY_API_KEY:
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
        print("Tavily initialized")
    except Exception as e:
        print("Tavily init failed:", e)


def should_search(text: str) -> bool:
    patterns = [
        r"\blatest\b", r"\bnews\b", r"\btoday\b",
        r"\bwho is\b", r"\bwhat is\b",
        r"\bvs\b", r"\bscore\b", r"\bweather\b",
        r"\brecent\b", r"\bupdate\b"
    ]
    text = text.lower()
    return any(re.search(p, text) for p in patterns)


def clean_results(results):
    safe = []
    for r in results.get("results", []):
        url = r.get("url", "")
        if not any(b in url for b in BAD_DOMAINS):
            safe.append(r)
    return safe


def web_search(query):
    if not tavily:
        return None

    try:
        res = tavily.search(query=query, max_results=5)
        res["results"] = clean_results(res)

        return {
            "query": query,
            "results": [
                {
                    "title": r.get("title"),
                    "snippet": r.get("content"),
                    "url": r.get("url")
                }
                for r in res["results"]
            ]
        }

    except Exception as e:
        print("Tavily error:", e)
        return None


# ---------------- MEMORY ---------------- #

def get_memory():
    return session.get("memory", {
        "system": SYSTEM_ROLE,
        "messages": []
    })


def save_memory(memory):
    session["memory"] = memory


# ---------------- GEMINI ---------------- #

def call_gemini(contents, system_instruction):
    if not GEMINI_API_KEY:
        return "Model error: Missing GEMINI_API_KEY"

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"

        payload = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            }
        }

        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=25
        )

        if response.status_code != 200:
            return f"HTTP {response.status_code}: {response.text}"

        data = response.json()

        if "error" in data:
            return "Model error: " + data["error"].get("message", "Unknown error")

        candidates = data.get("candidates", [])
        if not candidates:
            return "Model error: No candidates returned"

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])

        if not parts:
            return "Model error: Empty response"

        return parts[0].get("text", "").strip() or "Model error: empty text"

    except Exception as e:
        return "Model error: " + str(e)


# ---------------- USER STORAGE ---------------- #

USERS_FILE = "users.json"


def load_users():
    if os.path.exists(USERS_FILE):
