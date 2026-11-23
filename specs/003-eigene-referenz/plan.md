# Implementation Plan: Eigene Referenz statt Veo

**Branch**: `003-eigene-referenz` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-eigene-referenz/spec.md`

## Summary

Die Messung soll nicht mehr Veo als Wahrheit nehmen, und der Betrieb soll ganz ohne Veo-Daten laufen.

1. **Strittige Stellen finden**: aus der Zuordnung der Auswertung, nach festen Gründen (Verdeckung, Spurende mitten
   auf dem Platz, Trennung, Verbindung, Nummer, Widerspruch zu Veo) plus 5 zufällige Kontrollstellen
   ([research.md](research.md) R1).
2. **Entscheiden lassen**: ein lokales Markierwerkzeug (Python-Standardbibliothek als Server, schlichte Seite)
   spielt je Stelle einen kurzen Ausschnitt; eine Taste beantwortet „wer ist danach wer“ (R3).
3. **Referenz und Messung**: Personen aus Abschnitten und Antworten (R2). Gemessen wird je Erkennung statt über die
   Lage der Szene. Veo steht als zweite Spalte daneben, ohne pauschalen Versatz (R4).
4. **Lage an Platzlinien**: Steht ein Fuß auf einer Linie, ist die wahre Lage bekannt. Daraus folgt, welche Quelle
   in der Tiefe richtig liegt. Liegt die Szene falsch, wird es behoben (R5).
5. **Ohne Veo**:
   - eigene Spielbeschreibung statt Veo-Basisspiel (R7);
   - Kalibrierung ohne Veos Kameralage und Ecken (R6);
   - Nachweis per Audit-Hook (R8).

## Technical Context

**Language/Version**: Python 3.12 (`.venv`); Seite des Markierwerkzeugs in schlichtem JavaScript (wie der Viewer)

**Primary Dependencies**: vorhanden: NumPy, SciPy, OpenCV; neu nur Standardbibliothek (`http.server`). Keine neue
Bibliothek, kein neues Modell.

**Storage**: lokal unter `data/work/<aufnahme>/`:
- `{det}.identity.json`: Zuordnung der Auswertung;
- `{det}.reference.json`: Stellen und Antworten;
- `spiel.json`: Spielbeschreibung;
- Berichte.

Eigener Spielordner unter `web/data/<spiel>/` (nicht eingecheckt).

**Testing**: `unittest`. Neue Dateien:
- `tests/test_review_spots.py`, `tests/test_reference.py`, `tests/test_review_server.py`;
- `tests/test_line_check.py`, `tests/test_own_match.py`, `tests/test_no_veo_check.py`.

Erweitert wird `tests/test_jersey_eval.py`.

**Target Platform**: Linux; Markierwerkzeug in Chromium oder Firefox auf demselben Rechner

**Project Type**: Kommandozeilen-Werkzeuge (`tools/`) plus eine lokale Seite (`web/review/`)

**Performance Goals**: Stellen finden unter 10 s je Szene; Seite springt ohne spürbare Wartezeit zur nächsten
Stelle; Entscheiden höchstens 10 Minuten je Szene (SC-001); Lageprüfung unter 1 Minute je Szene

**Constraints**:
- Bilder verlassen den Rechner nicht; der Server lauscht nur an `127.0.0.1`.
- Die Seite lädt nichts von außen.
- Keine Namen.
- Veo nur mit `--veo`.

**Scale/Scope**: zwei Referenzszenen mit je 30–50 strittigen Stellen, rund 40 Spielern und rund 1000
Linienereignissen

Offene Punkte (NEEDS CLARIFICATION): keine.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Geprüft gegen `.spaex/constitution.md`.

| Regel (Modalität) | Stand | Nachweis |
|---|---|---|
| Worktree auf Topic-Branch (MUST) | ✅ | `../matchspace.worktrees/003-eigene-referenz`, Branch `003-eigene-referenz` auf `002-spieler-identitaet` |
| Conventional Commits, keine Selbstreferenz (MUST) | ✅ | wie in 001/002 |
| Tests in eigenen Dateien (MUST) | ✅ | sechs neue Testdateien, siehe oben |
| Dateien über 500 Zeilen (MUST) | ✅ mit Begründung | neue Module je unter 400 Zeilen. `veo_scene.py` (900) wird nur an der Stelle „Basisspiel lesen“ geändert (rund 20 Zeilen), die Aufteilung bleibt Folgefeature wie in 001. `veo_camera.py` (436) bleibt unter 500. |
| Umbau getrennt von Verhalten (SHOULD) | ✅ | Zuordnungsdatei zuerst ohne Verhaltensänderung, eigener Commit |
| ADR (MUST) | ✅ geplant | `docs/adr/0003-eigene-referenz.md`: Veo nur als zweite Meinung; Wahrheit aus eigenen Antworten und Platzgeometrie; Linsendaten bleiben Eingabe |
| Keine absoluten Pfade, keine Geheimnisse (MUST NOT) | ✅ | Pfade als Argumente; Server liefert nur freigegebene Dateien |
| PR nach main (MUST) | ⚠️ offen | kein Remote; Branch baut auf 002 auf |
| Phasen-Disziplin (MUST) | ✅ | baut auf 002 auf, das für beide Szenen läuft |
| graphify-first (MUST) | ✅ mit Hinweis | Graph-Snapshot vor 001 gebaut; Abfrage plus Prüfung von Hand, siehe unten |
| Ponytail: keine neue Abhängigkeit (Leitlinie) | ✅ | nur Standardbibliothek; keine CDN in der Seite |
| Datenschutz (Projektvorgabe) | ✅ | Referenz ohne Bilder und Namen; Server nur lokal; Bildschirmfotos nur im Scratchpad |

**Geprüfte Kandidaten** (graphify-Abfrage nach Linien, Kalibrierung, Uhr, Server; dazu Code von Hand):

| Kandidat | Entscheidung |
|---|---|
| `veo_camera.model_lines`, `Fit.line_residuals`, `project`, `to_ground` | werden für die Lageprüfung wiederverwendet (Linien des Normplatzes, Projektion ins Bild) |
| `veo_camera.main` (Start aus `read_veo` und `veo_corners`) | Start wird ersetzt (Gitter), `read_veo` liefert nur noch die Linsendaten |
| `veo_scene.main` (Basisspiel: Abschnitte, Uhr, Platz, Mannschaften, Bewegungsdaten) | liest im Betrieb ohne Veo nur noch den eigenen Spielordner |
| `jersey_eval` (`evaluate`, `wrong_time_share`, `switches`, `depth_offset`) | Kennzahlen bleiben, die Wahrheit wird austauschbar (Referenz oder Veo); `depth_offset` und `shift_depth` entfallen |
| `identity_link`, `own_scene.split_and_link` | liefern Trennungen und Verbindungen für die strittigen Stellen; `own_scene` schreibt die Zuordnungsdatei |
| `track_players.match_reference` | bleibt für die Veo-Spalte (Abgleich über Bodenlage) |
| Viewer `web/main.js` | unverändert; die Seite des Markierwerkzeugs ist getrennt (`web/review/`) |

**Ergebnis**: Gate bestanden.

## Project Structure

### Documentation (this feature)

```text
specs/003-eigene-referenz/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/            # cli, review-api, eval-report, match-description
├── checklists/requirements.md
└── tasks.md              # /speckit-tasks
```

### Source Code (repository root)

```text
tools/
├── review_spots.py      # NEU: strittige Stellen und Kontrollstellen finden, Referenzdatei anlegen/ergänzen
├── reference.py         # NEU: Personen aus Abschnitten und Antworten, Wiederfinden, Widersprüche (reine Logik)
├── review_server.py     # NEU: lokaler Server für das Markierwerkzeug (Standardbibliothek)
├── line_check.py        # NEU: Lage an Platzlinien je Quelle
├── own_match.py         # NEU: Spielbeschreibung -> eigener Spielordner
├── no_veo_check.py      # NEU: Audit-Hook-Prüflauf
├── own_scene.py         # ÄNDERUNG: schreibt {det}.identity.json
├── jersey_eval.py       # ÄNDERUNG: Wahrheit = eigene Referenz; Veo optional als zweite Spalte
├── veo_scene.py         # ÄNDERUNG (klein): ohne Veo nur eigener Spielordner
└── veo_camera.py        # ÄNDERUNG: Start ohne Veo-Kameralage und -Ecken

