# Contract: Kommandozeile

Alle Aufrufe aus dem Wurzelverzeichnis des Repos, Python aus `.venv`. Pfade in den Beispielen sind relativ.

## Erkenner trainieren (einmalig, nicht Teil der Szenenzeit)

```text
.venv/bin/python tools/jersey_reader.py train [--out models/jersey-digits.pt] [--negatives DETEKTIONEN.json ...] [--seed 0]
```

- Erzeugt synthetische Ausschnitte (tools/jersey_synth.py) und trainiert das Netz.
- `--negatives`: optionale Szenen, aus denen Ausschnitte von Spielern, die der Kamera zugewandt sind, als
  „keine Nummer“ dienen. Sie werden nur im Speicher gehalten.
- Gibt am Ende die Trefferquote auf einem zurückgehaltenen synthetischen Satz aus.
- Exit 0 bei Erfolg; Exit ≠ 0 mit Meldung, wenn keine passende Schrift gefunden wird (`fc-match`).

## Nummern einer Szene lesen (Prüfung einzeln)

```text
.venv/bin/python tools/jersey_reader.py read SZENENVIDEO DETEKTIONEN.json KAMERA.json [--crops ORDNER]
```

- Lesungen aller eigenen Spuren nach `{DETEKTIONEN}.numbers.npz` (siehe [numbers-cache.md](numbers-cache.md)).
- `--crops`: schreibt Ausschnitte zum Prüfen; der Ordner MUSS unter `data/work/` liegen, sonst bricht der
  Aufruf ab (FR-009).
- Gibt je Spur die beste Nummer und Sicherheit aus.

## Szene auswerten ohne Veo (bestehend, erweitert)

```text
.venv/bin/python tools/veo_scene.py - KAMERA.json - VIDEO START_S DETEKTIONEN.json BASIS_SPIEL AUSGABE_SPIEL [--kader KADER.json]
```

- Liest die Nummern selbst, wenn der Zwischenspeicher fehlt oder älter als Video, Detektionen oder Modell ist.
- `--kader`: optional, siehe [squad-list.md](squad-list.md).
- Ohne `models/jersey-digits.pt`: läuft wie bisher, alle Spieler ohne Nummer, Hinweis auf der Konsole.
- Schreibt Entitäten nach [viewer-entities.md](viewer-entities.md).

## Messen gegen eine Referenz (nur zum Prüfen)

```text
.venv/bin/python tools/jersey_eval.py AUSGABE_SPIEL DETEKTIONEN.json VEO_ORDNER VEO_ALIGN.json START_S [--bericht BERICHT.json]
```

- Liest die fertige Szene und Veo-Daten; schreibt nie in `AUSGABE_SPIEL`.
- Ausgabe auf der Konsole und optional als JSON (siehe [eval-report.md](eval-report.md)); der Bericht MUSS
  unter `data/work/` liegen.
