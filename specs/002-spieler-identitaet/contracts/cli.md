# Contract: Kommandozeile

## Szene auswerten ohne Veo (bestehend, Verhalten erweitert)

```text
.venv/bin/python tools/veo_scene.py - KAMERA.json - VIDEO START_S DETEKTIONEN.json BASIS_SPIEL AUSGABE_SPIEL [--kader KADER.json]
```

- **Ablauf**: Trennt Spurwechsel und verbindet Stücke derselben Person, bevor Nummern vergeben werden. Die
  Konsole nennt Kontakte, Trennungen und Verbindungen.
- **Zwischenspeicher**: Fehlt `{DETEKTIONEN}.appearance.npz` oder ist er veraltet, werden die Merkmale
  einmal berechnet. Das Modell liegt lokal unter `models/hf`; fehlt es, laufen Trennen und Verbinden nur
  mit Weg und Nummer, mit Hinweis.
- **Ausgabe**: unverändert nach `specs/001-rueckennummern/contracts/viewer-entities.md`.

## Prüfen einzeln

```text
.venv/bin/python tools/identity_link.py SZENENVIDEO DETEKTIONEN.json KAMERA.json
```

Gibt Kontakte mit Belegen, Trennungen und Verbindungen mit Kosten und Abstand zum Zweitbesten aus. Schreibt
nur den Zwischenspeicher.

## Messen (bestehend, Bericht erweitert)

```text
.venv/bin/python tools/jersey_eval.py SZENE_ORDNER DETEKTIONEN.json KAMERA.json VEO_ORDNER VEO_ALIGN.json START_S [--bericht B.json] [--lesezeit S]
```

Zusätzlich im Bericht (siehe [eval-report.md](eval-report.md)): `wrongTimeShare` und `switches`.
