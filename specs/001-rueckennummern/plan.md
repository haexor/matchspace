# Implementation Plan: Rückennummern aus dem Video

**Branch**: `001-rueckennummern` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-rueckennummern/spec.md`

## Summary

Jede eigene Spielerspur bekommt ihre Rückennummer aus den Videobildern, ohne Veo. Der Ablauf hat vier
Schritte:

1. **Ausschnitte**: Aus den vorhandenen Gelenkpunkten werden Rückenausschnitte von Spielern geschnitten,
   die der Kamera den Rücken zeigen.
2. **Lesen**: Ein kleines, lokal trainiertes Netz liest die Ausschnitte. Es kennt 100 Klassen: die Nummern
   1–99 und „keine“. Trainiert wird nur auf synthetischen Rückennummern.
3. **Abstimmung je Spur**: Eine Nummer wird nur bei klarer Mehrheit vergeben, sonst bleibt sie unbekannt.
4. **Vergabe je Mannschaft**: Keine Nummer doppelt zur selben Zeit. Spurstücke mit gleicher Nummer werden zu
   einem Spieler zusammengeführt.

Der Viewer zeigt die Nummern auf Trikot, Schild und Auswahl; unbekannte Spieler sind gekennzeichnet. Ein
getrenntes Messwerkzeug vergleicht mit Veos Nummern und ändert nichts am Ergebnis. Begründungen stehen in
[research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (`.venv`), JavaScript (ES-Module, Three.js r170) im Viewer

**Primary Dependencies**: vorhanden und ausreichend: Torch 2.15 mit CUDA, OpenCV, NumPy, SciPy und Pillow.
Keine neue Abhängigkeit.

**Storage**: Dateien.
- Zwischenstände unter `data/work/`: `{det}.numbers.npz`.
- Modell unter `models/jersey-digits.pt`.
- Viewer-Daten unter `web/data/…/meta.json`.

Alle drei Orte sind gitignored.

**Testing**: `unittest` aus der Standardbibliothek, Tests unter `tests/test_*.py`. Ende-zu-Ende nach
[quickstart.md](quickstart.md).

**Target Platform**: Linux-Rechner mit NVIDIA-GPU (RTX A2000, 8 GB); läuft auch auf der CPU, dann langsamer.

**Project Type**: Kommandozeilen-Werkzeuge (`tools/`) plus statischer Web-Viewer (`web/`)

**Performance Goals**: Lesen und Vergabe kosten höchstens 5 Minuten mehr je 25-Sekunden-Szene (SC-005).
Erwartet sind rund 1–2 Minuten, weil das Video einmal dekodiert wird und das Netz nur wenige tausend kleine
Ausschnitte rechnet.

**Constraints**:
- Kein Netzzugriff.
- Keine Bilder in eingecheckten Dateien oder in `web/data`.
- Veo nur im Messwerkzeug.
- Spielerhöhe rund 55 px, Rückenhöhe 24–60 px.

**Scale/Scope**: zwei Referenzszenen zu je 25 s, rund 40 Spuren und 20–25 echte Spieler je Szene

Offene Punkte (NEEDS CLARIFICATION): keine; alle Entscheidungen in [research.md](research.md).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Geprüft gegen `.spaex/constitution.md`. Die Spec-Kit-Verfassung `.specify/memory/constitution.md` ist eine
unausgefüllte Vorlage und gilt nicht.

| Regel (Modalität) | Stand | Nachweis |
|---|---|---|
| Worktree auf Topic-Branch (MUST) | ✅ | `../matchspace.worktrees/001-rueckennummern`, Branch `001-rueckennummern`; Haupt-Checkout nur zum Lesen |
| Conventional Commits (MUST) | ✅ | `docs(specs): …`, geplant `refactor:`, `feat:`, `test:`, `chore:` |
| Keine Agenten-Selbstreferenz (MUST) | ✅ | keine Trailer, keine Hinweise in Code oder Doku |
| Tests in eigenen Dateien, Tests mit Verhaltensänderung (MUST) | ✅ | `tests/test_jersey_*.py`, `tests/test_own_scene.py`; `unittest` |
| Dateien über 500 Zeilen aufteilen oder begründen und planen (MUST) | ⚠️ begründet | neue Module je < 400 Zeilen; Bestand siehe Complexity Tracking |
| Umbau getrennt von Verhaltensänderung (SHOULD) | ✅ | Auslagern aus `veo_scene.py` als eigener `refactor:`-Commit vor dem Feature |
| ADR für grundsätzliche Entscheidungen (MUST) | ✅ geplant | `docs/adr/0001-rueckennummern-ohne-fremddaten.md`: eigener Erkenner, nur synthetisch trainiert, Veo nur als Referenz, alles lokal |
| Keine absoluten lokalen Pfade (MUST NOT) | ✅ | Schriften über `fc-match` zur Laufzeit, Modell relativ zum Repo; Doku mit relativen Pfaden |
| Keine Geheimnisse (MUST NOT) | ✅ | keine Zugangsdaten nötig |
| PR nach main (MUST) | ⚠️ offen | noch kein Remote; Branch bleibt bis zum PR stehen, kein direkter Merge nach main |
| Phasen-Disziplin (MUST) | ✅ | baut auf dem eigenen Tracking auf, das für die Szenen schon läuft; Folgefeatures (Aussehen, Aufteilung) nur benannt |
| Selbständernde Anweisungen nur per Review (MUST) | ✅ | keine Änderung an Skills, Verfassung oder Rechten |
| Spec-Kit-Ablauf (MUST) | ✅ | specify → Freigabe → plan → Freigabe → tasks → implement |
| graphify-first (MUST) | ⚠️ Werkzeug fehlt | kein `graphify-out/` im Worktree-Snapshot → Warnung, Kandidaten von Hand geprüft (siehe unten) |
| Ponytail: keine neue Abhängigkeit, Bestand nutzen (Leitlinie) | ✅ | Torch, OpenCV, PIL vorhanden; Wiederverwendung siehe unten |
| Python: Typen, `dataclass`, Prüfung an der Grenze (Leitlinie) | ✅ | `Reading`, `TrackNumber`, `Player` als `dataclass`; Kader wird beim Einlesen geprüft |
| Datenschutz (Projektvorgabe) | ✅ | keine externen Dienste; Ausschnitte nur im Speicher oder unter `data/work/`; Viewer bekommt nur Nummern |

**Geprüfte Kandidaten zum Wiederverwenden** (graphify-Ersatz, von Hand):

| Kandidat | Entscheidung |
|---|---|
| `track_players.compare_veo` | wird für die Zuordnung im Messwerkzeug wiederverwendet; die Zuordnung wird dazu als Funktion herausgelöst, damit sie zurückgibt statt nur zu drucken |
| `track_players.stitch` | verbindet Stücke nach Lage; das Zusammenführen nach Nummer ist ein anderes Kriterium und kommt als eigene Funktion `merge_by_number` in `jersey_identity.py`. `stitch` bleibt unverändert |
| `track_players.track_hues`, Bildzugriff in `veo_looks.py` | Muster für den einmaligen Videodurchlauf |
| `veo_scene` VOTE_WINDOW/MIN_VOTES | stimmt über Veo-Zuordnungen ab, nicht über Lesungen; passt nicht |
| `avatar.js` `numberTexture`, `main.js` `numberSprite` | unverändert genutzt; der Rücken zeigt die Nummer schon über der Videotextur |

Ergebnis: **Gate bestanden**. Die drei ⚠️ sind begründet und haben einen Plan; kein Verstoß ohne
Begründung.

## Project Structure

### Documentation (this feature)

```text
specs/001-rueckennummern/
├── spec.md
├── plan.md              # dieser Plan
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/           # Phase 1: cli, numbers-cache, squad-list, viewer-entities, eval-report
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
tools/
├── own_scene.py         # NEU (Umbau): own_identities, own_ball, attach_ball aus veo_scene.py; ruft Nummern auf
├── jersey_synth.py      # NEU: synthetische Rückenausschnitte für das Training (Schriften über fc-match)
├── jersey_reader.py     # NEU: Netz, Training (CLI train), Ausschnitte aus Gelenkpunkten, Lesen (CLI read)
├── jersey_identity.py   # NEU: Abstimmung je Spur, Kaderfilter, Vergabe ohne Doppel, merge_by_number (reine Logik)
├── jersey_eval.py       # NEU: Messung gegen Referenz (nur Prüfung, importiert veo_tracks)
├── track_players.py     # ÄNDERUNG: Zuordnung aus compare_veo als wiederverwendbare Funktion
└── veo_scene.py         # ÄNDERUNG: nutzt own_scene, --kader, Entitäten mit number/label

