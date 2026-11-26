
import webbrowser
import threading
import os
import time
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def serve_hud():
    #  Check for multiple possible filenames to guarantee it finds yours
    possible_names = ["index.html", "heart_hud.html", "HEAR_HUD.HTML"]

    for filename in possible_names:
        file_path = os.path.join(BASE_DIR, filename)
        if os.path.exists(file_path):
            print(f" Successfully loaded UI file: {filename}")
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()


@app.get("/{filename}")
async def serve_static(filename: str):
    file_path = os.path.join(BASE_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "Not found"}


def start_hud():
    def start_server():
        print(f"H.E.A.R.T HUD Server running at http://localhost:8002")
        print(f"Serving UI files from: {BASE_DIR}")
        uvicorn.run(app, host="0.0.0.0", port=8002, log_level="warning")

    threading.Thread(target=start_server, daemon=True).start()
    time.sleep(1.5)
    webbrowser.open("http://localhost:8002/")