import re
import webbrowser
import requests
import json
import time
import subprocess
import sys
import os


# -----------------------------
# FUNCTION TOOL DECORATOR
# -----------------------------
def function_tool(name: str, description: str):
    def decorator(func):
        func._is_tool = True
        func._tool_name = name
        func._tool_description = description
        return func

    return decorator


# -----------------------------
# CONFIG
# -----------------------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


# =============================================
# MAIN EMAIL TOOL
# =============================================
@function_tool(
    name="send_email",
    description="Send professional email. Generates email and opens ready-to-send draft in Gmail."
)
def send_email(command: str, auto_send: bool = True) -> dict:
    """
    Main function for HEART Voice Assistant
    """
    print(f"📧 HEART Email Tool Activated: {command}")

    recipient_name, topic = extract_recipient_and_topic(command)
    if not recipient_name:
        return {"status": "error", "message": "Could not detect recipient"}

    if is_email(recipient_name):
        to_email = recipient_name
        to_name = None
    else:
        to_email = input(f"📧 Enter email for {recipient_name}: ").strip()
        to_name = recipient_name

    if not is_email(to_email):
        return {"status": "error", "message": "Invalid email address"}

    email_data = generate_natural_email(to_name, topic)

    print("\n📧 EMAIL GENERATED:")
    print(f"Subject: {email_data['subject']}")
    print(f"Body:\n{email_data['body']}\n")

    # Open Gmail with pre-filled content (Ready in Draft)
    open_email_web(to_email, email_data['subject'], email_data['body'])

    return {
        "status": "draft_ready",
        "message": f"✅ Gmail compose window opened with ready draft for {to_email}",
        "subject": email_data['subject']
    }


# =============================================
# HELPER FUNCTIONS
# =============================================
def is_email(text: str) -> bool:
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", text))


def extract_recipient_and_topic(command: str):
    clean = re.sub(r'(send email to|send to|email to|mail to)', '', command, flags=re.I).strip()
    if ' about ' in clean.lower():
        parts = clean.split(' about ', 1)
        return parts[0].strip(), parts[1].strip()
    words = clean.split()
    return words[0] if words else clean, " ".join(words[1:]) if len(words) > 1 else "general discussion"


def generate_natural_email(to_name: str, topic: str):
    name_part = to_name if to_name else "there"
    prompt = f"""You are a professional and friendly executive assistant.
Write a natural, human-sounding email.

Recipient: {name_part}
Topic: {topic}

Requirements:
- Warm professional tone
- Unique and natural
- Excellent subject line
- Concise body (4-7 sentences)
- Polite call to action
- Output ONLY JSON: {{"subject": "...", "body": "..."}}"""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={"model": "nex-agi/nex-n2-pro:free", "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.7, "max_tokens": 600},
            timeout=30
        )
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content'].strip()
            try:
                return json.loads(content)
            except:
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
    except:
        pass

    # Fallback
    return {
        "subject": f"Regarding {topic}",
        "body": f"Hi {name_part},\n\nI'm reaching out about {topic}.\n\nBest regards,\nYour Assistant"
    }


def open_email_web(to_email="", subject="", body=""):
    """Open Gmail with pre-filled content (Ready Draft)"""
    # URL Encoding
    subject = subject.replace(" ", "%20")
    body = body.replace(" ", "%20").replace("\n", "%0A").replace("&", "%26")

    url = f"https://mail.google.com/mail/u/0/?view=cm&fs=1&to={to_email}&su={subject}&body={body}"

    webbrowser.open(url)
    print("🌐 Gmail compose window opened with ready draft!")
    print("💡 Just review and press Ctrl + Enter to send")


# =============================================
# DIRECT TEST / DEBUG
# =============================================
if __name__ == "__main__":
    print("🚀 HEART Email Tool Ready (Selenium Removed)")
    print("Now opens ready Gmail draft when you say 'send email'")

    while True:
        cmd = input("\nCommand (or quit): ").strip()
        if cmd.lower() in ['quit', 'exit']:
            break
        if any(k in cmd.lower() for k in ['send email', 'email to', 'send to', 'mail to']):
            result = send_email(cmd, auto_send=True)
            print(f"\nResult: {result}")