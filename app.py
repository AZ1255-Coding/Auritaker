from flask import Flask, render_template, request, jsonify, session, redirect, send_from_directory
from flask_cors import CORS

from memory import get_memory, save_memory, trim
from tools.search import should_search, search_web
from ai_core import call_gemini, build_contents

import json
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "auritaker_secret")

CORS(app, supports_credentials=True, origins=[
    "https://az1255-coding.github.io"
])


# ---------------- USERS ---------------- #

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

@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        users = load_users()

        if users.get(u) == p:
            session["user"] = u
            return redirect("/")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        users = load_users()

        if u in users:
            return render_template("signup.html", error="User exists")

        users[u] = p
        save_users(users)

        session["user"] = u
        return redirect("/")

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- CHAT (AI ENGINE) ---------------- #

@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session:
        return jsonify({"response": "Not logged in"})

    user_input = request.json.get("message", "")

    memory = get_memory()

    # -------- TOOL: SEARCH -------- #
    context = None

    if should_search(user_input):
        context = search_web(user_input)

    if context:
        user_input = json.dumps({
            "message": user_input,
            "real_time_context": context
        })

    # -------- MEMORY -------- #
    memory["messages"].append({
        "role": "user",
        "content": user_input
    })

    memory = trim(memory)

    # -------- BUILD CONTEXT -------- #
    contents = build_contents(memory["messages"])

    # -------- AI CALL -------- #
    reply = call_gemini(contents, memory["system"])

    memory["messages"].append({
        "role": "assistant",
        "content": reply
    })

    save_memory(memory)

    return jsonify({"response": reply})


# ---------------- RUN ---------------- #

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 1000))
    app.run(host="0.0.0.0", port=port)
