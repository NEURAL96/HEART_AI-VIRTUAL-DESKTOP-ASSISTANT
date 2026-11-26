from __future__ import annotations
from heart_reminder import add_reminder
from heart_conversation_controll import HeartConversationControl
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import uvicorn
from neural_schema import PolicyEngine, ActionRequest, Context, DecisionType
policy_engine = PolicyEngine()
heart_ctrl = HeartConversationControl()
import ctypes
import uuid
import threading
import time
import sys
import os
import logging
import warnings
import asyncio
from livekit import rtc
from livekit.agents import AgentServer, AgentSession, Agent, room_io
from livekit.plugins import silero
from livekit.agents import RunContext
from livekit.agents.llm import function_tool, ChatContext
from livekit.plugins import google
from livekit.plugins import noise_cancellation as lk_nc
from HEART_SYSTEM_PROMPT import HEART_SYSTEM_PROMPT
from brain import HeartBrain, ToolMetadata, RiskLevel, DecisionType
import inspect
import keyboard
import shutil
from heart_memory import init_memory_engine, save_memory, recall_memory
import heart_hud
from livekit import agents
import pyautogui
import psutil
from datetime import datetime
import platform
from heart_search import search_agent

from heart_music_engine import play_track
try:
    from pynvml import (
        nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex,
        nvmlDeviceGetName, nvmlDeviceGetUtilizationRates,
        nvmlDeviceGetMemoryInfo, nvmlDeviceGetTemperature,
        NVMLError, NVML_TEMPERATURE_GPU
    )

    PYNVML_AVAILABLE = True
    nvmlInit()
except (ImportError, NVMLError):
    PYNVML_AVAILABLE = False

try:

    import torch

    TORCH_CUDA_AVAILABLE = torch.cuda.is_available()
except ImportError:
    TORCH_CUDA_AVAILABLE = False
from coding_agent import HeartCodingAgent
coding_agent = HeartCodingAgent()
from heart_expert_ppt import expert_creator
from typing import Optional

# =========================================================================
# H.E.A.R.T FILE RECEIVER & MEMORY
# =========================================================================
#  FIX 1: Use absolute path so the AI can ALWAYS find the folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "heart_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
CURRENT_FILE_PATH: Optional[str] = None
_last_memory_save = 0.0
_MEMORY_SAVE_DEBOUNCE = 2.0  # Seconds between memory saves
upload_app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

upload_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


#  FIX 2: Add a GET route so visiting localhost:8001 doesn't show "Not Found"
@upload_app.get("/")
async def receiver_status():
    return {
        "status": "ONLINE",
        "message": "H.E.A.R.T File Receiver is active. Upload files via the HUD (Port 8002).",
        "current_file": os.path.basename(CURRENT_FILE_PATH) if CURRENT_FILE_PATH else "None"
    }


@upload_app.post("/api/upload")
async def receive_file(file: UploadFile = File(...)):
    global CURRENT_FILE_PATH

    #  FIX 3: Save using the absolute path
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    CURRENT_FILE_PATH = file_path
    print(f" [RECEIVER] File successfully saved to: {CURRENT_FILE_PATH}")

    return JSONResponse(content={
        "status": "SUCCESS",
        "file_name": file.filename,
        "message": "File secured in H.E.A.R.T memory. Ready for commands."
    })


def run_upload_server():
    uvicorn.run(upload_app, host="0.0.0.0", port=8001, log_level="warning")
emergency_active: bool = False
_current_agent = None

load_dotenv(".env.local.local")
import atexit

def _emergency_save():

    print("[Memory] Real-time memory saving is active. Clean exit.")



def load_apps():
    apps = {}
    try:
        from win32com.client import Dispatch as dispatch
        shell = dispatch('WScript.Shell')
        # All users start menu
        start_menu_path = shell.SpecialFolders("Programs")
        # Current user start menu
        user_start_menu = shell.SpecialFolders("StartMenu")
        paths = [start_menu_path, user_start_menu]
        for path in paths:
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.endswith('.lnk'):
                        shortcut_path = os.path.join(root, file)
                        shortcut = shell.CreateShortCut(shortcut_path)
                        target = shortcut.TargetPath
                        if target and os.path.isfile(target):
                            name = file[:-4].strip()
                            apps[name] = target
    except Exception as e:
        print(f"Error loading apps: {e}")
    # Add hardcoded system apps only
    if 'notepad' not in [name.lower() for name in apps]:
        apps['Notepad'] = 'notepad.exe'
    if 'file explorer' not in [name.lower() for name in apps]:
        apps['File Explorer'] = 'explorer.exe'
    if 'calculator' not in [name.lower() for name in apps]:
        apps['Calculator'] = 'calc.exe'
    if 'cmd' not in [name.lower() for name in apps]:
        apps['Command Prompt'] = 'cmd.exe'
    if 'powershell' not in [name.lower() for name in apps]:
        apps['PowerShell'] = 'powershell.exe'
    if 'task manager' not in [name.lower() for name in apps]:
        apps['Task Manager'] = 'taskmgr.exe'
    return apps


# Load installed apps once
apps = load_apps()

class Assistant(Agent):
    def __init__(self, dynamic_instructions: str, chat_ctx: ChatContext):
        super().__init__(instructions=dynamic_instructions, chat_ctx=chat_ctx)
        self.brain = HeartBrain()
        self.stop_emergency = None
        asyncio.create_task(self._auto_register_tools())

    async def _auto_register_tools(self):
        """
        Automatically scans the Assistant class for all @function_tool methods
        and registers them into the HeartBrain Registry with appropriate Risk Levels.
        """
        await self.brain.initialize()

        # Define Risk Mapping based on function names
        HIGH_RISK_KEYWORDS = ["system", "shutdown", "restart", "delete", "uninstall", "format", "emergency"]
        MEDIUM_RISK_KEYWORDS = ["send", "email", "whatsapp", "file_manager", "install", "code"]

        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            # Check if the method has the 'function_tool' attribute added by LiveKit decorator
            if hasattr(method, '__livekit_function_tool__'):

                # Determine Risk Level
                risk_level = RiskLevel.LOW
                name_lower = name.lower()

                if any(kw in name_lower for kw in HIGH_RISK_KEYWORDS):
                    risk_level = RiskLevel.HIGH
                elif any(kw in name_lower for kw in MEDIUM_RISK_KEYWORDS):
                    risk_level = RiskLevel.MEDIUM

                # Extract description from the docstring or decorator if available
                description = f"Executes the {name} action. Refer to system instructions for details."

                # Register into Brain
                self.brain.registry.register(ToolMetadata(
                    name=name,
                    description=description,
                    handler=method,
                    risk_level=risk_level,
                    tags=[name.split('_')[0]]
                ))
