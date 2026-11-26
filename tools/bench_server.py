#!/usr/bin/env python3
"""Kleiner Webserver für den Bild-KI-Bericht (tools/photo_ai_bench.py bericht): liefert den Ordner aus und nimmt die Sterne aus dem Bericht an (POST /sterne
-> sterne.json im Ordner), damit sie nicht nur im Browser liegen. Aufruf: python tools/bench_server.py ORDNER [--port 8778]"""
import argparse
import functools
import http.server
import json
from pathlib import Path


def handler(directory):
    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path != "/sterne":
                self.send_error(404)
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                json.loads(body)
            except ValueError:
                self.send_error(400)
                return
            (Path(directory) / "sterne.json").write_bytes(body)
            self.send_response(204)
            self.end_headers()
    return functools.partial(H, directory=str(directory))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ordner")
    ap.add_argument("--port", type=int, default=8778)
    a = ap.parse_args()
    http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler(a.ordner)).serve_forever()
