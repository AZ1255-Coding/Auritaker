import re
from tavily import TavilyClient
from config import TAVILY_API_KEY

BAD_DOMAINS = ["quora.com", "reddit.com", "medium.com"]

tavily = None

if TAVILY_API_KEY:
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
    except Exception as e:
        print("Tavily error:", e)


def should_search(text):
    patterns = [
        r"\blatest\b", r"\bnews\b", r"\btoday\b",
        r"\bwho is\b", r"\bwhat is\b",
        r"\bvs\b", r"\bscore\b",
        r"\bweather\b", r"\brecent\b"
    ]
    text = text.lower()
    return any(re.search(p, text) for p in patterns)


def clean(results):
    safe = []
    for r in results.get("results", []):
        url = r.get("url", "")
        if not any(b in url for b in BAD_DOMAINS):
            safe.append(r)
    return safe


def search_web(query):
    if not tavily:
        return None

    try:
        res = tavily.search(query=query, max_results=5)
        res["results"] = clean(res)

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
        print("Search error:", e)
        return None
