#!/usr/bin/env python3
"""Lokaler Server für das Markierwerkzeug (web/review/): strittige Stellen einer Szene entscheiden.

Nur an 127.0.0.1, nur Standardbibliothek (specs/003-eigene-referenz/contracts/review-api.md). Liefert die Seite, das
Szenenvideo (mit Range-Anfragen zum Springen) und die Stellen; jede Antwort wird sofort in {det}.reference.json
gespeichert (temporäre Datei, dann umbenennen). Bilder verlassen den Rechner nicht.

Aufruf:
    .venv/bin/python tools/review_server.py SZENENVIDEO DETEKTIONEN.json [--port 8766]
"""
import argparse
import json
import re
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import reference as ref  # noqa: E402

WEB = Path(__file__).resolve().parent.parent / "web" / "review"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/review.js": ("review.js", "text/javascript; charset=utf-8"),
          "/review.css": ("review.css", "text/css; charset=utf-8")}
CHOICES = ("proposed", "swapped", "mapped", "unclear")
CHUNK = 1 << 20
MAX_ANSWER_BYTES = 64 << 10


class AnswerError(ValueError):
    """Antwort passt nicht zur Stelle."""


class Review:
    """Zustand einer Szene: Referenzdatei, Zuordnung der Auswertung, Video."""

    def __init__(self, video: str | Path, det_path: str | Path, web: Path = WEB):
        self.video, self.web = Path(video), web
        self.path = Path(f"{det_path}.reference.json")
        self.identity = json.loads(Path(f"{det_path}.identity.json").read_text())
        det = json.loads(Path(det_path).read_text())
        self.fps, self.lens_size = det["fps"], det.get("lensSize")
        self.lock = threading.Lock()
        data = json.loads(self.path.read_text())
        self.scene, self.stamp = data["scene"], data["identityStamp"]
        self.spots, self.answers, self.seed = ref.from_json(data)

    def state(self) -> dict:
        latest = {}
        for a in self.answers:
            if not a.repeat:
                latest[a.spot] = a
        data = ref.to_json(self.scene, self.stamp, self.spots, [], self.seed)
        return {"scene": self.scene, "fps": self.fps, "lensSize": self.lens_size, "spots": data["spots"],
                "answers": {k: v.__dict__ for k, v in latest.items()}, "open": self.open()}

    def open(self) -> int:
        decided = {a.spot for a in self.answers if not a.repeat}
        return sum(1 for s in self.spots if s.id not in decided)

    def check(self, body: dict) -> ref.Answer:
        spot = next((s for s in self.spots if s.id == body.get("spot")), None)
        if spot is None:
            raise AnswerError("unbekannte Stelle")
        choice = body.get("choice")
        if choice not in CHOICES:
            raise AnswerError(f"Antwort muss eine von {', '.join(CHOICES)} sein")
        before = {p.letter for p in spot.before}
        after = {p.letter for p in spot.after}
        mapping = body.get("mapping") or {}
        if choice == "mapped":
            if set(mapping) != after or any(v not in before | {"other", "unclear"} for v in mapping.values()):
                raise AnswerError("Zuordnung muss jeden Buchstaben nachher einem davor, „other“ oder „unclear“ geben")
        if choice == "swapped" and len(spot.before) != 2:
            raise AnswerError("„vertauscht“ geht nur bei zwei Beteiligten")
        numbers = body.get("numbers") or {}
        for letter, number in numbers.items():
            if letter not in before | after or not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 99:
                raise AnswerError("Nummern: Buchstabe der Stelle und ganze Zahl 1–99")
        anchors = {p.letter: p.anchor for p in spot.before + spot.after}
        return ref.Answer(spot.id, choice, dict(mapping) if choice == "mapped" else {}, dict(numbers), anchors,
                          datetime.now(timezone.utc).isoformat(timespec="seconds"), bool(body.get("repeat", False)))

    def answer(self, body: dict) -> dict:
        a = self.check(body)
        with self.lock:
            self.answers.append(a)
            data = ref.to_json(self.scene, self.stamp, self.spots, self.answers, self.seed)
            tmp = Path(f"{self.path}.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False) + "\n")
            tmp.replace(self.path)
            warnings = ref.conflicts(self.identity, ref.persons(self.identity, self.spots, self.answers))
            return {"ok": True, "warnings": warnings, "open": self.open()}


def handler(review: Review):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):   # keine Zugriffsprotokolle auf der Konsole
            pass

        def send(self, code: int, body: bytes, kind: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def json(self, code: int, data: dict) -> None:
            self.send(code, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in STATIC:
                name, kind = STATIC[path]
                return self.send(200, (review.web / name).read_bytes(), kind)
            if path == "/spots":
                return self.json(200, review.state())
            if path == "/video":
                return self.video()
            self.send(404, b"nicht gefunden", "text/plain; charset=utf-8")

        def video(self):
            size = review.video.stat().st_size
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            if m and (m.group(1) or m.group(2)):
                if m.group(1):   # offenes Ende: höchstens CHUNK Bytes je Antwort
                    start = int(m.group(1))
                    end = min(int(m.group(2)) if m.group(2) else start + CHUNK - 1,
                              start + CHUNK - 1, size - 1)
                else:
                    start, end = max(0, size - min(int(m.group(2)), CHUNK)), size - 1
                if start >= size or end < start:
                    return self.send(416, b"", "video/mp4", {"Content-Range": f"bytes */{size}"})
                with open(review.video, "rb") as f:
                    f.seek(start)
                    body = f.read(end - start + 1)
                return self.send(206, body, "video/mp4", {"Accept-Ranges": "bytes", "Content-Range": f"bytes {start}-{end}/{size}"})
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            if self.command != "HEAD":
                with open(review.video, "rb") as f:
                    while chunk := f.read(CHUNK):
                        self.wfile.write(chunk)

        def do_POST(self):
            if self.path != "/answer":
                return self.send(404, b"nicht gefunden", "text/plain; charset=utf-8")
            origin = self.headers.get("Origin")
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if origin and origin != expected_origin:
                return self.json(403, {"ok": False, "error": "fremder Ursprung"})
            if self.headers.get_content_type() != "application/json":
                return self.json(415, {"ok": False, "error": "Content-Type muss application/json sein"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > MAX_ANSWER_BYTES:
                    return self.json(413, {"ok": False, "error": "Antwort ist zu groß"})
                body = json.loads(self.rfile.read(length) or b"{}")
                return self.json(200, review.answer(body))
            except (AnswerError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as error:
                return self.json(400, {"ok": False, "error": str(error)})
    return Handler


def make_server(review: Review, port: int = 8766) -> ThreadingHTTPServer:
    """Server nur für den eigenen Rechner (127.0.0.1)."""
    return ThreadingHTTPServer(("127.0.0.1", port), handler(review))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("det")
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args(argv)
    review = Review(args.video, args.det)
    server = make_server(review, args.port)
    print(f"{len(review.spots)} Stellen, offen {review.open()}. Im Browser öffnen: http://127.0.0.1:{server.server_port}/ "
          "(beenden mit Strg+C; jede Antwort ist sofort gespeichert)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
