import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import BOTH, LEFT, X, Button, Frame, Label, Tk, messagebox


APP_NAME = "Local RAG Assistant"
HOST = "127.0.0.1"
PORT = 8000
BASE_URL = f"http://localhost:{PORT}"
HEALTH_URL = f"http://{HOST}:{PORT}/health"
READY_URL = f"http://{HOST}:{PORT}/ready"
OLLAMA_URL = "http://localhost:11434/api/tags"


def creation_flags():
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)

    return 0


def find_project_root():
    candidates = []

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir, exe_dir.parent])
    else:
        script_dir = Path(__file__).resolve().parent
        candidates.extend([script_dir, script_dir.parent])

    candidates.append(Path.cwd())

    for candidate in candidates:
        if (candidate / "app" / "main.py").exists() and (
            candidate / "frontend" / "index.html"
        ).exists():
            return candidate

    raise RuntimeError(
        "프로젝트 루트를 찾지 못했습니다. 런처 EXE를 프로젝트 폴더 또는 dist 폴더에서 실행해 주세요."
    )


def request_json(url, timeout=2):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def is_server_running():
    try:
        body = request_json(READY_URL)
        return "local-rag-assistant" in body
    except Exception:
        pass

    try:
        body = request_json(HEALTH_URL, timeout=8)
        return '"status"' in body and '"ok"' in body
    except Exception:
        return False


def is_server_healthy():
    try:
        request_json(HEALTH_URL, timeout=8)
        return True
    except Exception:
        return False


def is_port_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((HOST, PORT)) == 0


def is_ollama_running():
    try:
        request_json(OLLAMA_URL)
        return True
    except Exception:
        return False


def start_ollama_if_available():
    if is_ollama_running():
        return None

    try:
        process = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags(),
        )
    except Exception:
        return None

    for _ in range(20):
        if is_ollama_running():
            return process
        time.sleep(0.5)

    return process


def find_venv_python(project_root):
    python_path = project_root / "venv" / "Scripts" / "python.exe"

    if python_path.exists():
        return python_path

    raise RuntimeError(
        f"가상환경 Python을 찾지 못했습니다.\n\n예상 경로:\n{python_path}\n\n"
        "먼저 프로젝트 폴더에서 Python 3.11 venv를 만들어 주세요."
    )


def start_server(project_root):
    if is_server_running():
        return None, "already-running"

    if is_port_in_use():
        raise RuntimeError(
            f"{PORT} 포트가 이미 사용 중입니다. 기존 서버나 다른 프로그램을 종료한 뒤 다시 실행해 주세요."
        )

    python_path = find_venv_python(project_root)

    process = subprocess.Popen(
        [
            str(python_path),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ],
        cwd=str(project_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags(),
    )

    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError("서버 프로세스가 시작 직후 종료되었습니다.")

        if is_server_running():
            return process, "started"

        time.sleep(0.5)

    raise RuntimeError("서버가 제한 시간 안에 응답하지 않았습니다.")


def browser_candidates():
    local_appdata = os.getenv("LOCALAPPDATA", "")

    return [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(local_appdata) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]


def reset_browser_profile(profile_dir):
    if profile_dir.exists():
        shutil.rmtree(profile_dir, ignore_errors=True)

    profile_dir.mkdir(parents=True, exist_ok=True)


def open_app_browser(project_root):
    profile_dir = project_root / "storage" / "runtime" / "browser_profile_100"

    for browser_path in browser_candidates():
        if not browser_path.exists():
            continue

        reset_browser_profile(profile_dir)

        subprocess.Popen(
            [
                str(browser_path),
                f"--app={BASE_URL}",
                f"--user-data-dir={profile_dir}",
                "--force-device-scale-factor=1",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags(),
        )
        return

    webbrowser.open(BASE_URL)


class LauncherWindow:
    def __init__(self):
        self.root = Tk()
        self.root.title(APP_NAME)
        self.root.geometry("420x180")
        self.root.resizable(False, False)

        self.server_process = None
        self.ollama_process = None
        self.project_root = None

        self.status = Label(
            self.root,
            text="서버를 준비하는 중...",
            anchor="w",
            justify=LEFT,
            padx=16,
            pady=16,
        )
        self.status.pack(fill=BOTH, expand=True)

        button_frame = Frame(self.root, padx=16, pady=12)
        button_frame.pack(fill=X)

        self.open_button = Button(
            button_frame,
            text="브라우저 열기",
            command=self.open_browser,
            state="disabled",
            width=16,
        )
        self.open_button.pack(side=LEFT)

        self.stop_button = Button(
            button_frame,
            text="서버 종료",
            command=self.close,
            width=16,
        )
        self.stop_button.pack(side=LEFT, padx=8)

        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def set_status(self, text):
        self.status.config(text=text)

    def open_browser(self):
        open_app_browser(self.project_root or find_project_root())

    def start(self):
        thread = threading.Thread(target=self.boot, daemon=True)
        thread.start()
        self.root.mainloop()

    def boot(self):
        try:
            project_root = find_project_root()
            self.project_root = project_root
            self.root.after(0, self.set_status, f"프로젝트 폴더:\n{project_root}")

            self.ollama_process = start_ollama_if_available()

            self.server_process, mode = start_server(project_root)

            if mode == "already-running":
                status = "이미 실행 중인 Local RAG 서버를 찾았습니다."
            else:
                status = "Local RAG 서버가 실행되었습니다."

            if not is_ollama_running():
                status += "\n\nOllama는 감지되지 않았습니다. 질문/업로드 전에 Ollama를 실행해 주세요."

            self.root.after(0, self.set_status, status)
            self.root.after(0, self.open_button.config, {"state": "normal"})
            self.root.after(400, self.open_browser)

        except Exception as exc:
            self.root.after(0, self.set_status, "실행 실패")
            self.root.after(0, messagebox.showerror, APP_NAME, str(exc))

    def close(self):
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()

            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()

        self.root.destroy()


if __name__ == "__main__":
    LauncherWindow().start()
