import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = os.environ.get("NAVER_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("NAVER_BRIDGE_PORT", "8787"))
INBOX_DIR = Path(os.environ.get("NAVER_BRIDGE_INBOX_DIR", "bridge_inbox/naver_blog"))


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def safe_name(value: str) -> str:
    raw = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(value or "post"))
    return raw.strip("-") or "post"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in {"/", "/health"}:
            self._send_json(200, {"ok": True, "service": "naver_blog_bridge", "time": now_kst()})
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path not in {"/webhook/naver-blog-publish", "/naver-blog-publish"}:
            self._send_json(404, {"ok": False, "error": "not found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return

        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        asset_id = safe_name(payload.get("asset_id") or payload.get("content_id") or "post")
        stamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d_%H%M%S")
        file_path = INBOX_DIR / f"{stamp}_{asset_id}.json"
        payload["received_at"] = now_kst()
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        # This bridge stores the asset and returns an accepted status.
        # A local browser publisher will consume this inbox and perform the actual Naver Blog posting.
        self._send_json(202, {
            "ok": True,
            "status": "accepted",
            "post_id": asset_id,
            "inbox_file": str(file_path),
            "message": "stored for local Naver Blog publisher",
        })

    def log_message(self, format, *args):
        print(f"[{now_kst()}] {self.address_string()} - {format % args}")


def main():
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Naver bridge listening on http://{HOST}:{PORT}/webhook/naver-blog-publish")
    print("Keep this process running while GitHub Actions sends approved rows.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping bridge...")
        time.sleep(0.2)


if __name__ == "__main__":
    main()
