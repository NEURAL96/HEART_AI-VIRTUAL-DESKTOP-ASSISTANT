import time
from threading import Lock

_activity_lock = Lock()
last_activity = time.time()


def update_activity():
    global last_activity

    with _activity_lock:
        last_activity = time.time()


def get_idle_time():
    with _activity_lock:
        return time.time() - last_activity


def is_idle(timeout=3600):
    return get_idle_time() > timeout