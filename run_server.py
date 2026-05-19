from __future__ import annotations

import os
import shlex
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn


APP_DIR = Path(__file__).resolve().parent
DEFAULT_EXTERNAL_FE_BOT_DIR = APP_DIR / "external" / "bot-serving"
external_process: subprocess.Popen | None = None


def open_browser():
    time.sleep(1.0)
    webbrowser.open("http://127.0.0.1:8000/")


def start_external_fe_bot() -> None:
    global external_process

    if is_port_open("127.0.0.1", 8001):
        print("External FE bot service already running on http://127.0.0.1:8001")
        return

    command = os.getenv("EXTERNAL_FE_BOT_CMD")
    cwd = os.getenv("EXTERNAL_FE_BOT_CWD")
    if command:
        args = shlex.split(command, posix=os.name != "nt")
    elif DEFAULT_EXTERNAL_FE_BOT_DIR.exists():
        cwd = str(DEFAULT_EXTERNAL_FE_BOT_DIR)
        external_python = DEFAULT_EXTERNAL_FE_BOT_DIR / ".venv" / "Scripts" / "python.exe"
        args = [
            str(external_python if external_python.exists() else sys.executable),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8001",
        ]
    else:
        return

    external_process = subprocess.Popen(args, cwd=cwd or None)
    print("Started external FE bot service on http://127.0.0.1:8001")


def is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def stop_external_fe_bot() -> None:
    if external_process and external_process.poll() is None:
        external_process.terminate()


if __name__ == "__main__":
    start_external_fe_bot()
    threading.Thread(target=open_browser, daemon=True).start()
    try:
        uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
    finally:
        stop_external_fe_bot()
