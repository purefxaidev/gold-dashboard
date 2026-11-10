#!/usr/bin/env python3
"""Render latest PureGold share posters to share/latest-*-WxH.png via headless Chromium."""
from __future__ import annotations

import http.server
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "share"
HOST, PORT = "127.0.0.1", int(os.environ.get("SHARE_RENDER_PORT", "8769"))


def serve() -> http.server.ThreadingHTTPServer:
    os.chdir(ROOT)
    httpd = http.server.ThreadingHTTPServer((HOST, PORT), http.server.SimpleHTTPRequestHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def render() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    httpd = serve()
    url = f"http://{HOST}:{PORT}/render-share.html"
    try:
        with sync_playwright() as p:
            launch = {"headless": True, "args": ["--disable-gpu"]}
            try:
                browser = p.chromium.launch(channel="chrome", **launch)
            except Exception:
                browser = p.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            import base64
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_function("() => document.title === 'READY' || document.title === 'ERROR'", timeout=120000)
            title = page.title()
            if title != "READY":
                err = page.evaluate("() => window.__SHARE_ERROR || 'unknown'")
                print(f"[render_share] failed: {err}", file=sys.stderr)
                browser.close()
                return 1
            n = 0
            count = page.evaluate("() => (window.__SHARE_POSTERS || []).length")
            for i in range(count):
                f = page.evaluate("(i) => window.__SHARE_POSTERS[i]", i)
                raw = f["dataUrl"].split(",", 1)[1]
                path = OUT / f["name"]
                path.write_bytes(base64.b64decode(raw))
                print(f"[render_share] wrote {path.name} ({path.stat().st_size} bytes)")
                n += 1
            browser.close()
            print(f"[render_share] {n} posters")
            return 0 if n else 1
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    try:
        sys.exit(render())
    except Exception as e:
        print(f"[render_share] skipped ({e})", file=sys.stderr)
        sys.exit(0)
