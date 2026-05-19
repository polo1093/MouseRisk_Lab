from __future__ import annotations

from datetime import datetime
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
LOG_DIR = APP_DIR / "logs"
SERVER_LOG = LOG_DIR / "server.log"
external_process: subprocess.Popen | None = None


def log_server(message: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with SERVER_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message.rstrip()}\n")


def open_browser():
    time.sleep(1.0)
    log_server("Opening browser at http://127.0.0.1:8000/")
    webbrowser.open("http://127.0.0.1:8000/")


def start_external_fe_bot() -> None:
    global external_process

    if is_port_open("127.0.0.1", 8001):
        print("External FE bot service already running on http://127.0.0.1:8001")
        log_server("External FE bot service already running on http://127.0.0.1:8001")
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
        log_server("External FE bot service not started: directory/command unavailable")
        return

    external_process = subprocess.Popen(args, cwd=cwd or None)
    print("Started external FE bot service on http://127.0.0.1:8001")
    log_server(f"Started external FE bot service command={subprocess.list2cmdline(args)} cwd={cwd or os.getcwd()}")


def is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def stop_external_fe_bot() -> None:
    if external_process and external_process.poll() is None:
        external_process.terminate()
        log_server("Stopped external FE bot service")


if __name__ == "__main__":
    log_server("Starting MouseRisk Lab server on http://127.0.0.1:8000/")
    start_external_fe_bot()
    threading.Thread(target=open_browser, daemon=True).start()
    try:
        uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
    finally:
        stop_external_fe_bot()
        log_server("MouseRisk Lab server stopped")
