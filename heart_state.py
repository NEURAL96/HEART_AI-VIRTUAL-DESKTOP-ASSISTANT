import webbrowser
import threading
import os
import time
import asyncio
import logging
from enum import Enum
from typing import Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("H.E.A.R.T_HUD_SERVER")
app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class HeartState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    MUSIC = "MUSIC"
    SLEEP = "SLEEP"

class StatePayload(BaseModel):
    state: HeartState
    metadata: dict = {}

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.current_state: HeartState = HeartState.IDLE
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        await websocket.send_json({"state": self.current_state.value, "metadata": {}})

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, payload: dict):
        if not self.active_connections: return
        tasks = [self._safe_send(c, payload, []) for c in list(self.active_connections)]
        await asyncio.gather(*tasks)

    async def _safe_send(self, connection, payload, dead_list):
        try: await connection.send_json(payload)
        except: dead_list.append(connection)

    async def update_state(self, new_state: HeartState, metadata: dict = {}):
        async with self._lock:
            if new_state != self.current_state:
                self.current_state = new_state
                logger.info(f"[STATE CHANGE] → {new_state.value}")
                await self.broadcast({"state": new_state.value, "metadata": metadata})

manager = ConnectionManager()

@app.websocket("/ws/heart")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            payload = StatePayload.parse_raw(data)
            await manager.update_state(payload.state, payload.metadata)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/", response_class=HTMLResponse)
async def serve_hud():
    for name in ["index.html", "heart_hud.html"]:
        path = os.path.join(BASE_DIR, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f: return f.read()
    return "<h1>UI Not Found</h1>"

def start_hud():
    def run():
        print(f"🖥️ HUD Server: http://localhost:8002")
        print(f"💓 WS Endpoint: ws://localhost:8002/ws/heart")
        uvicorn.run(app, host="0.0.0.0", port=8002, log_level="warning")
    threading.Thread(target=run, daemon=True).start()
    time.sleep(1.5)
    webbrowser.open("http://localhost:8002/")