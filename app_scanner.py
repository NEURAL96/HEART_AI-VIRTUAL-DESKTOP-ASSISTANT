import os
import json

APP_DB_FILE = "installed_apps.json"


def scan_installed_apps():
    app_paths = {}

    search_paths = [
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        r"C:\Users\%USERNAME%\AppData\Local",
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"
    ]

    for base in search_paths:
        base = os.path.expandvars(base)
        for root, dirs, files in os.walk(base):
            for file in files:
                if file.endswith(".exe"):
                    name = file.replace(".exe", "").lower()
                    full_path = os.path.join(root, file)

                    if name not in app_paths:
                        app_paths[name] = full_path

    with open(APP_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(app_paths, f, indent=4)

    return app_paths


def load_apps():
    if not os.path.exists(APP_DB_FILE):
        return scan_installed_apps()

    with open(APP_DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
