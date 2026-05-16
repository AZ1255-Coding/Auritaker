from flask import Flask, request, jsonify, session, redirect, render_template
import requests, os, json
from flask_cors import CORS
from tavily import TavilyClient

app = Flask(__name__)

# 1. ALLOW GITHUB TO TALK TO RENDER
CORS(app, supports_credentials=True, origins=["https://az1255-coding.github.io"])

# Required for Conversation Memory (Sessions)
app.secret_key = os.environ.get("SECRET_KEY", "auritaker_secret_999")

# 2. LOAD KEYS FROM RENDER ENVIRONMENT
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

MODEL = "openrouter/free"
SYSTEM_ROLE = "You are Auritaker, a high-intelligence AI. Be sharp, witty, and direct."

# 3. SAFETY CHECK FOR TAVILY
tavily = None
if TAVILY_API_KEY:
    try:
        tavily = TavilyClient(api_key=TAVILY_API_KEY)
    except Exception as e:
        print(f"Tavily failed to start: {e}")

# ---------------- ROUTES ----------------

@app.route("/", methods=["GET"])
def home():
    # Serves index.html from your 'templates' folder if you visit the Render URL directly
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    if not OPENROUTER_API_KEY:
        return jsonify({"response": "Server Error: OpenRouter API Key is missing."})

    data = request.json
    user_input = data.get("message", "")

    # Manage Conversation Memory
    if "memory" not in session:
        session["memory"] = [{"role": "system", "content": SYSTEM_ROLE}]
    
    memory = session["memory"]

    # Web Search logic
    if tavily and any(k in user_input.lower() for k in ["search", "latest", "news", "who is"]):
        try:
            res = tavily.search(query=user_input, max_results=2)
            context = "\n".join([r["content"] for r in res["results"]])
            current_query = f"[Real-time info]: {context}\n\nUser: {user_input}"
        except:
            current_query = user_input
    else:
        current_query = user_input

    # Add user message to memory
    memory.append({"role": "user", "content": current_query})

    # Call OpenRouter with the last 10 messages for context
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": MODEL,
                "messages": memory[-10:] 
            }
        )
        result = response.json()
        reply = result['choices'][0]['message']['content']
        
        # Add AI reply to memory and save session
        memory.append({"role": "assistant", "content": reply})
        session["memory"] = memory
        
        return jsonify({"response": reply})
    except Exception as e:
        return jsonify({"response": f"AI Error: {str(e)}"})

@app.route("/clear")
def clear_chat():
    session.pop("memory", None)
    return jsonify({"status": "Memory cleared"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
