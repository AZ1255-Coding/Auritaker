import os

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

MODEL = "gemini-3.1-flash"

SYSTEM_ROLE = """
You are Auritaker AI.

RULES:
- Use ONLY provided context if available.
- Never hallucinate facts.
- If missing info, say: "Not available in sources."
- Be concise and factual.
"""
