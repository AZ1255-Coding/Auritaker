from flask import Flask, render_template, request, jsonify, session, redirect
import requests, os
from flask_cors import CORS
from tavily import TavilyClient

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "auritaker_secret")
CORS(app, supports_credentials=True, origins=["https://az1255-coding.github.io"])

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
MODEL_KEY = os.environ.get("MODEL_KEY")

MODEL = "auritaker-aura-1"  # This is the name of your model in Ollama. Change if you used a different name when importing.
SYSTEM_ROLE = "You are Auritaker, a high-intelligence AI built in April 2026. Be sharp, witty, and direct. Skip the self-introductions unless asked. Just answer and be helpful."

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
            "http://localhost:11434/api/chat",
            headers={
                "Authorization": f"Bearer {MODEL_KEY}",
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)