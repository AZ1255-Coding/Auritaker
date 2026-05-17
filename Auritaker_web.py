from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
import requests, os
from flask_cors import CORS
from tavily import TavilyClient

app = Flask(__name__)
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')
app.secret_key = os.environ.get("SECRET_KEY", "auritaker_secret")
CORS(app, supports_credentials=True, origins=["https://az1255-coding.github.io"])

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

MODEL = "openrouter/free"

# FIXED: Formatted system role clearly
SYSTEM_ROLE = (
    "You are Auritaker AI. Keep your answers extremely short, concise, and punchy. Be helpful and direct. "
    "Do not yap. Use bullet points if listing things. Max 2-3 sentences per response unless strictly asked for code. "
    "If the user asks for news, current events, or anything that may require up-to-date information, use the web search tool."
)

# Tracks accounts in memory (resets on server restart/deployment)
USERS = {"aryanzubin123@gmail.com": "password123"}

tavily = None
if TAVILY_API_KEY:
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
    except:
        pass

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
        if USERS.get(u) == p:
            session["user"] = u
            session["memory"] = [{"role": "system", "content": SYSTEM_ROLE}]
            return redirect("/")
        return render_template("login.html", error="Invalid email or password")
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        
        if not u or not p:
            return render_template("signup.html", error="Fields cannot be empty")
        
        if u in USERS:
            return render_template("signup.html", error="Username already exists")
        
        USERS[u] = p
        return redirect("/login")
        
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

def should_search(text):
    keys = ["latest", "news", "today", "who is", "what is", "when did", "where is",
            "update", "current", "recent", "now", "happened", "youtube", "yt",
            "song", "by the", "twitter", "reddit", "tiktok", "price", "score"]
    return any(k in text.lower() for k in keys)

def web_search(q):
    try:
        res = tavily.search(query=q, max_results=2)
        return "\n".join([r["content"] for r in res["results"]])[:800]
    except:
        return ""

@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session:
        return jsonify({"response": "Not logged in"})

    user_input = request.json.get("message", "")

    if tavily and should_search(user_input):
        web = web_search(user_input)
        if web:
            user_input += f"\n\n[Real-time data]:\n{web}"

    memory = session.get("memory", [{"role": "system", "content": SYSTEM_ROLE}])
    memory.append({"role": "user", "content": user_input})

    try:
        api_response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={"model": MODEL, "messages": memory[-10:]},
            timeout=25
        )
        reply = api_response.json()["choices"][0]["message"]["content"]
        memory.append({"role": "assistant", "content": reply})
        session["memory"] = memory
        return jsonify({"response": reply})
    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"})

# NEW: Automatically generates a 2-4 word summary title based on the first prompt
@app.route("/generate_title", methods=["POST"])
def generate_title():
    if "user" not in session:
        return jsonify({"title": "New Chat"})
        
    user_input = request.json.get("message", "")
    if not user_input:
        return jsonify({"title": "New Chat"})

    title_prompt = [
        {"role": "system", "content": "You are a title generator. Convert the user's message into an extremely short, clean, descriptive title of 2 to 4 words. Do not use quotes, punctuation, or extra words. Just output the title."},
        {"role": "user", "content": f"Message: {user_input}"}
    ]

    try:
        api_response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={"model": MODEL, "messages": title_prompt},
            timeout=15
        )
        title = api_response.json()["choices"][0]["message"]["content"].strip()
        return jsonify({"title": title})
    except Exception:
        return jsonify({"title": "New Chat"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
