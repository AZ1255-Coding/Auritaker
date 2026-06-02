from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
import requests, os, json
from flask_cors import CORS
from tavily import TavilyClient

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "auritaker_secret")
CORS(app, supports_credentials=True, origins=["https://az1255-coding.github.io"])

# ---------------- CONFIG ---------------- #

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

MODEL = "gemini-3.1-flash-lite"

SYSTEM_ROLE = """
You are Auritaker AI.

You are a strict fact-based assistant.

RULES:
- ONLY use REAL_TIME_CONTEXT JSON for external information.
- NEVER invent facts.
- NEVER generate narratives like "dominant discourse", "buzz", "analysts say".
- If data is missing, respond: "Not available in sources."
- Prefer short, factual sentences.
"""

USERS_FILE = "users.json"

# ---------------- USERS ---------------- #

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE) as f:
            return json.load(f)
    return {"aryanzubin123@gmail.com": "password123"}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

# ---------------- TAVILY ---------------- #

tavily = None
if TAVILY_API_KEY:
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
    except:
        pass

BAD_DOMAINS = ["quora.com", "reddit.com", "medium.com"]

def should_search(text):
    keys = [
        "latest", "news", "today", "who is", "what is", "when", "where",
        "update", "current", "recent", "now", "happened", "score", "match",
        "weather", "sports", "game", "live"
    ]
    return any(k in text.lower() for k in keys)

def clean_results(results):
    return [
        r for r in results["results"]
        if not any(b in r["url"] for b in BAD_DOMAINS)
    ]

def web_search(q):
    try:
        res = tavily.search(query=q, max_results=5)
        res["results"] = clean_results(res)

        structured = {
            "query": q,
            "results": [
                {
                    "title": r.get("title"),
                    "snippet": r.get("content"),
                    "url": r.get("url")
                }
                for r in res["results"]
            ]
        }

        return json.dumps(structured)[:1500]

    except:
        return ""

# ---------------- ROUTES ---------------- #

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')

@app.route("/", methods=["GET"])
def home():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        if load_users().get(u) == p:
            session["user"] = u
            session["memory"] = [{"role": "system", "content": SYSTEM_ROLE}]
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
        session["memory"] = [{"role": "system", "content": SYSTEM_ROLE}]
        return redirect("/")
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- CHAT ---------------- #

@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session:
        return jsonify({"response": "Not logged in"})

    user_input = request.json.get("message", "")

    # -------- SEARCH LAYER -------- #
    if tavily and should_search(user_input):
        web = web_search(user_input)

        if web:
            user_input += f"\n\nREAL_TIME_CONTEXT:\n{web}"

    # -------- MEMORY -------- #
    memory = session.get("memory", [{"role": "system", "content": SYSTEM_ROLE}])
    memory.append({"role": "user", "content": user_input})

    recent = memory[-10:]

    # -------- GEMINI FORMAT -------- #
    contents = []
    system_instruction = SYSTEM_ROLE

    for msg in recent:
        if msg["role"] == "system":
            system_instruction = msg["content"]
        else:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

    # -------- CALL GEMINI -------- #
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": contents,
                "systemInstruction": {
                    "parts": [{"text": system_instruction}]
                }
            },
            timeout=25
        )

        data = response.json()

        reply = data["candidates"][0]["content"]["parts"][0]["text"]

        memory.append({"role": "assistant", "content": reply})
        session["memory"] = memory

        return jsonify({"response": reply})

    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"})

# ---------------- RUN ---------------- #

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