#=================================================================================#
        @function_tool(
            name="set_reminder",
            description="""Set a reminder for the user. 
            Example: 'Remind me to take medicine at 5 PM' or 'Yaad dilana 8 baje meeting hai'.
            Time should be in 24-hour format (e.g., 17:00 for 5 PM)."""
        )
        async def set_reminder(self, context: RunContext, task: str, time_str: str) -> str:
            _ = context
            try:
                # Call the function from our new heart_reminder.py file
                return add_reminder(task, time_str)
            except Exception as e:
                return f"Failed to set reminder: {str(e)}"
        # ====================== NEURAL GOVERNANCE TOOL (Approach 3) ======================
        @function_tool(
            name="neural_govern_action",
            description="""Call this BEFORE doing any risky action.
            Risky actions: shutdown, restart, delete file/folder, install/uninstall apps, send whats
            app, emergency mode, system changes, etc.
            Do NOT call for normal tasks like time, weather, open app, play music, search, etc."""
        )
        async def neural_govern_action(
                self,
                context: RunContext,
                module: str,
                action: str,
                parameters: str = "{}",
                emergency_override: bool = False
        ) -> str:
            _ = context
            try:
                import json
                params = json.loads(parameters) if isinstance(parameters, str) else parameters

                # Emergency Override for Owner
                if emergency_override:
                    return "NEURAL_DECISION: ALLOWED | Emergency Owner Override Activated"

                # Normal Neural Check
                gov = await self._run_neural_check(module, action, params)

                if gov["allowed"]:
                    return f"NEURAL_DECISION: ALLOWED | Risk Level: {gov['risk_level']}"
                else:
                    return f"NEURAL_DECISION: BLOCKED | Reason: {gov['message']}"

            except Exception as e:
                return f"NEURAL_DECISION: ERROR | {str(e)}"

        async def _run_neural_check(self, module: str, action: str, parameters: dict):
            """Internal check using your Neural Schema"""
            request = ActionRequest(
                module=module,
                action=action,
                parameters=parameters,
                context=Context(
                    user_id="D4RK",
                    session_id=str(uuid.uuid4()),
                    intent=f"{module}.{action}"
                )
            )

            decision = policy_engine.process_action(request)

            return {
                "allowed": decision.decision_type == DecisionType.ALLOW,
                "risk_level": decision.risk_report.risk_level.name,
                "message": decision.explanation or "Action evaluated by Neural Constitution"
            }

    @function_tool(
        name="heart_security_utility",
        description="""Security and performance monitoring tool for Heart Assistant.
    - Returns real-time system report including CPU, RAM, Disk, Network, and GPU (0 & 1 if available)
    - Detects high resource usage and generates security alerts
    - Lists active processes that may be using microphone, camera, or location
    - Suggests redirects to Privacy settings or Task Manager for permission management
    - Supports one-time checks or continuous live monitoring"""
    )
    async def heart_security_utility(
            live_mode: bool = False,
            duration_seconds: int = 60
    ) -> str:
        """
        Real-time system monitoring and privacy check (optimized for Windows).
        Returns a formatted multi-line string report.
        """
        if platform.system() != "Windows":
            return "This monitoring tool is currently optimized for Windows systems only."

        report_lines = []
        report_lines.append("Heart Security & Performance Monitoring Report")
        report_lines.append("=" * 80)
        report_lines.append(f"Report generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")

        def get_gpu_status() -> str:
            """Collect GPU usage, memory, and temperature (NVIDIA priority)."""
            gpu_lines = []

            # NVIDIA GPU monitoring (using nvidia-ml-py)
            if PYNVML_AVAILABLE:
                try:
                    device_count = nvmlDeviceGetCount()
                    for i in range(min(device_count, 2)):
                        handle = nvmlDeviceGetHandleByIndex(i)
                        name = nvmlDeviceGetName(handle).decode('utf-8')
                        util = nvmlDeviceGetUtilizationRates(handle)
                        mem_info = nvmlDeviceGetMemoryInfo(handle)
                        temp = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)

                        gpu_lines.append(
                            f"GPU {i}: {name}\n"
                            f"   Utilization: {util.gpu}% | "
                            f"Memory Used: {mem_info.used / 1024 ** 3:.1f} / {mem_info.total / 1024 ** 3:.1f} GB\n"
                            f"   Temperature: {temp}°C"
                        )
                    if gpu_lines:
                        return "\n".join(gpu_lines)
                except Exception:
                    pass

            # Fallback for CUDA (via PyTorch)
            if TORCH_CUDA_AVAILABLE:
                try:
                    for i in range(min(torch.cuda.device_count(), 2)):
                        name = torch.cuda.get_device_name(i)
                        allocated = torch.cuda.memory_allocated(i) / 1024 ** 3
                        reserved = torch.cuda.memory_reserved(i) / 1024 ** 3
                        gpu_lines.append(
                            f"GPU {i} (CUDA/Torch): {name}\n"
                            f"   Memory Allocated: {allocated:.1f} GB\n"
                            f"   Memory Reserved:  {reserved:.1f} GB"
                        )
                    if gpu_lines:
                        return "\n".join(gpu_lines)
                except Exception:
                    pass

            return "No GPU detected or GPU monitoring libraries not available."

        def generate_report():
            nonlocal report_lines

            cpu_percent = psutil.cpu_percent(interval=1)
            ram_percent = psutil.virtual_memory().percent
            disk_percent = psutil.disk_usage('C:\\').percent
            net_io = psutil.net_io_counters()

            ts = datetime.now().strftime('%H:%M:%S')
            report_lines.append(f"[{ts}] SYSTEM PERFORMANCE SNAPSHOT")
            report_lines.append(f"  CPU Usage:          {cpu_percent:6.1f}%")
            report_lines.append(f"  RAM Usage:          {ram_percent:6.1f}%")
            report_lines.append(f"  Disk Usage (C:):    {disk_percent:6.1f}%")
            report_lines.append(f"  Network Sent:       {net_io.bytes_sent / (1024 * 1024):.1f} MB")
            report_lines.append(f"  Network Received:   {net_io.bytes_recv / (1024 * 1024):.1f} MB")

            report_lines.append("\nGPU STATUS (if available)")
            report_lines.append(get_gpu_status())

            # Top CPU consumers
            top_processes = sorted(
                psutil.process_iter(['name', 'cpu_percent', 'memory_percent']),
                key=lambda p: p.info['cpu_percent'], reverse=True
            )[:6]

            report_lines.append("\nTop 6 CPU-consuming processes:")
            for proc in top_processes:
                report_lines.append(
                    f"  • {proc.info['name']:<25} | CPU: {proc.info['cpu_percent']:5.1f}% | "
                    f"RAM: {proc.info['memory_percent']:5.1f}%"
                )

            # Security & performance alerts
            alerts = []
            if cpu_percent > 85:
                alerts.append("HIGH CPU USAGE DETECTED - possible background mining or malware activity")
            if ram_percent > 90:
                alerts.append("CRITICAL RAM USAGE - system performance may degrade")
            if disk_percent > 95:
                alerts.append("DISK SPACE NEARLY EXHAUSTED - immediate cleanup recommended")

            if alerts:
                report_lines.append("\nSECURITY & PERFORMANCE ALERTS:")
                for alert in alerts:
                    report_lines.append(f"  {alert}")

            # Basic privacy/process check
            report_lines.append("\nACTIVE PROCESSES (potential microphone/camera/location users)")
            try:
                cmd = (
                    "Get-Process | Where-Object {$_.MainWindowTitle} | "
                    "Select-Object Name, Id, CPU | Sort-Object CPU -Descending | Select-Object -First 10"
                )
                result = subprocess.run(
                    ['powershell', '-Command', cmd],
                    capture_output=True,
                    text=True,
                    timeout=8
                )
                output = result.stdout.strip() or "No active windowed processes detected"
                report_lines.append(output)
            except Exception:
                report_lines.append("Privacy/process details unavailable (run as Administrator for full access)")

            report_lines.append("\nPermission Management:")
            report_lines.append("  → Press 'P' → Open Windows Privacy & Security settings")
            report_lines.append("  → Press 'T' → Open Task Manager for detailed process inspection")

        # Run monitoring
        if live_mode:
            report_lines.append(f"\nLIVE MONITORING MODE ENABLED ({duration_seconds} seconds)")
            report_lines.append("Press Ctrl+C in the terminal to stop monitoring early\n")
            try:
                start_time = time.time()
                while time.time() - start_time < duration_seconds:
                    await asyncio.to_thread(generate_report)
                    await asyncio.sleep(5)
            except KeyboardInterrupt:
                report_lines.append("\nLive monitoring stopped by user.")
        else:
            await asyncio.to_thread(generate_report)

        report_lines.append("\n" + "=" * 80)
        report_lines.append("Heart Security Utility - Report Complete")
        report_lines.append("Protect your personal data and stay vigilant.")

        return "\n".join(report_lines)

    # ====================== ADVANCED VOICE + TOOL BRIDGE ======================
    def process_request(request: dict) -> dict:
        """Full power bridge - connects to main Assistant + tools"""
        try:
            req_type = request.get("type")

            if req_type == "text":
                message = request.get("message", "").strip()

                if not message:
                    return {"response": "I am listening...", "mode": "voice_ready"}

                # Try to route through main agent
                if _current_agent is not None:
                    try:
                        # Here we can trigger tool calls based on intent
                        response = f"[VOICE MODE] HEART heard: {message}\n\nActivating tools..."
                        # Future: You can call specific tools here
                        return {
                            "response": response,
                            "status": "success",
                            "voice_reply": True,
                            "tools_available": True
                        }
                    except:
                        pass

                return {
                    "response": f"HEART Voice Assistant Online. You said: {message}",
                    "status": "success",
                    "mode": "voice"
                }

            elif req_type == "file":
                return {
                    "response": "File received. Analyzing with full tools...",
                    "status": "success"
                }

            return {"status": "error", "response": "Unknown command"}

        except Exception as e:
            return {"status": "error", "response": str(e)}
    @function_tool(
        name="smart_send_file_to_contact",
        description="""Sends the most recently uploaded file from H.E.A.R.T's memory to a contact on WhatsApp Desktop. 
        Just provide the contact name. The actual file is taken directly from the HUD upload."""
    )
    async def smart_send_file_to_contact(self, context: RunContext, contact_name: str) -> str:
        _ = context

        # Pre-check in async context (fast, no blocking)
        if not CURRENT_FILE_PATH or not os.path.exists(CURRENT_FILE_PATH):
            return "No file found in H.E.A.R.T's active memory. Please upload a file via the HUD (Press 'M') first."

        found_file_path = CURRENT_FILE_PATH
        print(f" [WHATSAPP] Sending actual file from memory: {found_file_path}")

        def _send_file_sync():
            """All blocking pyautogui/win32gui calls run here safely."""
            import time
            import pyautogui
            import win32gui
            import win32con
            import pyperclip

            pyautogui.FAILSAFE = False

            # ================== WHATSAPP FOCUS ==================
            hwnd = win32gui.FindWindow(None, "WhatsApp")
            if hwnd:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                time.sleep(0.4)
            else:
                pyautogui.hotkey('win', 's')
                time.sleep(0.7)
                pyautogui.write('whatsapp')
                time.sleep(0.6)
                pyautogui.press('enter')
                time.sleep(7)

            # ================== SEARCH CONTACT ==================
            pyautogui.hotkey('ctrl', 'f')
            time.sleep(1.0)
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.press('delete')
            time.sleep(0.5)
            pyautogui.write(contact_name)
            time.sleep(2.0)
            pyautogui.press('enter')
            time.sleep(1.8)

            # ================== ATTACH FILE ==================
            pyautogui.hotkey('ctrl', 'shift', 'm')
            time.sleep(1.6)
            pyautogui.press('tab', presses=3)
            pyautogui.press('enter')
            time.sleep(2.5)

            pyperclip.copy(found_file_path)
            pyautogui.hotkey('ctrl', 'l')
            time.sleep(0.5)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1.0)
            pyautogui.press('enter')
            time.sleep(2.5)

            # ================== FINAL SEND ==================
            pyautogui.press('enter')
            time.sleep(1.5)
            pyautogui.press('enter')
            time.sleep(1.5)

            return f"Actual file '{os.path.basename(found_file_path)}' successfully sent to {contact_name}!"

        try:

            return await asyncio.to_thread(_send_file_sync)
        except Exception as e:
            return f"Error: {str(e)}\nMake sure WhatsApp Desktop is open and visible."
    @function_tool(
        name="generate_code",
        description="""When user asks to write, generate, bana do, likh do, code, program, script, function, class, coding kar do, create code — ALWAYS call this tool immediately.
        Supports Python, JS, Bash, Java, C++, Go, Rust. Auto-installs dependencies and runs code safely."""
    )
    async def generate_code(self, context: RunContext, request: str) -> str:
        _ = context
        try:
            # Use the global agent instance we created earlier
            result = await coding_agent.handle_coding(request, auto_run=True)
            return result
        except Exception as e:
            return f"Code generation failed: {str(e)}"
    @function_tool(
        name="create_expert_presentation",
        description="Creates a 10-slide, human-expert level PowerPoint. H.E.A.R.T performs deep research for each section, uses smart text wrapping to prevent overflow, selects cinematic images, and applies morph transitions. Takes time to ensure perfection."
    )
    async def create_expert_presentation(self, context: RunContext, topic: str) -> str:
        _ = context
        path = await asyncio.to_thread(expert_creator.generate_expert_ppt, topic)
        return f"Expert-level presentation created: {path}. Opening it now..."

    @function_tool(
        name="handle_apps",
        description="Open, close, install or uninstall applications. Also handles IDEs like VS Code."
    )
    @function_tool(name="handle_apps", description="Open, close, install or uninstall applications.")
    async def handle_apps(self, context: RunContext, text: str) -> str:
        _ = context

        def _handle_sync():
            global apps
            t = text.lower().strip()

            if t.startswith("open "):
                name = t[5:].strip()
                try:
                    pyautogui.press('win')
                    time.sleep(0.5)
                    pyautogui.typewrite(name)
                    time.sleep(0.5)
                    pyautogui.press('enter')
                    return f"{name} opened."
                except Exception as e:
                    return f"Failed to open {name}: {e}"

            if t.startswith("close "):
                name = t[6:].strip()
                closed_any = False
                for process in psutil.process_iter(['name', 'exe']):
                    proc_name = process.info['name']
                    proc_exe = process.info['exe']
                    if proc_name and (name in proc_name.lower() or (proc_exe and name in proc_exe.lower())):
                        try:
                            process.terminate()
                            closed_any = True
                        except Exception as e:
                            return f"Failed to close {proc_name}: {e}"
                return f"{name} closed." if closed_any else "Application not running."

            if t.startswith("install "):
                name = t[8:].strip()
                try:
                    args = [
                        "winget", "install", "-e", "--id", name,
                        "--accept-package-agreements", "--accept-source-agreements",
                    ]
                    return start_winget(args, f"Installation of {name}")
                except Exception as e:
                    return f"Installation failed: {e}"

            if t.startswith("uninstall "):
                name = t[10:].strip()
                try:
                    return start_winget(["winget", "uninstall", name], f"Uninstall of {name}")
                except Exception as e:
                    return f"Uninstall failed: {e}"

            return "App command not understood."

        def start_winget(args, action):
            process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            def refresh_apps_when_done():
                global apps
                return_code = process.wait()
                if return_code == 0:
                    apps = load_apps()
                else:
                    logging.getLogger("HEART").error(
                        "%s failed with exit code %s", action, return_code
                    )

            threading.Thread(target=refresh_apps_when_done, daemon=True).start()
            return f"{action} started in the background (PID {process.pid}); completion is not confirmed yet."

        return await asyncio.to_thread(_handle_sync)

    @function_tool(
        name="input_control",
        description="Advanced HEART Input Control: mouse, keyboard, window, screenshot, summarization, save to notepad, rewrite, delete text, folder management, and more."
    )
    async def input_control(
            self,
            context: RunContext,
            action: str,

            # Mouse Control
            x: int = None,
            y: int = None,
            duration: float = 0.5,
            pixels: int = 100,
            amount: int = 100,  # for scroll
            clicks: int = 1,
            button: str = "left",

            # Keyboard
            text: str = None,
            key: str = None,
            keys: list = None,
            interval: float = 0.05,

            # Summarization & Text Processing
            topic: str = None,
            instruction: str = None,  # for rewrite_summary (e.g. "shorter", "improve")

            # File & Summary Management
            filename: str = None,
            folder: str = None,
            folder_name: str = None,
            filepath: str = None,

            # Screenshot
            save_as: str = None,
            region: tuple = None,

    ) -> str:

        _ = context  # unused

        try:
            from heart_mouse import HeartInput

            # Pass everything to HeartInput.control()
            return await HeartInput.control(
                action=action,
                x=x,
                y=y,
                text=text,
                key=key,
                keys=keys,
                pixels=pixels,
                save_as=save_as,
                region=region,
                duration=duration,
                amount=amount,
                clicks=clicks,
                button=button,
                topic=topic,
                instruction=instruction,
                filename=filename,
                folder=folder,
                folder_name=folder_name,
                filepath=filepath,
                interval=interval,
            )

        except ImportError:
            return "Error: Could not import HeartInput from heart_mouse.py"
        except Exception as e:
            return f" Input control failed: {str(e)}"

    @function_tool(
        name="get_weather",
        description="Get current weather for a city."
    )
    async def get_weather(self, context: RunContext, city: str) -> str:
        _ = context

        key = os.getenv("OPENWEATHER_API_KEY")
        if not key:
            return "Weather service is not configured. Set OPENWEATHER_API_KEY in .env.local."

        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=metric"

        try:
            response = await asyncio.to_thread(requests.post, url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                temp = data['main']['temp']
                desc = data['weather'][0]['description']
                return f"Weather in {city}: {temp}°C, {desc}."
            else:
                return f"Weather fetch failed: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Weather fetch failed: {str(e)}"

    @function_tool(
        name="get_time",
        description="Get the exact current time. Default is India (IST). You can also ask for international time by specifying a city or country (e.g., 'New York', 'London', 'Dubai')."
    )
    async def get_time(self, context: RunContext, location: str = "India") -> str:
        _ = context

        try:
            import pytz
            from datetime import datetime

            #  STEP 1: Map common names to official Timezone IDs
            tz_map = {
                "india": "Asia/Kolkata",
                "hindustan": "Asia/Kolkata",
                "bharat": "Asia/Kolkata",
                "delhi": "Asia/Kolkata",
                "mumbai": "Asia/Kolkata",
                "kolkata": "Asia/Kolkata",
                "new york": "America/New_York",
                "london": "Europe/London",
                "dubai": "Asia/Dubai",
                "tokyo": "Asia/Tokyo",
                "paris": "Europe/Paris",
                "sydney": "Australia/Sydney"
            }

            # Get the official timezone ID
            tz_id = tz_map.get(location.lower(), location)

            # If it's not in our map, try to use it as a raw timezone ID (e.g., "Asia/Kolkata")
            try:
                tz = pytz.timezone(tz_id)
                display_name = location.title()
            except:
                # If all else fails, default to India
                tz = pytz.timezone("Asia/Kolkata")
                display_name = "India (IST)"

            now = datetime.now(tz)
            date_str = now.strftime("%d %B %Y")
            time_str = now.strftime("%I:%M %p")
            tz_abbr = now.tzname()
            return f"Aaj ki tareekh hai {date_str} aur waqt hai **{time_str}** ({display_name} - {tz_abbr})."

        except Exception as e:
            print(f" [TIME] Timezone lookup failed, using India time: {e}")
            try:
                import pytz
                from datetime import datetime
                # Force IST for fallback to ensure at least India time is correct
                tz = pytz.timezone("Asia/Kolkata")
                now = datetime.now(tz)
                date_str = now.strftime("%d %B %Y")
                time_str = now.strftime("%I:%M %p")
                return f"Aaj ki tareekh hai {date_str} aur waqt hai **{time_str}** (India - IST). [Source: System Clock]"
            except:
                return "Time service unavailable."

    import re
    import os
    import shutil

    @function_tool(
        name="file_manager",
        description="Manage files: list, search, open, read, create, delete, rename, move, or separate data. If no path is given for reading, it uses the last uploaded file."
    )
    async def file_manager(self, context: RunContext, action: str = "read", path: str = "", new_path: str = None,
                           item_type: str = "file") -> str:
        _ = context

        # SMART LOGIC: Auto-detect uploaded file if no path is provided
        if not path or path == "C:/":
            if action in ["read", "open", "separate"] and CURRENT_FILE_PATH:
                path = CURRENT_FILE_PATH
                print(f" [FILE MANAGER] Auto-detected uploaded file: {path}")

        path = os.path.expanduser(path)  # Handle ~ for home dir

        if action == "list":
            try:
                files = os.listdir(path)
                return f"Files in {path}:\n" + "\n".join(files[:20]) + ("\n... (truncated)" if len(files) > 20 else "")
            except Exception as e:
                return f"Failed to list files: {str(e)}"

        elif action == "search":
            if not new_path:
                return "Search term required in new_path."
            try:
                def search_files():
                    found = []
                    for root, dirs, files in os.walk(path):
                        for file in files:
                            if new_path.lower() in file.lower():
                                found.append(os.path.join(root, file))
                    return found

                found = await asyncio.to_thread(search_files)
                return f"Found files matching '{new_path}':\n" + "\n".join(found[:20])
            except Exception as e:
                return f"Failed to search: {str(e)}"

        elif action == "open":
            try:
                os.startfile(path)
                return f"Opened {path}."
            except Exception as e:
                return f"Failed to open {path}: {str(e)}"

        elif action == "read":
            try:
                if str(path).lower().startswith("http://") or str(path).lower().startswith("https://"):
                    return f"Error: I cannot read web URLs directly. Use the local path: {CURRENT_FILE_PATH}"

                def read_file():
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        return f.read()

                content = await asyncio.to_thread(read_file)
                return f"Content of {os.path.basename(path)}:\n{content[:2000]}..."
            except Exception as e:
                return f"Failed to read {path}: {str(e)}"

        elif action == "move":
            if not new_path:
                return "Error: 'new_path' (destination folder) is required to move a file."
            try:
                dest_dir = os.path.dirname(new_path)
                if dest_dir and not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)

                shutil.move(path, new_path)
                return f" Successfully moved '{os.path.basename(path)}' to '{new_path}'."
            except Exception as e:
                return f"Failed to move file: {str(e)}"

        elif action == "separate":
            """Separates data from a document (e.g., splits a CSV or text file into smaller parts)"""
            try:
                def separate_file():
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    filename = os.path.basename(path)
                    name, ext = os.path.splitext(filename)
                    output_folder = os.path.join(os.path.dirname(path), f"{name}_separated")
                    os.makedirs(output_folder, exist_ok=True)
                    lines = content.splitlines()
                    if len(lines) < 2:
                        return "File is too small to separate."

                    chunk_size = 10
                    chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]
                    created_files = []
                    for i, chunk in enumerate(chunks):
                        chunk_path = os.path.join(output_folder, f"{name}_part_{i + 1}{ext}")
                        with open(chunk_path, 'w', encoding='utf-8') as f_out:
                            f_out.write("\n".join(chunk))
                        created_files.append(os.path.basename(chunk_path))

                    return (
                        f" Separated '{filename}' into {len(chunks)} parts in folder: "
                        f"'{os.path.basename(output_folder)}'.\nFiles: {', '.join(created_files[:5])}"
                    )

                return await asyncio.to_thread(separate_file)

            except Exception as e:
                return f"Failed to separate data: {str(e)}"

        elif action == "create":
            try:
                if item_type == "dir":
                    os.makedirs(path, exist_ok=True)
                    return f"Directory {path} created."
                else:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    open(path, 'a').close()
                    return f"File {path} created."
            except Exception as e:
                return f"Failed to create: {str(e)}"

        elif action == "delete":
            try:
                if item_type == "dir":
                    shutil.rmtree(path)
                    return f"Directory {path} deleted."
                else:
                    os.unlink(path)
                    return f"File {path} deleted."
            except Exception as e:
                return f"Failed to delete: {str(e)}"

        elif action == "rename":
            if new_path:
                try:
                    os.rename(path, new_path)
                    return f"Renamed {path} to {new_path}."
                except Exception as e:
                    return f"Failed to rename: {str(e)}"
            else:
                return "New path required for rename."

        return "Command not understood. Use: list, search, open, read, move, separate, create, delete, or rename."
    @function_tool(
        name="system_control",
        description="Control system functions like volume, brightness, shutdown, restart, sleep, lock (use cautiously). For volume, requires pycaw and comtypes (pip install pycaw comtypes)."
    )
    async def system_control(self, context: RunContext, action: str, value: str = None) -> str:
        _ = context
        sys = platform.system()
        if sys != "Windows":
            return "System control currently supports Windows only."
        if action == "shutdown":
            # WARNING: This will shut down the PC immediately - use with care!
            await asyncio.to_thread(subprocess.call, ["shutdown", "/s", "/t", "0"])
            return "Shutting down the system."
        elif action == "restart":
            await asyncio.to_thread(subprocess.call, ["shutdown", "/r", "/t", "0"])
            return "Restarting the system."
        elif action == "sleep":
            await asyncio.to_thread(os.system, "rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            return "Putting system to sleep."
        elif action == "lock":
            ctypes.windll.user32.LockWorkStation()
            return "System locked."
        elif action == "volume":
            try:
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                vol = interface.QueryInterface(IAudioEndpointVolume)
                current = vol.GetMasterVolumeLevelScalar()
                if value == "up":
                    vol.SetMasterVolumeLevelScalar(min(1.0, current + 0.1), None)
                    return "Volume increased."
                elif value == "down":
                    vol.SetMasterVolumeLevelScalar(max(0.0, current - 0.1), None)
                    return "Volume decreased."
                elif value == "mute":
                    vol.SetMute(1, None)
                    return "Volume muted."
                elif value.isdigit():
                    level = float(int(value) / 100)
                    vol.SetMasterVolumeLevelScalar(level, None)
                    return f"Volume set to {value}%."
                else:
                    return "Specify 'up', 'down', 'mute', or a number 0-100 for volume."
            except ImportError:
                return "pycaw or comtypes not installed. Use pip install pycaw comtypes for full volume control."
            except Exception as e:
                return f"Volume control failed: {str(e)}"
        elif action == "brightness":
            try:
                import screen_brightness_control as sbc  # pip install screen-brightness-control
                current = sbc.get_brightness()
                if isinstance(current, list):
                    current = current[0]  # Take first display if multiple
                if value == "up":
                    sbc.set_brightness(min(100, current + 10))
                    return "Brightness increased."
                elif value == "down":
                    sbc.set_brightness(max(0, current - 10))
                    return "Brightness decreased."
                else:
                    try:
                        level = int(value.strip('% ').strip())
                        sbc.set_brightness(level)
                        return f"Brightness set to {level}%."
                    except ValueError:
                        return "Invalid brightness value. Use number or number%."
            except ImportError:
                return "screen-brightness-control not installed. Use pip install screen-brightness-control."
            except Exception as e:
                return f"Brightness control failed: {str(e)}"
        return "System control command not understood."

    @function_tool(
        name="media_control",
        description="Control media playback (play/pause/resume, next, previous). Windows-specific using key simulation. Resume is same as play/pause toggle."
    )
    async def media_control(self, context: RunContext, action: str) -> str:
        _ = context
        try:
            pyautogui.FAILSAFE = False  # Disable failsafe
            if action in ["play_pause", "resume"]:
                pyautogui.press('playpause')
                return "Media play/paused/resumed."
            elif action == "next":
                pyautogui.press('nexttrack')
                return "Next track."
            elif action == "previous":
                pyautogui.press('prevtrack')
                return "Previous track."
            else:
                return "Media command not understood. Use 'play_pause', 'resume', 'next', or 'previous'."
        except Exception as e:
            return f"Media control failed: {str(e)}"

    @function_tool(
        name="detect_mood",
        description="Detect mood from user text (simple sentiment analysis)."
    )
    async def detect_mood(self, context: RunContext, text: str) -> str:
        _ = context
        try:
            from textblob import TextBlob  # Requires pip install textblob
            blob = TextBlob(text)
            sentiment = blob.sentiment.polarity
            if sentiment > 0.5:
                return "Positive/Happy mood."
            elif sentiment < -0.5:
                return "Negative/Sad mood."
            else:
                return "Neutral mood."
        except ImportError:
            return "textblob not installed. Use pip install textblob for mood detection."
        except Exception as e:
            return f"Mood detection failed: {str(e)}"

    @function_tool(
        name="play_music",
        description="Play music from YouTube/Spotify. Provides vibe summary."
    )
    async def play_music(self, context: RunContext, path_or_query: str, genre: str = None,
                         source: str = "local", suggest: bool = False) -> str:
        _ = context

        result = await play_track(path_or_query, source=source, genre=genre, suggest=suggest)

        intel = result.get('intelligence', {})
        asyncio.create_task(save_memory(f"User played '{path_or_query}'. Vibe: {intel.get('vibe')}."))

        return result['status']
    @function_tool(
        name="handle_pdf",
        description="Handle PDF files: open, extract text, or merge (requires pypdf)."
    )
    async def handle_pdf(self, context: RunContext, action: str, file_path: str, other_files: str = "",
                         output_path: str = "merged.pdf") -> str:
        _ = context
        file_path = os.path.expanduser(file_path)
        if action == "open":
            try:
                os.startfile(file_path)
                return f"Opened PDF: {file_path}."
            except Exception as e:
                return f"Failed to open PDF: {str(e)}"
        elif action == "extract_text":
            try:
                def extract_text_sync():
                    from pypdf import PdfReader
                    reader = PdfReader(file_path)
                    return "\n".join(page.extract_text() or "" for page in reader.pages)

                text = await asyncio.to_thread(extract_text_sync)
                return f"Extracted text from {file_path}:\n{text[:2000]}..."  # Increased limit
            except ImportError:
                return "pypdf not installed. Use pip install pypdf for PDF handling."
            except Exception as e:
                return f"PDF extraction failed: {str(e)}"
        elif action == "merge":
            try:
                def merge_sync():
                    from pypdf import PdfMerger
                    merger = PdfMerger()
                    try:
                        merger.append(file_path)
                        for f in other_files.split(','):
                            merger.append(os.path.expanduser(f.strip()))
                        merger.write(os.path.expanduser(output_path))
                    finally:
                        merger.close()

                await asyncio.to_thread(merge_sync)
                return f"PDFs merged to {output_path}."
            except ImportError:
                return "pypdf not installed. Use pip install pypdf for PDF handling."
            except Exception as e:
                return f"PDF merge failed: {str(e)}"
        return "PDF command not understood. Use 'open', 'extract_text', or 'merge'."

    @function_tool(
        name="web_intelligence",
        description="""Unified web assistant for H.E.A.R.T. Handles three actions securely:
        1. 'search' - Searches the internet and provides a summary. Does NOT open browser. Requires 'query'.
        2. 'open' - Opens a specific result from the last search by number. Requires 'result_index' (e.g., 1, 2).
        3. 'navigate' - Finds a place and opens Google Maps navigation. Requires 'query' as destination.
        Always specify the 'action' parameter first."""
    )
    async def web_intelligence(
            self,
            context: RunContext,
            action: str,
            query: str = "",
            result_index: int = 0
    ) -> str:
        _ = context
        action = action.lower().strip()
        if action == "search":
            return await search_agent.async_search_web(query)
        elif action == "open":
            return await search_agent.async_open_result(result_index)
        elif action == "navigate":
            return await search_agent.async_navigate_to(query)
        else:
            return f" Unknown action '{action}'. Use: search, open, or navigate."
    @function_tool(
        name="get_love_quote",
        description="Get a random love quote. Requires QUOTES_API_KEY from api-ninjas.com in .env.local.local."
    )
    async def get_love_quote(self, context: RunContext) -> str:
        _ = context
        key = os.getenv("QUOTES_API_KEY")
        if not key:
            return "API key not set for quotes. Add QUOTES_API_KEY to .env.local.local (get from api-ninjas.com)."
        url = "https://api.api-ninjas.com/v1/quotes?category=love"
        try:
            response = await asyncio.to_thread(
                requests.post, url, headers={'X-Api-Key': key}, timeout=5
            )
            if response.status_code == 200:
                data = response.json()[0]  # Returns list of 1
                return f"\"{data['quote']}\" - {data['author']}"
            else:
                return f"Could not get quote: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Quote fetch failed: {str(e)}"

    emergency_active = False

    @function_tool(
        name="send_heart_live_location_emergency",
        description="Heart की लाइव लोकेशन WhatsApp Desktop से trusted contacts को भेजता है। इमरजेंसी मोड में हर 60 सेकंड में अपडेट भेजता रहेगा। Ctrl+Alt+S से रोक सकते हैं।"
    )
    async def send_heart_live_location_emergency(self, context: RunContext) -> str:
        global emergency_active

        if emergency_active:
            return "इमरजेंसी पहले से चल रही है। Ctrl+Alt+S दबाकर रोकें।"

        emergency_active = True

        try:
            trusted_contacts = ["Mummy", "papa jii"]
            search_bar_x = 203
            search_bar_y = 140

            def get_live_location() -> str:
                try:
                    resp = requests.post('https://ipinfo.io/json', timeout=6)
                    data = resp.json()
                    city = data.get('city', 'Unknown')
                    region = data.get('region', 'Unknown')
                    country = data.get('country', 'Unknown')
                    loc = data.get('loc', 'Unknown')
                    ts = time.strftime("%I:%M %p")
                    return f" Heart लाइव लोकेशन ({ts}):\n{city}, {region}, {country}\nLat/Long: {loc}"
                except Exception:
                    return f"लोकेशन नहीं मिली ({time.strftime('%I:%M %p')})"

            def focus_and_send(contact: str, message: str) -> bool:
                try:
                    pyautogui.hotkey('win', 's')
                    time.sleep(0.7)
                    pyautogui.write('whatsapp')
                    time.sleep(0.7)
                    pyautogui.press('enter')
                    time.sleep(2.5)

                    pyautogui.hotkey('ctrl', 'f')
                    time.sleep(1.0)
                    pyautogui.click(x=search_bar_x, y=search_bar_y)
                    time.sleep(0.8)

                    pyautogui.hotkey('ctrl', 'a')
                    pyautogui.press('backspace')
                    time.sleep(0.4)

                    pyautogui.write(contact)
                    time.sleep(0.8)
                    pyautogui.press('down')
                    pyautogui.press('enter')
                    time.sleep(3.5)

                    pyautogui.write(message)
                    time.sleep(0.8)
                    pyautogui.press('enter')
                    time.sleep(1.5)
                    return True
                except Exception as err:
                    print(f"{contact} fail: {err}")
                    return False

            def emergency_loop():
                global emergency_active
                while emergency_active:
                    loc = get_live_location()
                    msg = f" HEART EMERGENCY UPDATE\n{loc}\n need help"
                    for contact in trusted_contacts:
                        focus_and_send(contact, msg)
                    time.sleep(60)

            # MUST BE OUTSIDE THE LOOP
            def stop_emergency():
                global emergency_active
                emergency_active = False
                print(" Emergency Stopped by Assistant/User")

            self.stop_emergency = stop_emergency

            import threading
            threading.Thread(target=emergency_loop, daemon=True).start()
            keyboard.add_hotkey('ctrl+alt+s', stop_emergency)

            return " HEART EMERGENCY MODE ACTIVATED!\n\nAssistant को बोलें:\n\"stop emergency\" या \"emergency band kar do\""

        except Exception as err:
            emergency_active = False
            return f"problem: {str(err)}"

    @function_tool(
        name="get_horoscope",
        description="Get daily motivation"
    )
    async def get_horoscope(self, context: RunContext, zodiac: str, date: str = None) -> str:
        _ = context
        key = os.getenv("QUOTES_API_KEY")
        if not key:
            return "API key not set for horoscope."
        url = f"https://api.api-ninjas.com/v1/horoscope?sign={zodiac.lower()}"
        if date:
            url += f"&date={date}"  # Format: YYYY-MM-DD
        try:
            response = await asyncio.to_thread(
                requests.post, url, headers={'X-Api-Key': key}, timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                return f"Horoscope for {zodiac.capitalize()}: {data['horoscope']}"
            else:
                return f"Could not get horoscope: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Horoscope fetch failed: {str(e)}"


@function_tool(name="send_whatsapp_desktop", description="""Send message via Desktop WhatsApp app.""")
async def send_whatsapp_desktop(self, context: RunContext, contact_name: str, message: str = None,
                                file_path: str = None) -> str:
    _ = context

    def _send_sync():
        import pyautogui, win32gui, win32con, time, os
        pyautogui.FAILSAFE = False

        hwnd = win32gui.FindWindow(None, "WhatsApp")
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(1.0)
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            time.sleep(0.8)
        else:
            pyautogui.hotkey('win', 's')
            time.sleep(0.7)
            pyautogui.write('whatsapp')
            time.sleep(0.6)
            pyautogui.press('enter')
            time.sleep(3.0)

        pyautogui.hotkey('ctrl', 'f')
        time.sleep(0.8)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')
        time.sleep(0.5)
        pyautogui.write(contact_name)
        time.sleep(1.8)
        pyautogui.press('enter')
        time.sleep(2.0)

        if file_path and os.path.exists(file_path):
            pyautogui.hotkey('ctrl', 'shift', 'm')
            time.sleep(1.5)
            pyautogui.write(file_path)
            time.sleep(0.8)
            pyautogui.press('enter')
            time.sleep(2.0)

        if message:
            pyautogui.write(message)
            time.sleep(0.6)
            pyautogui.press('enter')

        return f"Message sent successfully to '{contact_name}'"

    try:
        return await asyncio.to_thread(_send_sync)
    except Exception as e:
        return f"Desktop WhatsApp failed: {str(e)}\nMake sure WhatsApp Desktop is installed and visible."
def _create_backup(full_path: str) -> tuple[bool, str]:
    """
    Create timestamped backup copy before modification.
    Returns (success: bool, message: str)
    """
    if not os.path.exists(full_path):
        return False, "No backup needed (file did not exist)"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = os.path.splitext(full_path)
    backup_path = f"{base}_backup_{timestamp}{ext}"

    try:
        shutil.copy2(full_path, backup_path)
        return True, f"Backup created: {os.path.basename(backup_path)}"
    except Exception as e:
        return False, f"Backup failed: {str(e)}"


@function_tool(
    name="manage_heart_note",
    description="""Manages heart-related notes, moods, feelings, quotes, memories etc.

Supported operations:
  append   - add new entry at the end (default)
  write    - overwrite the entire file
  edit     - replace content of a specific line (needs line_number & data)
  delete   - remove a line by number (needs line_number)
  rename   - change filename (needs new_file_name)

Every call requires folder and file_name.
Folder is created automatically if it does not exist.
Timestamps are added automatically on append & write.

Examples:
manage_heart_note(folder="C:/Diary", file_name="mood.txt", data="Feeling calm today ")
manage_heart_note(folder="C:/Diary", file_name="mood.txt", operation="edit",   line_number=3, data="New version of line 3")
manage_heart_note(folder="C:/Diary", file_name="mood.txt", operation="delete", line_number=5)
manage_heart_note(folder="C:/Diary", file_name="mood.txt", operation="rename", new_file_name="mood_2026.txt")
"""
)
async def manage_heart_note(
        self,
        context,
        folder: str,
        file_name: str,
        operation: str = "append",
        data: Optional[str] = None,
        line_number: Optional[int] = None,
        new_file_name: Optional[str] = None,
) -> str:
    """
    Manage emotional / heart-related notes with full control.
    """
    try:
        folder = folder.strip()
        file_name = file_name.strip()
        operation = operation.lower().strip()

        if not folder:
            return "Error: folder path is required"
        if not file_name:
            return "Error: file_name is required"

        full_path = os.path.join(folder, file_name)

        # Create folder if needed
        os.makedirs(folder, exist_ok=True)

        if operation in ("append", "write"):
            if not data:
                return "Error: 'data' is required for append/write"

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = f"[{timestamp}] {data.strip()}"

            if operation == "append":
                exists = os.path.exists(full_path)
                with open(full_path, "a", encoding="utf-8") as f:
                    if exists and os.path.getsize(full_path) > 0:
                        f.write("\n")
                    f.write(entry + "\n")
                action = "appended"
            else:  # write
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(entry + "\n")
                action = "overwritten"

            return (
                f"Note successfully {action}\n"
                f"File     : {file_name}\n"
                f"Folder   : {folder}\n"
                f"Full path: {full_path}\n"
                f"Entry    : {entry}"
            )

        elif operation == "edit":
            if line_number is None or data is None:
                return "Error: 'line_number' and 'data' are both required for edit"

            if not os.path.exists(full_path):
                return f"File not found: {full_path}"

            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if line_number < 1 or line_number > len(lines):
                return f"Invalid line number. File has {len(lines)} lines (1–{len(lines)})."

            old_content = lines[line_number - 1].rstrip("\n")
            lines[line_number - 1] = data.rstrip() + "\n"

            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            return (
                f"Line {line_number} updated successfully\n"
                f"File     : {file_name}\n"
                f"Old text : {old_content}\n"
                f"New text : {data}"
            )

        elif operation == "delete":
            if line_number is None:
                return "Error: 'line_number' is required for delete"

            if not os.path.exists(full_path):
                return f"File not found: {full_path}"

            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if line_number < 1 or line_number > len(lines):
                return f"Invalid line number. File has {len(lines)} lines (1–{len(lines)})."

            removed = lines.pop(line_number - 1).rstrip("\n")

            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            return (
                f"Line {line_number} deleted\n"
                f"File     : {file_name}\n"
                f"Removed  : {removed}"
            )

        elif operation == "rename":
            if not new_file_name:
                return "Error: 'new_file_name' is required for rename"

            new_file_name = new_file_name.strip()
            new_path = os.path.join(folder, new_file_name)

            if not os.path.exists(full_path):
                return f"Source file not found: {full_path}"

            if os.path.exists(new_path):
                return f"Target already exists: {new_path}"

            os.rename(full_path, new_path)

            return (
                f"File renamed successfully\n"
                f"Old name : {file_name}\n"
                f"New name : {new_file_name}\n"
                f"Folder   : {folder}"
            )

        else:
            return "Invalid operation. Allowed: append, write, edit, delete, rename"

    except PermissionError:
        return f"Permission denied: {full_path}\nCheck folder permissions."
    except Exception as e:
        return f"Operation failed: {str(e)}"


import re
import webbrowser
import requests
import subprocess


# =============================================
# MAIN EMAIL TOOL
# =============================================
@function_tool(
    name="send_email",
    description="Create a Gmail draft. Include the recipient's exact email address in command and provide draft_subject and draft_body when available. This opens a draft only; it does not send."
)
async def send_email(
        command: str,
        draft_subject: str = "",
        draft_body: str = "",
) -> dict:
    """
    Create a draft without blocking the realtime voice event loop.
    """
    recipient_name, topic = extract_recipient_and_topic(command)
    if not recipient_name:
        return {"status": "error", "message": "Could not detect recipient"}

    if not is_email(recipient_name):
        return {
            "status": "error",
            "message": f"Please provide the exact email address for {recipient_name}.",
        }

    email_data = {
        "subject": draft_subject.strip() or f"Regarding {topic}",
        "body": draft_body.strip() or (
            f"Hi there,\n\nI'm reaching out about {topic}.\n\nBest regards,\nYour Assistant"
        ),
    }
    await asyncio.to_thread(
        open_email_web,
        recipient_name,
        email_data["subject"],
        email_data["body"],
    )

    return {
        "status": "draft_ready",
        "message": f"Gmail draft opened for {recipient_name}. Review it before sending.",
        "subject": email_data["subject"],
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


def open_email_web(to_email="", subject="", body=""):
    """Open Gmail with pre-filled content (Ready Draft)"""
    from urllib.parse import urlencode

    url = "https://mail.google.com/mail/u/0/?" + urlencode({
        "view": "cm",
        "fs": "1",
        "to": to_email,
        "su": subject,
        "body": body,
    })

    if not webbrowser.open(url):
        raise RuntimeError("Could not open the Gmail draft in a browser.")
    print(" Gmail compose window opened with ready draft!")


@function_tool(
    name="monitor_whatsapp_incoming",
    description="""WhatsApp Web ko Brave browser mein khol kar incoming messages monitor karegi.
Naya message aate hi padhegi, sender bata degi, aur reply suggest karegi.
Pehli baar QR code scan karna padega."""
)
async def monitor_whatsapp_incoming(self, context: RunContext, sender_name: str = None,
                                    check_interval_sec: int = 3) -> str:
    _ = context
    try:
        def open_whatsapp():
            from selenium import webdriver

            brave_path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
            options = webdriver.ChromeOptions()
            options.binary_location = brave_path
            options.add_argument(
                "--user-data-dir=C:\\Users\\Tilak Kumar\\AppData\\Local\\BraveSoftware\\Brave-Browser\\User Data"
            )
            driver = webdriver.Chrome(options=options)
            driver.get("https://web.whatsapp.com")
            return driver

        driver = await asyncio.to_thread(open_whatsapp)
        print("WhatsApp Web opened in Brave. Scan the QR code if prompted.")

        def latest_incoming_message():
            messages = driver.find_elements(
                "css selector", "div.message-in span.selectable-text"
            )
            return messages[-1].text.strip() if messages else ""

        last_message = ""
        while True:
            try:
                current = await asyncio.to_thread(latest_incoming_message)
                if current and current != last_message:
                    last_message = current
                    sender = sender_name or "Unknown"
                    emotion = "neutral"
                    if "happy" in current.lower() or "love" in current.lower():
                        emotion = "happy"
                    elif "sad" in current.lower() or "miss" in current.lower():
                        emotion = "sad"
                    reply = "Aww, kitna pyaara message! " if emotion == "happy" else "Arey, sad mat ho na... "
                    return f"**Naya message from {sender}:** {current}\nEmotion: {emotion}\nReply idea: {reply}"
            except:
                pass

            await asyncio.sleep(max(1, check_interval_sec))

    except Exception as e:
        return f"Monitoring failed: {str(e)}\nBrave browser mein WhatsApp Web open rakho aur QR scan karo."


server = AgentServer()


def async_event_handler(session, event_name):
    def decorator(func):
        def wrapper(*args, **kwargs):
            asyncio.create_task(func(*args, **kwargs))

        session.on(event_name, wrapper)
        return func

    return decorator


@server.rtc_session()
async def my_agent(ctx: agents.JobContext):
    await init_memory_engine()
    memories = await recall_memory("What is the user's name, preferred language, and speaking style?", top_k=3)
    user_profile = ""
    if memories:
        user_profile = "\n\n--- DYNAMIC USER PROFILE & STYLE (OVERRIDE DEFAULTS) ---\n"
        for mem in memories:
            user_profile += f"- {mem.memory.content}\n"
        user_profile += "CRITICAL: You MUST adapt your tone, language, and name usage to strictly match the user profile above, while maintaining ALL core HEART security and neural schema rules.\n"

    final_instructions = HEART_SYSTEM_PROMPT + user_profile

    fast_vad = silero.VAD.load(
        min_silence_duration=0.35,
        activation_threshold=0.15,
        prefix_padding_duration=0.08,
        max_buffered_speech=6.0
    )
    heart_session = AgentSession(
        vad=fast_vad,
        llm=google.beta.realtime.RealtimeModel(
            voice="Leda",
            temperature=0.6
        ),
        preemptive_generation=True,
        allow_interruptions=True
    )
    # Layer 2: Advanced Noise Suppression
    noise_cancellation = lambda p: (
        noise_cancellation.BVCTelephony()
        if p.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
        else noise_cancellation.BVC()
    )


    global _current_agent
    agent = Assistant(dynamic_instructions=final_instructions, chat_ctx=ChatContext())
    _current_agent = agent

    await heart_session.start(
        room=ctx.room,
        agent=agent,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda p: (
                    lk_nc.BVCTelephony()
                    if p.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else lk_nc.BVC()

                )
            )
        )
    )

    # --- STARTUP GREETING PROTOCOL (FIXED) ---
    async def _trigger_greeting():
        try:
            await asyncio.sleep(1.5)
        except Exception as e:
            print(f" [GREETING ERROR] Failed to send greeting: {e}")

    asyncio.create_task(_trigger_greeting())

    # --- EVENT HANDLERS FOR BARGE-IN & MEMORY ---
    @async_event_handler(heart_session, "user_input_transcribed")
    async def on_user_input(event):
        if not heart_active.is_set():
            return

        text = getattr(event, "transcription", None)
        if not text:
            return

        print(f" [Debug] User said: {text}")

        decision = heart_ctrl.check_input(text)
        if decision['action'] == 'STOP_IMMEDIATELY':
            await heart_session.generate_reply(user_message=decision['message'])
            return

        # Process and Persist with Debouncing
        async def process_and_persist(user_text: str, active_session=heart_session):
            global CURRENT_FILE_PATH, _last_memory_save

            # Memory Save Debounce
            now = time.time()
            if now - _last_memory_save >= _MEMORY_SAVE_DEBOUNCE:
                asyncio.create_task(save_memory(user_text))
                _last_memory_save = now

            # File Context Injection Logic (Optimized)
            user_lower = user_text.lower().strip()
            file_keywords = {"file", "upload", "document", "read", "summarize"}
            is_asking_about_file = any(kw in user_lower for kw in file_keywords)

            if is_asking_about_file and CURRENT_FILE_PATH and os.path.exists(CURRENT_FILE_PATH):
                try:
                    def read_file_sync(path):
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            return f.read(1500)

                    file_content = await asyncio.to_thread(read_file_sync, CURRENT_FILE_PATH)
                    system_note = f"\n[FILE CONTEXT: '{os.path.basename(CURRENT_FILE_PATH)}' content:\n{file_content}\n...]"
                    user_text += system_note
                except Exception as e:
                    print(f" [SYSTEM] Error reading file: {e}")

            # Use generate_reply for token-streaming enabled responses
            await active_session.generate_reply(user_message=user_text)

        asyncio.create_task(process_and_persist(text))


if __name__ == "__main__":

    warnings.filterwarnings("ignore")
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", message=".*padding_duration is deprecated.*")
    warnings.filterwarnings("ignore", message=".*allow_interruptions.*")
    warnings.filterwarnings("ignore", message=".*inference is slower than realtime.*")

    # 2. Set Logging Level to CRITICAL (Only show if system crashes)
    logging.getLogger().setLevel(logging.CRITICAL)
    logging.getLogger("livekit").setLevel(logging.CRITICAL)
    logging.getLogger("google").setLevel(logging.CRITICAL)
    logging.getLogger("chromadb").setLevel(logging.CRITICAL)
    logging.getLogger("aiosqlite").setLevel(logging.CRITICAL)
    logging.getLogger("websockets").setLevel(logging.CRITICAL)
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    logging.getLogger("silero").setLevel(logging.CRITICAL)

    # 3. Environment Variables for Performance & Silence
    os.environ["PYTHONASYNCIODEBUG"] = "0"
    os.environ["LIVEKIT_LOG_LEVEL"] = "CRITICAL"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    # =========================================
    # IMPORTS (After logging is configured)
    # =========================================
    from runtime.monitor import update_activity
    from heart_reminder import check_and_get_triggered

    # =========================================
    # CONFIG & GLOBAL STATE
    # =========================================
    IDLE_TIMEOUT = 3600


    STATE = {
        "running": True,
        "processing": False,
        "hud_started": False,
        "reminder_started": False,
        "upload_started": False,
    }

    wake_lock = threading.Lock()
    heart_active = threading.Event()
    heart_active.set()

    # Only print these 3 lines for a clean start
    print("\n HEART SYSTEM ONLINE - AUTH BYPASSED")
    print(" Starting Services...")
    print(" Welcome Back D4RK\n")


    # =========================================
    # BACKGROUND MONITORS
    # =========================================
    def check_reminders_loop():
        while STATE["running"]:
            try:
                messages = check_and_get_triggered()
                for msg in messages:
                    print(f" [REMINDER] {msg}")  # Only show reminders
            except:
                pass
            time.sleep(60)


    threading.Thread(target=check_reminders_loop, daemon=True, name="ReminderThread").start()

    # =========================================
    # FORCE CONSOLE MODE
    # =========================================
    if "--console" not in sys.argv and "console" not in sys.argv:
        sys.argv.append("console")

    # =========================================
    # MAIN HEART ENGINE LOOP
    # =========================================
    while STATE["running"]:
        heart_active.wait()

        with wake_lock:
            if STATE["processing"]:
                continue

            STATE["processing"] = True
            update_activity()

            try:
                # 1. START HUD
                if not STATE["hud_started"]:
                    threading.Thread(target=heart_hud.start_hud, daemon=True, name="HUDThread").start()
                    STATE["hud_started"] = True

                # 2. START FILE RECEIVER
                if not STATE.get("upload_started"):
                    threading.Thread(target=run_upload_server, daemon=True, name="UploadServer").start()
                    STATE["upload_started"] = True

                # 3. RUN HEART AGENT
                agents.cli.run_app(server)

            except KeyboardInterrupt:
                print("\n [SYSTEM] Shutdown requested")
                STATE["running"] = False
            except Exception as e:
                # Only print error if it's critical
                print(f"\n [ERROR] {e}")
                time.sleep(1)
            finally:
                STATE["processing"] = False
                heart_active.clear()
