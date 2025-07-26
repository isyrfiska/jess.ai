import os
import json
import openai
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

# --- Database Setup ---
USER_DB = "users.json"

# --- OpenAI Client Setup ---
client = openai.OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=os.environ.get("OPENROUTER_API_KEY"),
)

# --- Data Helper Functions ---
def load_users():
    if not os.path.exists(USER_DB):
        with open(USER_DB, 'w') as f: json.dump({}, f)
        return {}
    try:
        with open(USER_DB, "r") as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_users(users_data):
    with open(USER_DB, "w") as f: json.dump(users_data, f, indent=4)

# --- Command Handlers ---
# NEW: Handles the "when... reply with..." command
def handle_training_command(message, user_data):
    """Saves a custom trigger and response for the user."""
    if message.startswith("when ") and " reply with " in message:
        try:
            parts = message.split(" reply with ", 1)
            trigger = parts[0].replace("when ", "").strip()
            response = parts[1].strip()
            
            user_data["custom_replies"][trigger] = response
            return f"✅ OK. When someone says '{trigger}', I will reply with '{response}'."
        except Exception:
            return "❌ Something went wrong. Please use the format: 'when [trigger], reply with [response]'."
    return None

def handle_memory_command(message, user_data):
    """Handles commands like 'remember...' or 'what is...'"""
    fact_to_remember = None
    if message.startswith("remember that"):
        fact_to_remember = message[13:].strip()
    elif message.startswith("remember"):
        fact_to_remember = message[8:].strip()

    if fact_to_remember:
        try:
            key, value = fact_to_remember.split(" is ", 1)
            user_data["memory"][key.strip()] = value.strip()
            return f"✅ Got it. I'll remember that **{key.strip()}** is **{value.strip()}**."
        except ValueError:
            return "🤔 To remember that properly, please phrase it like: 'remember [topic] **is** [detail]'."
    
    if message.startswith("what is"):
        key = message.replace("what is", "").replace("?", "").strip()
        answer = user_data["memory"].get(key)
        if answer:
            return f"💡 From my memory, **{key}** is **{answer}**."
        else:
            return f"🤔 I don't have a memory for '{key}'."
    return None

def handle_crm_command(message, user_data):
    """Handles simple CRM commands"""
    parts = message.split()
    if not parts: return None
    command = parts[0]

    if command == "new" and len(parts) > 2 and parts[1] == "client":
        name = parts[2].capitalize()
        phone = ""
        if "phone" in parts:
            phone_index = parts.index("phone")
            if phone_index + 1 < len(parts):
                phone = parts[phone_index + 1]
        user_data["crm"][name] = {"phone": phone, "notes": ""}
        return f"✅ New client **{name}** saved."

    if command == "note" and len(parts) > 2 and parts[1] == "for":
        name = parts[2].capitalize()
        if name in user_data["crm"]:
            note = " ".join(parts[3:])
            user_data["crm"][name]["notes"] = note
            return f"✅ Note added for **{name}**."
        else:
            return f"❌ Client '{name}' not found."

    if command == "find" and len(parts) > 1:
        name = parts[1].capitalize()
        client_data = user_data["crm"].get(name)
        if client_data:
            return f"Found client: **{name}**\nPhone: {client_data.get('phone', 'N/A')}\nNotes: {client_data.get('notes', 'N/A')}"
        else:
            return f"❌ Client '{name}' not found."
    return None

# --- Main Flask App ---
app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "Jess AI is running."

@app.route("/webhook", methods=["POST"])
def webhook():
    all_users = load_users()
    wa_from_number = request.values.get("From", "")
    user_profile = all_users.setdefault(wa_from_number, {
        "profile": {}, "memory": {}, "crm": {}, "custom_replies": {}
    })
    
    incoming_msg = request.values.get("Body", "").strip()
    response_text = None
    lower_msg = incoming_msg.lower()
    
    # --- Intent Router ---
    
    # NEW: First, check for a custom reply trigger. This has top priority.
    for trigger, response in user_profile.get("custom_replies", {}).items():
        if lower_msg == trigger.lower():
            response_text = response
            break # Exit the loop once a match is found
    
    if not response_text:
        response_text = handle_training_command(lower_msg, user_profile)
    if not response_text:
        response_text = handle_memory_command(lower_msg, user_profile)
    if not response_text:
        response_text = handle_crm_command(lower_msg, user_profile)
    
    # If no command was triggered, call the AI
    if not response_text:
        system_prompt = f"""You are Jess, a helpful AI assistant.
        The user's name is {user_profile.get('profile', {}).get('name', 'not set')}."""
        # ... (rest of AI call logic)
        response = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct:free",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": incoming_msg}
            ]
        )
        response_text = response.choices[0].message.content.strip()

    save_users(all_users)
    
    reply = MessagingResponse()
    reply.message(response_text)
    return str(reply)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
