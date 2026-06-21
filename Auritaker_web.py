from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
from flask_cors import CORS
from flask_session import Session  # Resolves the 4KB cookie overflow issue
from tavily import TavilyClient
import requests, os, json, re, base64, time
from duckduckgo_search import DDGS
from google import genai
from werkzeug.utils import secure_filename

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
UPLOAD_FOLDER = "/tmp"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ---------------- CONFIG ---------------- #

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

# Initializing modern GenAI Client
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-3.1-flash-lite"

SYSTEM_ROLE = """
You are Auritaker AI, a multimodal sports assistant.

RULES:
- Prioritize provided real-time context when available.
- If information is not in the provided context, use general knowledge when appropriate.
- Never fabricate specific facts.
- If information cannot be verified, say: "Not available in sources."
- Be concise and factual.
- When analyzing images or videos, provide detailed insights about sports-related content.
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
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        
        cleaned_results = []
        for item in results:
            url_link = item.get("href", "")
            if not any(b in url_link for b in BAD_DOMAINS):
                cleaned_results.append({
                    "title": item.get("title"),
                    "snippet": item.get("body"),
                    "url": url_link
                })

        return {
            "query": query,
            "results": cleaned_results
        }

    except Exception as e:
        print("DuckDuckGo Search error:", e)
        return None

# ---------------- MEMORY ---------------- #

def get_memory():
    return session.get("memory", {
        "system": SYSTEM_ROLE,
        "messages": []
    })


def save_memory(memory):
    session["memory"] = memory
    session.modified = True


# ---------------- FILE/IMAGE HANDLING ---------------- #

def encode_image_to_base64(file_obj):
    return base64.b64encode(file_obj.read()).decode('utf-8')


def get_mime_type(filename):
    ext = filename.lower().split('.')[-1]
    mime_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
        'mp4': 'video/mp4',
        'webm': 'video/webm',
        'mov': 'video/quicktime'
    }
    return mime_types.get(ext, 'image/jpeg')


def is_video_file(filename):
    ext = filename.lower().split('.')[-1]
    return ext in ['mp4', 'webm', 'mov', 'avi', 'mkv', '3gp']


# ---------------- GEMINI CALL ENGINE ---------------- #

def call_gemini_client(contents, system_instruction):
    if not GEMINI_API_KEY:
        return "Model error: Missing GEMINI_API_KEY"
    try:
        # Convert legacy parts-based dictionary structure back into the required prompt input format
        formatted_contents = []
        for item in contents:
            role = item.get("role")
            parts_list = []
            for p in item.get("parts", []):
                if "text" in p:
                    parts_list.append(p["text"])
                elif "inlineData" in p:
                    # Append raw bytes directly using modern SDK structures
                    parts_list.append({
                        "inline_data": {
                            "mime_type": p["inlineData"]["mimeType"],
                            "data": base64.b64decode(p["inlineData"]["data"])
                        }
                    })
            formatted_contents.append({"role": role, "parts": parts_list})

        response = client.models.generate_content(
            model=MODEL,
            contents=formatted_contents,
            config={"system_instruction": system_instruction}
        )
        return response.text
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


# ---------------- CHAT ROUTE ---------------- #

@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session:
        return jsonify({"response": "Not logged in"}), 401

    user_input = request.form.get("message", "")
    image_data = None
    mime_type = None
    video_path = None
    uploaded_cloud_file = None

    # Handle file uploads if sent via multipart form data
    if "file" in request.files:
        uploaded_file = request.files["file"]
        if uploaded_file and uploaded_file.filename != '':
            filename = secure_filename(uploaded_file.filename)
            mime_type = get_mime_type(filename)

            if is_video_file(filename):
                # Save locally to upload to the File API
                video_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                uploaded_file.save(video_path)
            else:
                # Handle standard inline images
                image_data = encode_image_to_base64(uploaded_file)

    if not user_input.strip() and not image_data and not video_path:
        return jsonify({"response": "Empty message and no media attached"}), 400

    memory = get_memory()

    # -------- WEB SEARCH -------- #
    context = None
    if user_input.strip() and should_search(user_input):
        context = web_search(user_input)

    # -------- SAVE USER MESSAGE TO HISTORICAL MEMORY -------- #
    message_record = {
        "role": "user",
        "content": user_input if user_input.strip() else "[Media attachment shared]"
    }
    if image_data:
        message_record["image_base64"] = image_data
        message_record["image_mime"] = mime_type

    memory["messages"].append(message_record)
    recent = memory["messages"][-10:]

    # -------- BUILD CONTEXT STRUCTURES -------- #
    contents = []
    for msg in recent:
        role = "model" if msg["role"] == "assistant" else "user"
        parts = []

        if msg.get("content"):
            parts.append({"text": msg["content"]})

        if msg.get("image_base64"):
            parts.append({
                "inlineData": {
                    "mimeType": msg.get("image_mime", "image/jpeg"),
                    "data": msg["image_base64"]
                }
            })
        if parts:
            contents.append({"role": role, "parts": parts})

    # Inject search context text directly into current prompt part
    if context and contents and contents[-1]["role"] == "user":
        context_text = f"\n\nReal-time web context:\n{json.dumps(context, indent=2)}"
        if contents[-1]["parts"] and "text" in contents[-1]["parts"][0]:
            contents[-1]["parts"][0]["text"] += context_text
        else:
            contents[-1]["parts"].insert(0, {"text": context_text})

    try:
        # Handle video integration using the cloud file pipeline if tracking video_path
        if video_path:
            print(f"Staging {video_path} into Gemini File API...")
            uploaded_cloud_file = client.files.upload(file=video_path)
            
            # Pool loop waiting for frames extraction processing
            while uploaded_cloud_file.state.name == "PROCESSING":
                print("Waiting for cloud file parsing processing...")
                time.sleep(3)
                uploaded_cloud_file = client.files.get(name=uploaded_cloud_file.name)
                
            if uploaded_cloud_file.state.name == "FAILED":
                raise Exception("Google cloud processing failed.")

            # Append the structured cloud handle straight into the prompt sequence
            # Reconstruct elements matching call parameters requirements
            formatted_contents = []
            for item in contents:
                role = item.get("role")
                parts_list = []
                for p in item.get("parts", []):
                    if "text" in p:
                        parts_list.append(p["text"])
                    elif "inlineData" in p:
                        parts_list.append({
                            "inline_data": {
                                "mime_type": p["inlineData"]["mimeType"],
                                "data": base64.b64decode(p["inlineData"]["data"])
                            }
                        })
                formatted_contents.append({"role": role, "parts": parts_list})

            # Inject the loaded reference handle into the final text sequence array position
            if formatted_contents:
                formatted_contents[-1]["parts"].insert(0, uploaded_cloud_file)

            response = client.models.generate_content(
                model=MODEL,
                contents=formatted_contents,
                config={"system_instruction": memory["system"]}
            )
            reply = response.text
        else:
            # Standard text and image generation
            reply = call_gemini_client(contents, memory["system"])

    except Exception as e:
        print(f"Error during execution pipeline: {e}")
        reply = f"An error occurred processing the request: {str(e)}"
    finally:
        # Cleanup routine tracking local block references and file indices copies
        if uploaded_cloud_file:
            try:
                client.files.delete(name=uploaded_cloud_file.name)
                print("Cleaned up cloud asset data.")
            except Exception as ce:
                print(f"Cloud file cleanup exception: {ce}")
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
            print("Cleaned up local temporary video file storage copy.")

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
