from __future__ import annotations

import threading
import time
import webbrowser

import uvicorn
from app.main import app


HOST = "127.0.0.1"
PORT = 8000
APP_URL = f"http://{HOST}:{PORT}"


def open_browser() -> None:
    time.sleep(1.2)
    webbrowser.open(APP_URL)


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host=HOST, port=PORT, reload=False)
