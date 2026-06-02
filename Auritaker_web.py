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

# Changed environment variable name to reflect Google AI Studio
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

# Updated to a current Gemini model identifier
MODEL = "gemini-3.1-flash-lite"
SYSTEM_ROLE = "You are Auritaker, an intelligent and helpful AI built by a young developer in April 2026. Be sharp, witty, and direct. Never greet the user unless they greet first. Skip self-introductions. Just answer and be helpful. If unsure, say so."

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

    # Keep conversation history to last 10 messages
    recent_history = memory[-10:]

    # Convert the OpenAI role structure into Google's required JSON layout
    # System instructions go into systemInstruction; 'assistant' changes to 'model'
    gemini_contents = []
    system_instruction = SYSTEM_ROLE

    for msg in recent_history:
        if msg["role"] == "system":
            system_instruction = msg["content"]
        else:
            role = "model" if msg["role"] == "assistant" else "user"
            gemini_contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

    try:
        # Google AI Studio direct v1beta API endpoint call
        api_response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": gemini_contents,
                "systemInstruction": {
                    "parts": [{"text": system_instruction}]
                }
            },
            timeout=25
        )
        
        response_json = api_response.json()
        print(response_json)
        reply = response_json["candidates"][0]["content"]["parts"][0]["text"]
        
        memory.append({"role": "assistant", "content": reply})
        session["memory"] = memory
        return jsonify({"response": reply})

    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
