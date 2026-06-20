from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
from flask_cors import CORS
from flask_session import Session  # Resolves the 4KB cookie overflow issue
from tavily import TavilyClient
import requests, os, json, re, base64

# ---------------- APP SETUP ---------------- #

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "auritaker_secret")

# Configure Server-Side Sessions
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
Session(app)

CORS(app, supports_credentials=True, origins=[
    "https://az1255-coding.github.io"
])

MAX_MEMORY = 20

# ---------------- CONFIG ---------------- #

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

MODEL = "gemini-3.1-flash-lite"

SYSTEM_ROLE = """
You are Auritaker AI, a multimodal sports assistant.

RULES:
- Prioritize provided real-time context when available.
- If information is not in the provided context, use general knowledge when appropriate.
- Never fabricate specific facts.
- If information cannot be verified, say: "Not available in sources."
- Be concise and factual.
- When analyzing images, provide detailed insights about sports-related content.
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
    session.modified = True  # Explicitly tell Flask the session changed


# ---------------- IMAGE HANDLING ---------------- #

def encode_image_to_base64(file_obj):
    """Convert uploaded file to base64 string"""
    return base64.b64encode(file_obj.read()).decode('utf-8')


def get_mime_type(filename):
    """Get MIME type from filename"""
    ext = filename.lower().split('.')[-1]
    mime_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp'
    }
    return mime_types.get(ext, 'image/jpeg')


# ---------------- GEMINI ---------------- #

def call_gemini(contents, system_instruction):
    if not GEMINI_API_KEY:
        return "Model error: Missing GEMINI_API_KEY"

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

        if response.status_code != 200:
            return f"HTTP {response.status_code}: {response.text}"

        data = response.json()

        if "error" in data:
            return "Model error: " + data["error"].get("message", "Unknown error")

        candidates = data.get("candidates", [])
        if not candidates:
            return "Model error: No candidates returned"

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])

        if not parts:
            return "Model error: Empty response"

        return parts[0].get("text", "").strip() or "Model error: empty text"

    except Exception as e:
        return "Model error: " + str(e)


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
        u = request.form.get("username", "")
        p = request.form.get("password", "")

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
        u = request.form.get("username", "")
        p = request.form.get("password", "")

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


# ---------------- CHAT (MULTIMODAL) ---------------- #

@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session:
        return jsonify({"response": "Not logged in"}), 401

    # Handle both JSON and FormData
    user_input = ""
    image_data = None
    mime_type = None

    # Try to get message from JSON first
    if request.is_json:
        req_data = request.get_json(silent=True) or {}
        user_input = req_data.get("message", "")
    else:
        # Get from FormData
        user_input = request.form.get("message", "")

    # Handle image upload
    if "image" in request.files:
        image_file = request.files["image"]
        if image_file and image_file.filename:
            try:
                image_data = encode_image_to_base64(image_file)
                mime_type = get_mime_type(image_file.filename)
                print(f"Image received: {image_file.filename} ({mime_type})")
            except Exception as e:
                print(f"Image processing error: {e}")
                return jsonify({"response": f"Error processing image: {str(e)}"}), 400

    if not user_input.strip() and not image_data:
        return jsonify({"response": "Empty message and no image"}), 400

    memory = get_memory()

    # -------- WEB SEARCH (only if text and triggers pattern) -------- #
    context = None
    if user_input.strip() and should_search(user_input):
        context = web_search(user_input)

    # -------- SAVE USER MESSAGE TO MEMORY -------- #
    message_record = {
        "role": "user",
        "content": user_input if user_input.strip() else "[Image shared]"
    }
    if image_data:
        message_record["image_base64"] = image_data
        message_record["image_mime"] = mime_type

    memory["messages"].append(message_record)

    recent = memory["messages"][-10:]

    # -------- BUILD GEMINI INPUT (MULTIMODAL) -------- #
    contents = []
    for msg in recent:
        role = "model" if msg["role"] == "assistant" else "user"
        parts = []

        # Add text
        text_content = msg.get("content", "")
        if text_content:
            parts.append({"text": text_content})

        # Add image if present
        if msg.get("image_base64"):
            parts.append({
                "inlineData": {
                    "mimeType": msg.get("image_mime", "image/jpeg"),
                    "data": msg["image_base64"]
                }
            })

        if parts:
            contents.append({"role": role, "parts": parts})

    # -------- INJECT WEB SEARCH CONTEXT INTO LAST USER MESSAGE -------- #
    if context and contents and contents[-1]["role"] == "user":
        context_text = f"\n\nReal-time web context:\n{json.dumps(context, indent=2)}"
        if contents[-1]["parts"] and "text" in contents[-1]["parts"][0]:
            contents[-1]["parts"][0]["text"] += context_text
        else:
            contents[-1]["parts"].insert(0, {"text": context_text})

    # -------- CALL GEMINI -------- #
    reply = call_gemini(contents, memory["system"])

    # -------- SAVE RESPONSE -------- #
    memory["messages"].append({
        "role": "assistant",
        "content": reply
    })

    memory["messages"] = memory["messages"][-MAX_MEMORY:]
    save_memory(memory)

    return jsonify({"response": reply})


# ---------------- RUN ---------------- #

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 1000))
    app.run(host="0.0.0.0", port=port)
