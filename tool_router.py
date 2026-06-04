import json
import requests
from datetime import datetime
from tavily import TavilyClient

# ---------------- CONFIG ---------------- #

GEMINI_API_KEY = None
TAVILY_API_KEY = None

tavily = None

# ---------------- SETUP ---------------- #

def init_tools(gemini_api_key, tavily_api_key=None):
    global GEMINI_API_KEY, TAVILY_API_KEY, tavily

    GEMINI_API_KEY = gemini_api_key
    TAVILY_API_KEY = tavily_api_key

    if tavily_api_key:
        try:
            tavily = TavilyClient(api_key=tavily_api_key)
        except Exception:
            tavily = None

# ---------------- TOOLS ---------------- #

def calculator_tool(query):
    try:
        allowed = "0123456789+-*/(). "
        if not all(c in allowed for c in query):
            return "Invalid mathematical expression."

        result = eval(query, {"__builtins__": {}}, {})
        return str(result)

    except Exception as e:
        return f"Calculator error: {e}"


def time_tool(query=None):
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def search_tool(query):
    if not tavily:
        return "Search unavailable."

    try:
        results = tavily.search(
            query=query,
            max_results=5
        )

        output = []

        for r in results.get("results", []):
            output.append({
                "title": r.get("title"),
                "content": r.get("content"),
                "url": r.get("url")
            })

        return json.dumps(output, indent=2)

    except Exception as e:
        return f"Search error: {e}"


def wikipedia_tool(query):
    return (
        "Wikipedia integration not configured yet. "
        f"Requested topic: {query}"
    )


def weather_tool(query):
    return (
        "Weather integration not configured yet. "
        f"Requested location: {query}"
    )


def translate_tool(query):
    return (
        "Translation integration not configured yet. "
        f"Requested text: {query}"
    )

# ---------------- ROUTER MODEL ---------------- #

ROUTER_PROMPT = """
You are a tool router.

Available tools:

- search
- calculator
- time
- wikipedia
- weather
- translate
- none

Respond ONLY with valid JSON.

Examples:

{
  "tool": "calculator",
  "query": "22*9"
}

{
  "tool": "weather",
  "query": "Kolkata"
}

{
  "tool": "none"
}
"""


def call_router_llm(user_message):
    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/gemini-3.1-flash-lite:generateContent"
        f"?key={GEMINI_API_KEY}"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": user_message
                    }
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {
                    "text": ROUTER_PROMPT
                }
            ]
        }
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=15
        )

        data = response.json()

        text = (
            data["candidates"][0]
            ["content"]["parts"][0]["text"]
        )

        return text

    except Exception:
        return '{"tool":"none"}'

# ---------------- MAIN ROUTER ---------------- #

def route_tool(user_message):
    try:
        decision_text = call_router_llm(user_message)

        decision_text = (
            decision_text
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        decision = json.loads(decision_text)

        tool = decision.get("tool", "none")
        query = decision.get("query", user_message)

        if tool == "calculator":
            return {
                "tool_used": tool,
                "result": calculator_tool(query)
            }

        if tool == "time":
            return {
                "tool_used": tool,
                "result": time_tool(query)
            }

        if tool == "search":
            return {
                "tool_used": tool,
                "result": search_tool(query)
            }

        if tool == "wikipedia":
            return {
                "tool_used": tool,
                "result": wikipedia_tool(query)
            }

        if tool == "weather":
            return {
                "tool_used": tool,
                "result": weather_tool(query)
            }

        if tool == "translate":
            return {
                "tool_used": tool,
                "result": translate_tool(query)
            }

        return None

    except Exception:
        return None
