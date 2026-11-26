import os
import re
import sys
import time
import json
import queue
import hashlib
import random
import threading
import subprocess
from pathlib import Path
from datetime import datetime

# =========================================
# CONFIGURATION & PATHS
# =========================================
PROJECT_DIR = Path(__file__).parent.resolve()
VENV_DIR = PROJECT_DIR / ".venv"
PYTHON_EXE = VENV_DIR / "Scripts" / "python.exe" if os.name == "nt" else VENV_DIR / "bin" / "python"
REQUIREMENTS_FILE = PROJECT_DIR / "requirements.txt"
MAIN_FILE = PROJECT_DIR / "heart.py"
CACHE_DIR = PROJECT_DIR / ".heart_cache"
DEP_HASH_FILE = CACHE_DIR / "dep_hash.json"

# Performance Flags
CHECK_INTERVAL = 0.5
MAX_RESTARTS = 50


# =========================================
# VISUAL ENGINE (FUTURISTIC)
# =========================================
class Visuals:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

    @staticmethod
    def clear():
        os.system("cls" if os.name == "nt" else "clear")

    @staticmethod
    def print_header():
        Visuals.clear()
        print(f"{Visuals.CYAN}")
        print("╔══════════════════════════════════════════════════════╗")
        print("║              H.E.A.R.T SYSTEM CORE                 ║")
        print("║           Autonomous Self-Healing Engine           ║")
        print("║             Version: 3.0 [NEON EDITION]            ║")
        print("╚══════════════════════════════════════════════════════╝")
        print(f"{Visuals.RESET}")

    @staticmethod
    def glitch_text(text, speed=0.02):
        """Types text with a slight random glitch effect"""
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%^&*"
        for char in text:
            if random.random() < 0.1:  # 10% chance of glitch
                sys.stdout.write(f"{Visuals.MAGENTA}{random.choice(chars)}{Visuals.RESET}")
                sys.stdout.flush()
                time.sleep(speed)
                sys.stdout.write(f"\b{char}")  # Overwrite with correct char
            else:
                sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(speed)
        print()

    @staticmethod
    def loading_bar(task_name, total_steps=25):
        bar_width = 20
        sys.stdout.write(f"{Visuals.BLUE}[INIT] {task_name:<20} [{(' ' * bar_width)}]")
        sys.stdout.flush()
        sys.stdout.write(f"\b" * (bar_width + 1))

        for i in range(total_steps):
            time.sleep(0.04)
            filled = int((i / total_steps) * bar_width)
            bar = "█" * filled + "-" * (bar_width - filled)
            sys.stdout.write(f"[{bar}]")
            sys.stdout.flush()
            sys.stdout.write(f"\b" * (bar_width + 2))

        sys.stdout.write(f"[{'█' * bar_width}] 100%{Visuals.RESET}\n")

    @staticmethod
    def log(msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if level == "OK":
            color = Visuals.GREEN
            tag = "SUCCESS"
        elif level == "ERROR":
            color = Visuals.RED
            tag = "CRITICAL"
        elif level == "WARN":
            color = Visuals.YELLOW
            tag = "WARNING"
        else:
            color = Visuals.CYAN
            tag = "SYSTEM"

        print(f"{Visuals.DIM}[{timestamp}]{Visuals.RESET} {color}[{tag}] {msg}{Visuals.RESET}")


# =========================================
# SMART DEPENDENCY MANAGER
# =========================================
class DependencyManager:
    def __init__(self):
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(exist_ok=True)

    def get_hash(self):
        if not REQUIREMENTS_FILE.exists(): return None
        with open(REQUIREMENTS_FILE, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def is_synced(self):
        if not DEP_HASH_FILE.exists(): return False
        try:
            with open(DEP_HASH_FILE, 'r') as f:
                data = json.load(f)
            return data.get('hash') == self.get_hash() and PYTHON_EXE.exists()
        except:
            return False

    def sync(self):
        if self.is_synced():
            Visuals.log("Environment verified. Cache hit.", "OK")
            return True

        Visuals.log("Dependency mismatch detected. Initiating sync...", "WARN")
        Visuals.loading_bar("Installing Packages", 30)

        cmd = [str(PYTHON_EXE), "-m", "pip", "install", "--upgrade", "--no-cache-dir", "-r", str(REQUIREMENTS_FILE)]
        try:
            result = subprocess.run(cmd, capture_output=False)
            if result.returncode == 0:
                with open(DEP_HASH_FILE, 'w') as f:
                    json.dump({'hash': self.get_hash(), 'time': datetime.now().isoformat()}, f)
                Visuals.log("System synchronized successfully.", "OK")
                return True
            else:
                Visuals.log("Sync failed. Check internet or requirements.txt", "ERROR")
                return False
        except Exception as e:
            Visuals.log(f"Sync error: {e}", "ERROR")
            return False


# =========================================
# EMERGENCY COMMAND CENTER
# =========================================
def emergency_shell(last_error=None):
    """Interactive shell for manual debugging"""
    Visuals.clear()
    print(f"{Visuals.RED}╔══════════════════════════════════════════════╗")
    print("║         ⚠️  EMERGENCY RECOVERY MODE  ⚠️          ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"{Visuals.RESET}")

    if last_error:
        print(f"{Visuals.YELLOW}LAST DETECTED ERROR:{Visuals.RESET}")
        print(f"{Visuals.DIM}{last_error}{Visuals.RESET}\n")

    print(f"{Visuals.CYAN}Available Commands:{Visuals.RESET}")
    print("  1. retry       - Attempt to restart HEART")
    print("  2. install <pkg> - Manually install a package")
    print("  3. pip list    - Show installed packages")
    print("  4. logs        - Show last error details")
    print("  5. exit        - Shutdown system")
    print("-" * 50)

    while True:
        try:
            cmd = input(f"{Visuals.GREEN}root@heart:~# {Visuals.RESET}").strip().lower()

            if cmd == "retry":
                return True
            elif cmd.startswith("install "):
                pkg = cmd.split(" ", 1)[1]
                Visuals.log(f"Installing {pkg}...", "INFO")
                subprocess.run([str(PYTHON_EXE), "-m", "pip", "install", pkg])
            elif cmd == "pip list":
                subprocess.run([str(PYTHON_EXE), "-m", "pip", "list"])
            elif cmd == "logs":
                print(last_error)
            elif cmd == "exit":
                sys.exit(0)
            else:
                print("Unknown command.")
        except KeyboardInterrupt:
            sys.exit(0)


# =========================================
# AUTO-HEAL ENGINE
# =========================================
def analyze_and_heal(line):
    patterns = [
        (r"No module named ['\"](.+?)['\"]", "missing_module"),
        (r"cannot import name ['\"](.+?)['\"]", "import_error"),
        (r"Failed to load PyTorch C extensions", "torch_corrupt"),
    ]

    for pattern, err_type in patterns:
        match = re.search(pattern, line)
        if match:
            target = match.group(1).split('.')[0] if err_type != "torch_corrupt" else "torch"
            Visuals.log(f"Detected issue: {err_type} ({target})", "WARN")

            # Auto-heal attempt
            Visuals.log(f"Attempting auto-repair for '{target}'...", "INFO")
            try:
                flag = "--force-reinstall" if err_type == "torch_corrupt" else ""
                subprocess.run([str(PYTHON_EXE), "-m", "pip", "install", flag, target], capture_output=False)
                Visuals.log("Repair successful. Restarting...", "OK")
                return True
            except:
                Visuals.log("Auto-repair failed.", "ERROR")
                return False
    return None


# =========================================
# SUPERVISOR
# =========================================
def launch_heart():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        [str(PYTHON_EXE), "-B", str(MAIN_FILE), "console"],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env
    )


def supervisor():
    dep_mgr = DependencyManager()
    Visuals.print_header()
    Visuals.glitch_text("INITIALIZING NEURAL KERNEL...")

    if not PYTHON_EXE.exists():
        Visuals.log("Virtual Environment missing. Creating...", "WARN")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)])
        Visuals.log("VEnv created. Please restart bootloader.", "ERROR")
        sys.exit(1)

    # Sync Dependencies
    if not dep_mgr.sync():
        Visuals.log("Critical dependency failure.", "ERROR")
        emergency_shell("Dependency Sync Failed")

    time.sleep(1)
    Visuals.glitch_text("LAUNCHING H.E.A.R.T AGENT...")
    time.sleep(0.5)

    restart_count = 0
    last_error_log = ""

    while True:
        try:
            process = launch_heart()
            q_out, q_err = queue.Queue(), queue.Queue()

            t_out = threading.Thread(target=lambda: [q_out.put(l) for l in iter(process.stdout.readline, '')],
                                     daemon=True)
            t_err = threading.Thread(target=lambda: [q_err.put(l) for l in iter(process.stderr.readline, '')],
                                     daemon=True)
            t_out.start();
            t_err.start()

            while True:
                # Print Output
                while not q_out.empty():
                    sys.stdout.write(q_out.get())

                # Handle Errors
                while not q_err.empty():
                    line = q_err.get()
                    sys.stderr.write(f"{Visuals.RED}{line}{Visuals.RESET}")
                    last_error_log = line

                    healed = analyze_and_heal(line)
                    if healed:
                        process.kill()
                        time.sleep(2)
                        break  # Restart loop
                    elif healed is False:
                        process.kill()
                        emergency_shell(last_error_log)

                if process.poll() is not None:
                    Visuals.log(f"Process exited (Code: {process.returncode})", "WARN")
                    restart_count += 1
                    if restart_count > MAX_RESTARTS:
                        emergency_shell("Max restart limit reached")
                    time.sleep(2)
                    break

                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            Visuals.log("Shutdown sequence initiated...", "WARN")
            if 'process' in locals(): process.kill()
            sys.exit(0)


if __name__ == "__main__":
    supervisor()