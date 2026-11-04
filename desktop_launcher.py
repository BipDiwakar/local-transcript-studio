from __future__ import annotations

import atexit
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import webview


APP_TITLE = "Local Transcript Studio"


def log_path() -> Path:
    folder = Path.home() / "Library" / "Logs" / "Local Transcript Studio"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "desktop.log"


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(url: str, timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.35)
    raise RuntimeError("The app took too long to start.")


def start_streamlit(project_root: Path, port: int) -> subprocess.Popen:
    log_file = log_path().open("a", encoding="utf-8")
    env = {
        **os.environ,
        "BROWSER": "none",
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:"
        + os.environ.get("PATH", ""),
    }
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(project_root / "app.py"),
        "--server.headless=true",
        f"--server.port={port}",
        "--server.address=127.0.0.1",
        "--browser.gatherUsageStats=false",
    ]
    return subprocess.Popen(
        command,
        cwd=project_root,
        stdout=log_file,
        stderr=log_file,
        env=env,
    )


def main() -> None:
    project_root = Path(__file__).resolve().parent
    log_path().write_text(f"Starting {APP_TITLE} from {project_root}\n", encoding="utf-8")
    port = find_free_port()
    url = f"http://127.0.0.1:{port}"
    process = start_streamlit(project_root, port)

    def stop_server() -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    atexit.register(stop_server)

    try:
        wait_for_server(url)
    except Exception:
        stop_server()
        raise

    webview.create_window(
        APP_TITLE,
        url,
        width=1240,
        height=760,
        min_size=(980, 640),
        text_select=True,
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