web/
└── main.js              # ÄNDERUNG: Auswahl "Wir ? (S4)", Schild "?" für unbekannt (wenige Zeilen)

tests/
├── test_jersey_identity.py
├── test_jersey_reader.py   # Rücken-Erkennung, Viereck, Mindestgröße
├── test_jersey_synth.py
├── test_jersey_eval.py
└── test_own_scene.py       # Entitäten: number/label, IDs ohne Überschneidung

docs/adr/
└── 0001-rueckennummern-ohne-fremddaten.md

.gitignore               # ÄNDERUNG: __pycache__/
README.md                # ÄNDERUNG: Training, Lesen, Messen, Grenzen
```

**Structure Decision**: Es bleibt bei der flachen Struktur aus `tools/` und `web/`.
- Die Nummern bekommen eigene Module, nach Verantwortung getrennt:
  - Trainingsdaten in `jersey_synth.py`;
  - Netz und Lesen in `jersey_reader.py`;
  - Vergabe in `jersey_identity.py`, reine Logik und gut testbar;
  - Messung in `jersey_eval.py`, damit Veo nicht im Produktionspfad steckt.
- Neu ist der Ordner `tests/`, im Projekt der erste.

## Ablauf (Überblick)

```text
track_players.track ──▶ own_scene.own_identities ──▶ jersey_reader.read (Video einmal, Gelenkpunkte)
                                                        │  {det}.numbers.npz
                                                        ▼
                                  jersey_identity: Abstimmung ▶ Kader ▶ Vergabe ohne Doppel ▶ merge_by_number
                                                        │  {(Mannschaft, Nummer|1000+k): Spurstücke}
                                                        ▼
                                  veo_scene: Positionen, Haltung, meta.json (number | label) ──▶ veo_looks ──▶ Viewer
