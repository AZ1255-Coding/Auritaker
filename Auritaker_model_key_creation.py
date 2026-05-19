import json
import secrets
import sqlite3
import urllib.request
from flask import Flask, request, jsonify

app = Flask(__name__)
DB_FILE = "auritaker.db"

# Initialize local SQLite database
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key TEXT PRIMARY KEY,
                user_label TEXT
            )
        """)
init_db()

# Automatically generate a master key on startup so you don't need test scripts
def auto_generate_master_key():
    master_key = "at_local_2bcf9b0fde13c49293f2f4c2d067a0cf"
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key FROM api_keys WHERE key = ?", (master_key,))
        if not cursor.fetchone():
            conn.execute("INSERT INTO api_keys (key, user_label) VALUES (?, 'Master_Bro')", (master_key,))
    print("\n" + "="*50)
    print(f"🔑 YOUR ACTIVE AURITAKER API KEY IS AUTHORISED:")
    print(f"👉 {master_key}")
    print("="*50 + "\n")

# --- NEW ROUTE: Click this link in your web browser to test! ---
@app.route("/test_auritaker", methods=["GET"])
def test_via_browser():
    ollama_url = "http://localhost:11434/api/chat"
    payload = {
        "model": "auritaker-aura-1", 
        "messages": [
            {"role": "system", "content": "You are Auritaker, a high-intelligence AI built in April 2026. Be sharp, witty, and direct. Skip the self-introductions unless asked. Just answer and be helpful."},
            {"role": "user", "content": "Yo bro! Give me an epic prompt for how humanity harnesses wind energy."}
        ],
        "stream": False 
    }
    try:
        req = urllib.request.Request(
            ollama_url, 
            data=json.dumps(payload).encode("utf-8"), 
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
        return f"<h1>Auritaker Engine Reply:</h1><p>{result['message']['content']}</p>"
    except Exception as e:
        return f"<h1>Error:</h1><p>{str(e)}</p><p>Make sure Ollama is open in your Windows taskbar tray!</p>"

@app.route("/generate_key", methods=["POST"])
def generate_key():
    data = request.get_json() or {}
    user_label = data.get("user", "anonymous_bro")
    new_key = f"at_local_{secrets.token_hex(16)}"
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT INTO api_keys (key, user_label) VALUES (?, ?)", (new_key, user_label))
    return jsonify({"status": "success", "api_key": new_key, "assigned_to": user_label})

@app.route("/v1/auritaker/chat", methods=["POST"])
def chat():
    user_key = request.headers.get("X-Auritaker-Key")
    if not user_key:
        return jsonify({"error": "Missing key header"}), 401
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_label FROM api_keys WHERE key = ?", (user_key,))
        row = cursor.fetchone()
    if not row:
        return jsonify({"error": "Invalid API key"}), 403

    data = request.get_json() or {}
    user_prompt = data.get("prompt", "")
    if not user_prompt:
        return jsonify({"error": "Missing prompt"}), 400

    ollama_url = "http://localhost:11434/api/chat"
    payload = {
        "model": "auritaker-aura-1", 
        "messages": [
            {"role": "system", "content": "You are Auritaker, a high-intelligence AI built in April 2026. Be sharp, witty, and direct. Skip the self-introductions unless asked. Just answer and be helpful."},
            {"role": "user", "content": user_prompt}
        ],
        "stream": True 
    }

    try:
        req = urllib.request.Request(
            ollama_url, 
            data=json.dumps(payload).encode("utf-8"), 
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            
        return jsonify({
            "model": "auritaker-aura-1",
            "reply": result["message"]["content"]
        })
    except Exception as e:
        return jsonify({"error": f"Failed talking to local Ollama engine: {str(e)}"}), 500

if __name__ == "__main__":
    auto_generate_master_key()
    app.run(port=5000, debug=True, use_reloader=False)
