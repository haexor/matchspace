# Contract: Kommandozeile

Alle Werkzeuge lesen und schreiben nur lokal. Berichte und Referenzen nur unter `data/work/`
(`jersey_reader.check_private_dir`).

## Strittige Stellen erzeugen

```text
.venv/bin/python tools/review_spots.py DETEKTIONEN.json KAMERA.json [--veo VEO_ORDNER VEO_ALIGN.json START_S] [--kontrolle 5]
```

- Liest `{DETEKTIONEN}.identity.json` (aus dem letzten Szenenlauf) und schreibt oder ergänzt
  `{DETEKTIONEN}.reference.json`.
- Vorhandene Antworten bleiben; ihre Stellen werden über die Anker wiedergefunden, verwaiste werden gemeldet.
- Ausgabe: Zahl der Stellen je Grund, davon offen.
- `--veo`: zusätzlich Stellen „Veo sieht anders“. Ohne die Angabe wird nichts von Veo gelesen.

## Markierwerkzeug

```text
.venv/bin/python tools/review_server.py SZENENVIDEO DETEKTIONEN.json [--port 8766]
```

- Startet den Server an `127.0.0.1` und nennt die Adresse (`http://127.0.0.1:8766/`).
- Schnittstelle siehe [review-api.md](review-api.md). Beenden mit Strg+C; jede Antwort ist dann schon
  gespeichert.

## Messen

```text
.venv/bin/python tools/jersey_eval.py DETEKTIONEN.json KAMERA.json [--veo VEO_ORDNER VEO_ALIGN.json START_S] [--bericht B.json] [--lesezeit S]
```

- **Geändert gegenüber Feature 002**:
  - Die Wahrheit ist die eigene Referenz `{DETEKTIONEN}.reference.json` zusammen mit `{DETEKTIONEN}.identity.json`.
  - Veo ist optional und erscheint als zweite Spalte.
  - Der Szenenordner wird nicht mehr gebraucht; gemessen wird je Erkennung.
- Bericht siehe [eval-report.md](eval-report.md).

## Lage an Platzlinien prüfen

```text
.venv/bin/python tools/line_check.py SZENENVIDEO DETEKTIONEN.json KAMERA.json SZENE_ORDNER [--veo VEO_ORDNER VEO_ALIGN.json START_S] [--bericht B.json]
```

Gibt je Quelle (fertige Szene, Boxunterkante, Fußpunkt, Veo) Median und Streuung des Fehlers in Tiefe und quer aus,
dazu die Zahl der Linienstellen je Szene. Bericht siehe [eval-report.md](eval-report.md), Abschnitt `lines`.

## Eigener Spielordner

```text
.venv/bin/python tools/own_match.py SPIEL.json KAMERA.json SPIELORDNER
```

Legt `SPIELORDNER/meta.json` ohne Bewegungsdaten an (siehe [match-description.md](match-description.md)). Danach wie
bisher `veo_ground.py` und `veo_backdrop.py` mit diesem Ordner.

## Szene auswerten (bestehend, ohne Veo geändert)

```text
.venv/bin/python tools/veo_scene.py - KAMERA.json - VIDEO START_S DETEKTIONEN.json SPIELORDNER AUSGABE_SPIEL [--kader KADER.json]
```

- Im Betrieb ohne Veo darf `SPIELORDNER` ein eigener Spielordner sein; aus ihm werden nur Spielabschnitte, Uhr,
  Platz und Mannschaften gelesen.
- Schreibt zusätzlich `{DETEKTIONEN}.identity.json` (siehe [../data-model.md](../data-model.md)).

## Nachweis „ohne Veo“

```text
.venv/bin/python tools/no_veo_check.py [--verbiete ORDNER …] [--erlaube DATEI …] WERKZEUG.py [ARGUMENTE …]
```

Führt ein Werkzeug mit einem Audit-Hook aus. Er bricht mit Fehler ab, sobald eine Datei unter `data/raw/veo/` oder
im Veo-Basisspiel (`--verbiete web/data/veo-2026-11-01`, mehrfach möglich) geöffnet wird. Einzelne Dateien der
Aufnahme selbst (Panoramavideo, Linsendaten der Kamera) lassen sich mit `--erlaube PFAD` freigeben. Ausgabeordner
der Szenen sind nicht betroffen, auch wenn ihr Name mit `veo-` beginnt.

## Kamera kalibrieren (bestehend, Start geändert)

```text
.venv/bin/python tools/veo_camera.py VIDEO HANDPUNKTE.json LINSEN.json KAMERA.json
```

- Startet ohne Veos Kameralage aus einem Gitter möglicher Lagen.
- `LINSEN.json` liefert nur noch die Linsendaten der Kamera.
- `-` statt Handpunkten (Start aus Veos Ecken) entfällt, mit klarer Meldung.
