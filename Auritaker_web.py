from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory, Response, copy_current_request_context
from flask_cors import CORS
from flask_session import Session
from tavily import TavilyClient
import os, json, re, time
from ddgs import DDGS
from google import genai
from google.genai import types

# ---------------- APP SETUP ---------------- #

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "auritaker_secret")

app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
Session(app)

CORS(app, supports_credentials=True, origins=["https://github.io"])

MAX_MEMORY = 20

# ---------------- CONFIG & CLIENTS ---------------- #

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
MODEL = "gemini-3.1-flash-lite"
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

SYSTEM_ROLE = """You are Auritaker AI, a multimodal sports assistant. RULES: Prioritize context. Never fabricate facts. If unverified, say 'Not available in sources.' Be concise."""

BAD_DOMAINS = ["quora.com", "reddit.com", "medium.com"]

# ---------------- TAVILY & SEARCH ---------------- #

tavily = None
if TAVILY_API_KEY:
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
    except Exception as e:
        print("Tavily init failed:", e)

def should_search(text: str) -> bool:
    patterns = [r"\blatest\b", r"\bnews\b", r"\btoday\b", r"\bwho is\b", r"\bwhat is\b", r"\bvs\b", r"\bscore\b", r"\bweather\b", r"\brecent\b", r"\bupdate\b"]
    return any(re.search(p, text.lower()) for p in patterns)

def web_search(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        cleaned = []
        for item in results:
            url_link = item.get("url", "")
            if not any(b in url_link for b in BAD_DOMAINS):
                cleaned.append({"title": item.get("title"), "snippet": item.get("snippet") or item.get("body"), "url": url_link})
        return {"query": query, "results": cleaned}
    except Exception as e:
        print("DuckDuckGo Search error:", e)
        return None

# ---------------- MEMORY & USER STORAGE ---------------- #

def get_memory():
    return session.get("memory", {"system": SYSTEM_ROLE, "messages": []})

def save_memory(memory):
    session["memory"] = memory
    session.modified = True

USERS_FILE = "users.json"
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f: return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f: json.dump(users, f)

# ---------------- ROUTES ---------------- #

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')

@app.route("/")
def home():
    if "user" not in session: return redirect("/login")
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form.get("username", ""), request.form.get("password", "")
        users = load_users()
        if users.get(u) == p:
            session["user"] = u
            session["memory"] = {"system": SYSTEM_ROLE, "messages": []}
            return redirect("/")
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u, p = request.form.get("username", ""), request.form.get("password", "")
        users = load_users()
        if u in users: return render_template("signup.html", error="User exists")
        users[u] = p
        save_users(users)
        session["user"] = u
        session["memory"] = {"system": SYSTEM_ROLE, "messages": []}
        return redirect("/")
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- CHAT ROUTE ---------------- #

@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session: return jsonify({"response": "Not logged in"}), 401
    if not ai_client: return jsonify({"response": "Model error"}), 500

    raw_message = request.form.get("message", "")
    uploaded_file_obj = request.files.get("file")
    
    memory = get_memory()
    user_input = raw_message
    
    context = web_search(user_input) if user_input.strip() and should_search(user_input) else None
    if context: user_input += f"\n\nReal-time web context:\n{json.dumps(context, indent=2)}"

    file_uri_to_store, mime_type_to_store = None, None
    if uploaded_file_obj and uploaded_file_obj.filename:
        temp_dir = os.path.join(os.getcwd(), "temp_uploads")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, uploaded_file_obj.filename)
        uploaded_file_obj.save(temp_path)
        try:
            gemini_file = ai_client.files.upload(file=temp_path)
            file_uri_to_store, mime_type_to_store = gemini_file.uri, gemini_file.mime_type
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)

    memory["messages"].append({"role": "user", "content": raw_message, "file_uri": file_uri_to_store, "mime_type": mime_type_to_store})
    recent = memory["messages"][-10:]
    
    contents = []
    for msg in recent:
        parts = [types.Part.from_text(text=msg["content"])]
        if msg.get("file_uri"): parts.append(types.Part.from_uri(file_uri=msg["file_uri"], mime_type=msg["mime_type"]))
        contents.append(types.Content(role="model" if msg["role"] == "assistant" else "user", parts=parts))

    @copy_current_request_context
    def generate_stream():
        full_reply = ""
        try:
            response_stream = ai_client.models.generate_content_stream(model=MODEL, contents=contents, config=types.GenerateContentConfig(system_instruction=memory["system"]))
            for chunk in response_stream:
                if chunk.text:
                    full_reply += chunk.text
                    yield chunk.text
            memory["messages"].append({"role": "assistant", "content": full_reply.strip()})
            save_memory(memory)
        except Exception as e:
            yield f"\n[Chat processing error: {repr(e)}]"

    return Response(generate_stream(), mimetype='text/markdown')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 1000)))
