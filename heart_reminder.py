import os
import json
import datetime

# ✅ Ensure we use the same 'heart_uploads' folder as your main script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "heart_reminder")
os.makedirs(UPLOAD_DIR, exist_ok=True)

REMINDER_FILE = os.path.join(UPLOAD_DIR, "heart_reminders.json")


def load_reminders():
    """Load reminders from the JSON file."""
    if not os.path.exists(REMINDER_FILE):
        return []
    try:
        with open(REMINDER_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []


def save_reminders(reminders):
    """Save the list of reminders back to the JSON file."""
    with open(REMINDER_FILE, 'w') as f:
        json.dump(reminders, f, indent=4)


def add_reminder(task: str, time_str: str):
    """Add a new reminder and return a confirmation message."""
    reminders = load_reminders()
    new_reminder = {
        "task": task,
        "time": time_str,
        "created_at": datetime.datetime.now().isoformat(),
        "triggered": False
    }
    reminders.append(new_reminder)
    save_reminders(reminders)
    return f"✅ Done! I will remind you about '{task}' at {time_str}."


def check_and_get_triggered():
    """Check for reminders that should trigger now. Returns a list of messages."""
    now = datetime.datetime.now()
    current_time_str = now.strftime("%H:%M")
    reminders = load_reminders()
    triggered_messages = []

    for r in reminders:
        if r['time'] == current_time_str and not r.get('triggered', False):
            triggered_messages.append(f"Hey D4RK, yaad dila rahi hoon: {r['task']}")
            r['triggered'] = True

    save_reminders(reminders)
    return triggered_messages