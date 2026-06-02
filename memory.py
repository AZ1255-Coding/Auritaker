import json
from flask import session
from config import SYSTEM_ROLE

def init_memory():
    if "memory" not in session:
        session["memory"] = {
            "system": SYSTEM_ROLE,
            "messages": []
        }

def get_memory():
    init_memory()
    return session["memory"]

def save_memory(memory):
    session["memory"] = memory

def trim(memory, limit=12):
    memory["messages"] = memory["messages"][-limit:]
    return memory
