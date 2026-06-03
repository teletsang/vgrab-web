#!/usr/bin/env python3
"""vgrab-web 原生窗口启动器"""
import threading
import sys
import os
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def start_server():
    from app import app
    app.run(host="127.0.0.1", port=9999, debug=False, use_reloader=False)


if __name__ == "__main__":
    import webview

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    import time, urllib.request
    for _ in range(40):
        try:
            urllib.request.urlopen("http://127.0.0.1:9999/api/status", timeout=1)
            break
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)

    webview.create_window("扒扒侠", "http://127.0.0.1:9999", width=900, height=720, min_size=(600, 500))
    webview.start()
