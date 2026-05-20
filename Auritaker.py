import tkinter as tk
import customtkinter as ctk  
import threading
import json
from dotenv import load_dotenv
from flask import Flask
import requests 
import os
from tavily import TavilyClient 
import speech_recognition as sr #type: ignore
import pyttsx3
from openai import OpenAI
from dotenv import load_dotenv
    

# ---------------- CONFIG ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Tell it exactly where the file is
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, 'api.env'))

# Use this "Pro" way to load the file
script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(script_dir, "api.env"))

OPENROUTER_API_KEY = os.getenv ("OPENROUTER_API_KEY")
TAVILY_API_KEY = os.getenv ("TAVILY_API_KEY")

MODEL = "openrouter/free"

appdata = os.getenv("APPDATA")
MEMORY_FILE = os.path.join(appdata, "Auritaker", "ezi_memory.json")
os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)

ICON_FILE = os.path.join(BASE_DIR, "Futuristic_Auritaker_AI_icon.ico")

# ---------------- COLORS ----------------
BG = "#0f0f0f"
USER_COLOR = "#2563eb"
AI_COLOR = "#1f1f1f"
TEXT_COLOR = "#e5e5e5"

# ---------------- INIT ----------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

tavily = TavilyClient(api_key=TAVILY_API_KEY)


engine = pyttsx3.init()
engine.setProperty("rate", 185)  # smoother voice speed

# ---------------- SEARCH ----------------
def should_search(text):
    triggers = ["latest", "news", "today", "current", "who is", "what is", "when", "where", "released", "date", "year"]
    return any(t in text.lower() for t in triggers)

def web_search(query):
    try:
        results = tavily.search(query=query, max_results=2)
        snippets = [r.get("content") or r.get("snippet") or "" for r in results.get("results", [])]
        return "\n".join(snippets)[:800]
    except:
        return ""

# ---------------- STREAMING ----------------
def stream_ai_response(messages, on_chunk):
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "Auritaker"
        }

        data = {
            "model": MODEL,
            "messages": messages,
            "stream": True
        }

        with requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            stream=True,
            timeout=60
        ) as r:

            for line in r.iter_lines():
                if not line:
                    continue

                decoded = line.decode("utf-8", errors="ignore")

                if decoded.startswith("data: "):
                    chunk = decoded[6:]

                    if chunk.strip() == "[DONE]":
                        break

                    try:
                        json_data = json.loads(chunk)
                        delta = json_data["choices"][0]["delta"].get("content", "")
                        if delta:
                            on_chunk(delta)
                    except:
                        pass

    except Exception as e:
        on_chunk(f"\n[Error: {e}]")

# ---------------- MEMORY ----------------
SYSTEM_ROLE = (
    "You are Auritaker, a private high-intelligence AI system created on April 4th, 2026 "
    "and refined on April 5th, 2026. You communicate with calm precision and clarity, "
    "delivering accurate and structured responses. Use web data as truth when provided. "
    "If unsure, say you are not certain instead of guessing."
)

if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r") as f:
        chat_memory = json.load(f)
else:
    chat_memory = [{"role": "system", "content": SYSTEM_ROLE}]

def save_memory():
    try:
        with open(MEMORY_FILE, "w") as f:
            json.dump(chat_memory, f)
    except:
        pass

# ---------------- APP ----------------
class AuritakerAI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Auritaker AI")
        self.geometry("550x700")
        self.configure(fg_color=BG)

        if os.path.exists(ICON_FILE):
            try:
                self.iconbitmap(ICON_FILE)
            except:
                pass

        self.chat_frame = ctk.CTkScrollableFrame(self, fg_color=BG)
        self.chat_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.input_container = ctk.CTkFrame(self, fg_color="transparent")
        self.input_container.pack(fill="x", padx=20, pady=15)

        self.entry = ctk.CTkEntry(self.input_container, height=45)
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry.bind("<Return>", lambda e: self.send())

        self.send_btn = ctk.CTkButton(self.input_container, text="Send", command=self.send)
        self.send_btn.pack(side="right")

        self.voice_btn = ctk.CTkButton(self.input_container, text="🎤", width=50, command=self.listen_voice)
        self.voice_btn.pack(side="right", padx=5)

        self.add_bubble("Auritaker", "Welcome! I'm Auritaker. How can I assist you today?")

    # ---------------- CHAT ----------------
    def add_bubble(self, sender, text):
        frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        frame.pack(fill="x", pady=5)

        bubble = ctk.CTkLabel(
            frame,
            text=text,
            wraplength=350,
            fg_color=USER_COLOR if sender == "You" else AI_COLOR,
            text_color=TEXT_COLOR,
            padx=12,
            pady=10
        )

        bubble.pack(side="right" if sender == "You" else "left")
        self.chat_frame._parent_canvas.yview_moveto(1.0)

    # ---------------- SEND ----------------
    def send(self):
        user_input = self.entry.get().strip()
        if not user_input:
            return

        self.add_bubble("You", user_input)
        self.entry.delete(0, "end")

        threading.Thread(target=self.process_ai, args=(user_input,), daemon=True).start()

    # ---------------- VOICE ----------------
    def listen_voice(self):
        r = sr.Recognizer()

        try:
            with sr.Microphone() as source:
                self.add_bubble("Auritaker", "Listening...")
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=5)
        except:
            self.add_bubble("Auritaker", "Mic error.")
            return

        try:
            text = r.recognize_google(audio)
            self.entry.insert(0, text)
        except:
            self.add_bubble("Auritaker", "Couldn't understand.")

    # ---------------- SPEECH ----------------
    def speak(self, text):
        try:
            engine.say(text)
            engine.runAndWait()
        except:
            pass

    # ---------------- AI CORE ----------------
    def process_ai(self, user_input):
        frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        frame.pack(fill="x", pady=5)

        bubble = ctk.CTkLabel(
            frame,
            text="",
            wraplength=350,
            fg_color=AI_COLOR,
            text_color=TEXT_COLOR,
            padx=12,
            pady=10
        )
        bubble.pack(side="left")

        response_text = ""

        def on_chunk(chunk):
            nonlocal response_text
            response_text += chunk

            # smoother UI update
            self.after(0, lambda: bubble.configure(text=response_text))

        # WEB SEARCH
        if should_search(user_input):
            web = web_search(user_input)
            if web:
                user_input += f"\n\n[Web Info - Use as truth]:\n{web}"

        chat_memory.append({"role": "user", "content": user_input})

        stream_ai_response(chat_memory, on_chunk)

        chat_memory.append({"role": "assistant", "content": response_text})
        save_memory()

        threading.Thread(target=self.speak, args=(response_text,), daemon=True).start()

# ---------------- RUN ----------------
if __name__ == "__main__":
    app = AuritakerAI()
    app.mainloop()