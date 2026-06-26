from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory, Response
from flask_cors import CORS
from flask_session import Session  # Resolves 4KB client cookie overflow issue
from tavily import TavilyClient
import os, json, re, time
# Using the updated standalone package module
from ddgs import DDGS
# Import the official modern Google GenAI SDK
from google import genai
from google.genai import types

# ---------------- APP SETUP ---------------- #

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "auritaker_secret")

# Allow larger file payloads (up to 500 Megabytes) for videos
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

# Configure Server-Side File System Sessions
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
Session(app)

CORS(app, supports_credentials=True, origins=[
    "https://github.io"
])

MAX_MEMORY = 20

# ---------------- CONFIG & CLIENTS ---------------- #

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

# High-efficiency, fast multi-modal workhorse model
MODEL = "gemini-3.1-flash-lite"

# Initialize official GenAI client
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

SYSTEM_ROLE = """
You are Auritaker AI, a multimodal sports assistant.

RULES:
- Prioritize provided real-time context when available.
- If information is not in the provided context, use general knowledge when appropriate.
- Never fabricate specific facts.
- If information cannot be verified, say: "Not available in sources."
- Be concise and factual.
- When analyzing images or video clips, provide detailed insights about sports-related content.
- Don't be too obsessed about sports.
- If there's no info available, then do not say that some things (based on the prompt) did not happen. Say: "Sorry, but I couldn't find any information about" and whatever was asked for finding in the user's prompt. It is similar to the scratch code: "join (Sorry, but I couldn't find any information about ) ((whatever was asked to find in prompt))"
"""

BAD_DOMAINS = ["quora.com", "reddit.com", "medium.com"]

# ---------------- TAVILY & SEARCH ---------------- #

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


def web_search(query):
    try:
        # Restored context manager with correct keys
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        
        cleaned_results = []
        for item in results:
            url_link = item.get("url", "")
            if not any(b in url_link for b in BAD_DOMAINS):
                cleaned_results.append({
                    "title": item.get("title"),
                    "snippet": item.get("snippet") or item.get("body"),
                    "url": url_link
                })
        return {"query": query, "results": cleaned_results}
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
            session["memory"] = {"system": SYSTEM_ROLE, "messages": []}
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
        session["memory"] = {"system": SYSTEM_ROLE, "messages": []}
        return redirect("/")
    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- CHAT (MULTIMODAL WITH RESPONSE STREAMING OVERRIDES) ---------------- #

@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session:
        return jsonify({"response": "Not logged in"}), 401
    if not ai_client:
        return jsonify({"response": "Model error: GEMINI_API_KEY missing on server"}), 500

    # Extract request form details immediately before entering the generator scope
    raw_message = request.form.get("message", "")
    user_input = raw_message
    uploaded_file_obj = None

    # Access file mapping from frontend JS FormData key name 'file'
    if "file" in request.files:
        f = request.files["file"]
        if f and f.filename:
            uploaded_file_obj = f

    if not user_input.strip() and not uploaded_file_obj:
        return jsonify({"response": "Empty message and no attachment"}), 400

    memory = get_memory()

    # -------- WEB SEARCH -------- #
    context = None
    if user_input.strip() and should_search(user_input):
        context = web_search(user_input)
    if context:
        user_input += f"\n\nReal-time web context:\n{json.dumps(context, indent=2)}"

    def generate_stream():
        nonlocal user_input, uploaded_file_obj, memory, raw_message
        try:
            file_uri_to_store = None
            mime_type_to_store = None

            if uploaded_file_obj:
                # Save file securely inside an application-owned relative directory path
                temp_dir = os.path.join(os.getcwd(), "temp_uploads")
                os.makedirs(temp_dir, exist_ok=True)
                temp_path = os.path.join(temp_dir, uploaded_file_obj.filename)
                uploaded_file_obj.save(temp_path)
                
                print(f"Uploading {uploaded_file_obj.filename} to Gemini File API...")
                gemini_file = ai_client.files.upload(file=temp_path)
                
                # Asynchronous pooling loop with Keep-Alive stream pulses for proxies
                if "video" in gemini_file.mime_type.lower():
                    print("Video file detected. Waiting for Gemini backend processing...")
                    attempts = 0
                    while gemini_file.state.name == "PROCESSING" and attempts < 40:
                        time.sleep(2)
                        gemini_file = ai_client.files.get(name=gemini_file.name)
                        attempts += 1
                        print(f"Processing state: {gemini_file.state.name} (Loop {attempts})")
                    
                    if gemini_file.state.name != "ACTIVE":
                        raise ValueError(f"Video file processing failed or timed out. State: {gemini_file.state.name}")

                file_uri_to_store = gemini_file.uri
                mime_type_to_store = gemini_file.mime_type

                # Clean up local disk cache space
                if os.path.exists(temp_path):
                    os.remove(temp_path)

            # -------- UPDATE HISTORY STORAGE -------- #
            user_record = {
                "role": "user",
                "content": raw_message if raw_message.strip() else "[Media attachment shared]"
            }
            if file_uri_to_store:
                user_record["file_uri"] = file_uri_to_store
                user_record["mime_type"] = mime_type_to_store

            memory["messages"].append(user_record)
            recent = memory["messages"][-10:]

            # Build strictly verified Pydantic Content structures
            contents = []
            for msg in recent:
                role = "model" if msg["role"] == "assistant" else "user"
                parts = []
                
                if msg.get("content"):
                    text_content = msg["content"]
                    if msg == recent[-1] and role == "user" and context:
                        text_content = user_input
                    parts.append(types.Part.from_text(text=text_content))
                
                if msg.get("file_uri"):
                    parts.append(types.Part(
                        file_data=types.FileData(
                            file_uri=msg.get("file_uri"),
                            mime_type=msg.get("mime_type")
                        )
                    ))
                
                if parts:
                    contents.append(types.Content(role=role, parts=parts))

            # Send structures directly to generate content execution
            config = types.GenerateContentConfig(
                system_instruction=memory["system"]
            )
            response = ai_client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=config
            )
            reply = response.text.strip() if response.text else "Model returned an empty response."

            # Append results to thread session storage
            memory["messages"].append({
                "role": "assistant",
                "content": reply
            })

            memory["messages"] = memory["messages"][-MAX_MEMORY:]
            save_memory(memory)

            yield json.dumps({"response": reply})

        except Exception as e:
            print(f"Chat transaction failed: {e}")
            err_msg = repr(e)
            yield json.dumps({"response": f"Chat processing error: {err_msg}"})

    # Wrapping via an open Response stream tricks cloud host proxies into keeping the channel open
    return Response(generate_stream(), mimetype='application/json')


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 1000))
    app.run(host="0.0.0.0", port=port)
