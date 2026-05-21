from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
import requests, os, json
from flask_cors import CORS
from tavily import TavilyClient

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "auritaker_secret")
CORS(app, supports_credentials=True, origins=["https://az1255-coding.github.io"])

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
NGROK_URL = "https://parsnip-crevice-guiding.ngrok-free.dev"

MODEL = "auritaker-aura-1"
SYSTEM_ROLE = "You are Auritaker, a high-intelligence AI built in April 2026. Be sharp, witty, and direct. Never greet the user unless they greet first. Skip self-introductions. Just answer and be helpful."

USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE) as f:
            return json.load(f)
    return {"aryanzubin123@gmail.com": "password123"}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

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
        if load_users().get(u) == p:
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
        users = load_users()
        if u in users:
            return render_template("signup.html", error="Email already registered")
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

def should_search(text):
    keys = ["latest", "news", "today", "who is", "what is", "when did", "where is",
            "update", "current", "recent", "now", "happened", "youtube", "yt",
            "song", "by the", "twitter", "reddit", "tiktok", "price", "score",
            "weather", "sports", "game", "match", "live", "stream", "video"]
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

    prompt = "\n".join([m["content"] for m in memory[-10:]])

    try:
        r = requests.post(
            f"{NGROK_URL}/api/generate",
            headers={"ngrok-skip-browser-warning": "true"},
            json={"model": MODEL, "prompt": prompt, "stream": True},
            timeout=30
        )
        print("STATUS:", r.status_code)
        print("RESPONSE TEXT:", r.text[:500])
        reply = r.json()["response"]
        memory.append({"role": "assistant", "content": reply})
        session["memory"] = memory
        return jsonify({"response": reply})

    except Exception as e:
        print("EXCEPTION:", str(e))
        return jsonify({"response": f"Error: {str(e)}"})
    
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
