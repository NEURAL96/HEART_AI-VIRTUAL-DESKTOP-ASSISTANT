import subprocess
import time
import os
import sys

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

HEART_PATH = os.path.join(BASE_DIR, "heart.py")


def start_heart():

    print("[WATCHDOG] Starting HEART")
    VENV_PYTHON = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    return subprocess.Popen(
        [sys.executable, HEART_PATH],
        cwd=BASE_DIR
    )


process = start_heart()

while True:

    time.sleep(10)

    if process.poll() is not None:

        print("[WATCHDOG] HEART stopped")

        time.sleep(5)

        process = start_heart()