jersey_eval (getrennt): meta.json + Veo ──▶ Bericht unter data/work/
```

## Reihenfolge der Umsetzung (für /speckit-tasks)

1. `chore:` `.gitignore` um `__pycache__/` ergänzen; `tests/` anlegen.
2. `refactor:` Teile ohne Veo aus `veo_scene.py` nach `tools/own_scene.py` auslagern, ohne
   Verhaltensänderung. Prüfung: Die Szene 705 ohne Veo ergibt dieselbe `meta.json`.
3. `feat:` US1:
   - `jersey_synth.py` und `jersey_reader.py` (train, read);
   - `jersey_identity.py` (Abstimmung, Kader);
   - Einbindung in `own_scene`;
   - Tests.
4. `feat:` US2: Vergabe ohne Doppel und `merge_by_number`, Tests.
5. `feat:` US3: Viewer-Kennzeichnung, Entitäten nach Contract.
6. `feat:` US4: `jersey_eval.py`, Zuordnung aus `track_players` herauslösen, Tests.
7. `docs:` ADR 0001, README.
8. Messen an beiden Szenen und Schwellen an 705 einstellen. Danach an 722 prüfen, gegebenenfalls
   Rückfallebenen aus research.md R9 nehmen. Die Ergebnisse kommen in den PR-Text.

## Complexity Tracking

| Abweichung | Warum nötig | Einfachere Alternative verworfen, weil |
|---|---|---|
| `tools/veo_scene.py` bleibt über 500 Zeilen (999, nach dem Auslagern rund 900) | `main()` ist eine 600 Zeilen lange Kette von Stufen. Sie ganz zu zerlegen, ist ein großer Umbau ohne Bezug zu den Nummern und würde das Feature-Review überladen. | Jetzt alles zerlegen: vermischt Umbau und Feature. **Plan**: Folgefeature „Szenenauswertung in Stufen aufteilen“ zerlegt `main()` in `identities`, `positions`, `ground_poses`, `fit_poses` und `write_scene`, je ein Modul unter 400 Zeilen; Start nach dem Merge dieses Features. |
| `web/main.js` (855), `web/avatar.js` (614) bleiben über 500 Zeilen | Hier ändern sich nur wenige Zeilen (Auswahl, Schild). | Aufteilen jetzt: kein Bezug zum Feature. **Plan**: im selben Folgefeature `main.js` in Laden, Szene/Akteure und Bedienung trennen; `avatar.js` in Modellaufbereitung und Material/Shader. |
| `tools/pose_limits.py` (617) bleibt über 500 Zeilen | wird nicht angefasst | **Plan**: Schrittplaner (`step_plan`, `plant_feet`, `body_pace`) in ein eigenes Modul, im selben Folgefeature. |
| PR nach main noch nicht möglich | kein Remote eingerichtet | Direkt nach main mergen verstößt gegen die Verfassung; der Branch wartet auf das Remote. |