web/review/
├── index.html, review.js, review.css   # NEU: Markierwerkzeug

tests/ (siehe Testing)
docs/adr/0003-eigene-referenz.md
README.md
```

**Structure Decision**: Reine Logik (`reference.py`, Teile von `review_spots.py`) ist getrennt von Datei- und
Netzzugriff. Die Seite liegt getrennt vom Viewer, damit dieser unverändert bleibt.

## Ablauf

```text
veo_scene (ohne Veo, eigener Spielordner) ──▶ {det}.identity.json
review_spots ──▶ {det}.reference.json (Stellen)
review_server + web/review ──▶ Nutzer entscheidet ──▶ {det}.reference.json (Antworten)
jersey_eval: identity + reference ──▶ Kennzahlen; optional --veo: zweite Spalte und Widersprüche
line_check: Fußgelenke auf Platzlinien ──▶ Tiefenfehler je Quelle ──▶ ggf. Korrektur in veo_scene
no_veo_check: Prüflauf ohne Zugriff auf Veo-Dateien
```

## Reihenfolge der Umsetzung (für /speckit-tasks)

1. `refactor(identity):` `own_scene` schreibt `{det}.identity.json` (ohne Verhaltensänderung).
2. `feat(reference):` `reference.py` und `review_spots.py` mit Tests; Zahl der Stellen je Szene messen (Erwartung
   30–50).
3. `feat(reference):` `review_server.py` und `web/review/` mit Tests; Bildschirmfoto im Scratchpad.
4. **Nutzerschritt**: Ihr entscheidet die strittigen Stellen von 705 und 722, Zeit gestoppt, dazu 5 Wiederholungen
   je Szene. Ohne diesen Schritt gibt es keine eigenen Messwerte.
5. `feat(numbers):` `jersey_eval.py` gegen die Referenz, Veo als zweite Spalte; Messwerte aus 001/002 neu
   bestimmen.
6. `feat(scene):` `line_check.py`. Danach ist entschieden, ob die Szene den Versatz trägt. Falls ja:
   `fix(scene):` Korrektur in `veo_scene` und neue Prüfung.
7. `feat(scene):` `own_match.py`, `veo_scene` ohne Veo-Basisspiel; `feat(camera):` Start ohne Veo;
   `no_veo_check.py`; Vergleichslauf.
8. `docs:` ADR 0003, README, Ergebnisse.

Die Schritte 6 und 7 hängen nicht am Nutzerschritt und können vorgezogen werden, während markiert wird.

## Complexity Tracking

| Abweichung | Warum nötig | Einfachere Alternative verworfen, weil |
|---|---|---|
| Eigener kleiner HTTP-Server | Video mit Springen (Range-Anfragen) und sofortiges Speichern der Antworten | `python -m http.server` kann kein Speichern und keine Range-Anfragen; Herunterladen von Antworten ist fehleranfällig |
| `veo_scene.py` über 500 Zeilen wird angefasst | Basisspiel-Zugriff sitzt dort | Aufteilen wäre ein eigenes Umbau-Feature; die Änderung ist klein und getestet |
| PR nach main noch nicht möglich | kein Remote | wie in 001/002 |
