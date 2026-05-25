import argparse
import mimetypes
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()


def main():
    parser = argparse.ArgumentParser(description="Serve generated media files for external platform fetch tests.")
    parser.add_argument("--root", default=".", help="Repository root or media root to serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"root does not exist: {root}")

    mimetypes.add_type("video/mp4", ".mp4")
    handler = lambda *a, **kw: Handler(*a, directory=str(root), **kw)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {root} at http://{args.host}:{args.port}")
    print("Example media path: http://127.0.0.1:%s/generated/short_videos/asset-content-001-shorts.mp4" % args.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
