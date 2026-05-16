from flask import Flask, request, jsonify, session, render_template
import requests, os
from flask_cors import CORS 
from tavily import TavilyClient

app = Flask(__name__)

# 1. Direct CORS for your GitHub site
CORS(app, supports_credentials=True, origins=["https://az1255-coding.github.io"])

# 2. Secret key for memory/sessions
app.secret_key = os.environ.get("SECRET_KEY", "auritaker_default_999")

# 3. Load Keys safely from Render (not local files)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

MODEL = "openrouter/free"
SYSTEM_ROLE = "You are Auritaker, a sharp AI built in 2026. Answer directly."

# 4. Initialize Tavily safely (This stops the Status 1 crash!)
tavily = None
if TAVILY_API_KEY:
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
    except:
        print("Tavily failed to initialize.")

@app.route("/", methods=["GET"])
def home():
    return "Auritaker API is Running!"

@app.route("/chat", methods=["POST"])
def chat():
    if not OPENROUTER_API_KEY:
        return jsonify({"response": "Error: OpenRouter Key missing."})

    user_input = request.json.get("message", "")

    # Handle Conversation Memory
    if "memory" not in session:
        session["memory"] = [{"role": "system", "content": SYSTEM_ROLE}]
    
    memory = session["memory"]

    # Simple Search Logic
    if tavily and "search" in user_input.lower():
        try:
            res = tavily.search(query=user_input, max_results=2)
            context = "\n".join([r["content"] for r in res["results"]])
            user_input = f"[Search Data]: {context}\n\nUser: {user_input}"
        except:
            pass

    memory.append({"role": "user", "content": user_input})

    # Call OpenRouter
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={"model": MODEL, "messages": memory[-10:]},
            timeout=25
        )
        reply = response.json()['choices'][0]['message']['content']
        memory.append({"role": "assistant", "content": reply})
        session["memory"] = memory
        return jsonify({"response": reply})
    except Exception as e:
        return jsonify({"response": f"AI Error: {str(e)}"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
