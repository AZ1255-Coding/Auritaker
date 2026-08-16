from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory, Response, copy_current_request_context
from flask_cors import CORS
from flask_session import Session
from tavily import TavilyClient
import os, json, re, time, urllib.parse, requests
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
MODEL = "gemini-2.5-flash"
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

SYSTEM_ROLE = """You are Auritaker AI, a multimodal sports assistant. RULES: Prioritize context. Never fabricate facts. If unverified, say 'Not available in sources.' and provide reasoning. Be concise. NEVER output raw tool JSON like 'dalle.text2im' or function calling syntax; fulfill generation text directly."""

# ---------------- HELPER FUNCTIONS ---------------- #

def get_memory():
    if "memory" not in session:
        session["memory"] = {
            "system": SYSTEM_ROLE,
            "messages": []
        }
    return session["memory"]

def save_memory(mem):
    session["memory"] = mem

# ---------------- ROUTES ---------------- #

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    if not ai_client:
        return jsonify({"error": "Gemini API client not initialized. Check API Key."}), 500

    data = request.json or {}
    user_message = data.get("message", "").strip()
    file_info = data.get("file_info")

    memory = get_memory()
    
    user_entry = {"role": "user", "content": user_message}
    if file_info:
        user_entry["file_info"] = file_info
    
    memory["messages"].append(user_entry)
    
    if len(memory["messages"]) > MAX_MEMORY:
        memory["messages"] = memory["messages"][-MAX_MEMORY:]
    save_memory(memory)

    contents = []
    for msg in memory["messages"]:
        parts = []
        if msg.get("content"):
            parts.append(msg["content"])
            
        f_meta = msg.get("file_info")
        if f_meta and f_meta.get("file_uri"):
            parts.append(types.Part.from_uri(file_uri=f_meta["file_uri"], mime_type=f_meta["mime_type"]))
        elif msg.get("file_uri"):
            parts.append(types.Part.from_uri(file_uri=msg.get("file_uri"), mime_type=msg.get("mime_type")))
        
        if parts:
            contents.append(types.Content(role="model" if msg["role"] == "assistant" else "user", parts=parts))

    @copy_current_request_context
    def generate_stream():
        full_response_text = ""
        try:
            config_kwargs = {"system_instruction": memory["system"]}

            chat = ai_client.chats.create(
                model=MODEL,
                history=contents[:-1] if len(contents) > 1 else [],
                config=types.GenerateContentConfig(**config_kwargs)
            )
            
            latest_message = contents[-1] if contents else user_message
            response_stream = chat.send_message_stream(latest_message)

            for chunk in response_stream:
                if chunk.text:
                    full_response_text += chunk.text
                    yield chunk.text
                    
            if full_response_text:
                memory["messages"].append({"role": "assistant", "content": full_response_text})
                save_memory(memory)
                
        except Exception as e:
            yield f"\n[Chat processing error: {repr(e)}]"
    
    return Response(generate_stream(), mimetype='text/markdown')

# ---------------- CATCH-ALL ROUTE (AT THE VERY END) ---------------- #
@app.route("/<path:path>")
def catch_all(path):
    # Let missing API calls return a proper 404 JSON instead of HTML
    if path.startswith("api/"):
        return jsonify({"error": "API endpoint not found"}), 404
    # Fallback all other frontend routes (like /login, /signup) to index.html
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
