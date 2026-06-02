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

# ---------------- CONFIG ---------------- #

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

MODEL = "gemini-3.1-flash"  # safer stable model

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

        structured = {
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

        return structured

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

        # ---------------- HTTP CHECK ---------------- #
        if response.status_code != 200:
            return f"HTTP {response.status_code}: {response.text}"

        data = response.json()

        # ---------------- ERROR HANDLING ---------------- #
        if "error" in data:
            return "Model error: " + data["error"].get("message", "Unknown error")

        candidates = data.get("candidates", [])
        if not candidates:
            return "Model error: No candidates returned"

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])

        if not parts:
            return "Model error: Empty response parts"

        return parts[0].get("text", "").strip() or "Model error: empty text"

    except Exception as e:
        return "Model error: " + str(e)

        # ---------------- SAFETY CHECKS ---------------- #

        if "error" in data:
            return "Model error: " + data["error"].get("message", "Unknown error")

        if "candidates" not in data or not data["candidates"]:
            return "Model error: No candidates returned"

        candidate = data["candidates"][0]

        if "content" not in candidate:
            return "Model error: Empty content"

        parts = candidate["content"].get("parts", [])
        if not parts:
            return "Model error: Empty parts"

        return parts[0].get("text", "Model error: empty text")

    except Exception as e:
        return "Model error: " + str(e)


# ---------------- ROUTES ---------------- #

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')


@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        users = load_users()
        if users.get(u) == p:
            session["user"] = u
            session["memory"] = {
                "system": SYSTEM_ROLE,
                "messages": []
            }
            return redirect("/")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        users = load_users()

        if u in users:
            return render_template("signup.html", error="User exists")

        users[u] = p
        save_users(users)

        session["user"] = u
        session["memory"] = {
            "system": SYSTEM_ROLE,
            "messages": []
        }

        return redirect("/")

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- USER STORAGE ---------------- #

USERS_FILE = "users.json"


def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)


# ---------------- CHAT ---------------- #

@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session:
        return jsonify({"response": "Not logged in"})

    user_input = request.json.get("message", "")

    memory = get_memory()

    # -------- WEB SEARCH LAYER -------- #

    context = None
    if should_search(user_input):
        context = web_search(user_input)

    if context:
        user_input = {
            "message": user_input,
            "real_time_context": context
        }
        contents.append({
    "role": "user",
    "parts": [{
        "text": f"{user_input}"
    }]
})
    # -------- MEMORY BUILD -------- #

    memory["messages"].append({
        "role": "user",
        "content": user_input
    })

    recent = memory["messages"][-10:]

    # -------- GEMINI FORMAT -------- #

    contents = []
    for msg in recent:
        role = "user"
        if msg["role"] == "assistant":
            role = "model"

        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })

    # -------- CALL MODEL -------- #

    reply = call_gemini(contents, memory["system"])

    memory["messages"].append({
        "role": "assistant",
        "content": reply
    })
    memory["messages"] = memory["messages"][-MAX_MEMORY:]

MAX_MEMORY = 20
save_memory(memory)

    return jsonify({"response": reply})


# ---------------- RUN ---------------- #

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 1000))
    app.run(host="0.0.0.0", port=port)
