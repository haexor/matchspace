# Contract: Schnittstelle des Markierwerkzeugs

Server `tools/review_server.py`, nur an `127.0.0.1`. Keine Anmeldung, weil nur der eigene Rechner zugreift.
Andere Pfade als die hier genannten liefern 404; Pfade außerhalb von `web/review/` und der übergebenen Szene sind
nicht erreichbar.

| Methode, Pfad | Antwort |
|---|---|
| `GET /` | Seite `web/review/index.html` |
| `GET /review.js`, `GET /review.css` | Skript und Stil der Seite |
| `GET /video` | Szenenvideo, mit `Range` (206 Partial Content), `Content-Type: video/mp4` |
| `GET /spots` | `{scene, fps, lensSize, spots: [Spot], answers: {spotId: Answer}, open: n}` |
| `POST /answer` | Body `Answer` (siehe [../data-model.md](../data-model.md)); prüft Form und Widersprüche, speichert atomar; Antwort `{ok, warnings: [..], open: n}` |

- **Widersprüche** (FR-015) kommen als `warnings` zurück, die Antwort wird trotzdem gespeichert:
  - dieselbe Person zur selben Zeit an zwei Orten;
  - dieselbe Nummer bei zwei Personen einer Mannschaft;
  - eine Person in zwei Mannschaften.
- **Speichern**: Die Referenzdatei wird in eine temporäre Datei daneben geschrieben und umbenannt; ein Absturz
  hinterlässt nie eine halbe Datei.
- **Seite**: lädt keine Ressourcen von außen (keine CDN, keine Schriften), setzt keine Cookies.
