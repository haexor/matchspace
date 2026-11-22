---
description: "Aufgabenliste: Rückennummern aus dem Video"
---

# Tasks: Rückennummern aus dem Video

**Input**: Design documents from `specs/001-rueckennummern/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Die spaex-Verfassung verlangt Tests mit jeder Verhaltensänderung, in eigenen Dateien. Deshalb hat
jede Story Testaufgaben.
- Werkzeug: `unittest` aus der Standardbibliothek.
- Aufruf: `.venv/bin/python -m unittest discover -s tests`.
- Testdateien setzen `tools/` selbst auf `sys.path`, weil die Werkzeuge keine Paketstruktur haben.

**Organization**: Aufgaben nach User Story gruppiert; jede Story ist für sich prüfbar.

**Regeln für alle Aufgaben**:
- Arbeiten nur im Worktree `../matchspace.worktrees/001-rueckennummern`.
- Commits nach Conventional Commits, ohne Hinweise auf Agenten oder Werkzeuge und ohne `Co-authored-by`.
- Keine absoluten Pfade in eingecheckten Dateien.
- Kein Bild und kein Ausschnitt eines Spielers in eingecheckten Dateien oder unter `web/data/`.
- Keine Netzzugriffe.
- Neue Python-Funktionen mit Typangaben.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallel möglich (andere Datei, keine offene Abhängigkeit)
- **[Story]**: US1–US4 aus [spec.md](spec.md)

---

## Phase 1: Setup

**Purpose**: Testgerüst und Aufräumen, bevor Code entsteht

- [ ] T001 `__pycache__/` in `.gitignore` aufnehmen. Commit `chore: ignore python bytecode caches`.
- [ ] T002 Ordner `tests/` mit `tests/__init__.py` (leer) und `tests/helpers.py` anlegen.
  - `helpers.py` fügt `tools/` relativ zur eigenen Datei in `sys.path` ein, mit `Path(__file__).parent`,
    ohne absoluten Pfad.
  - Danach prüfen: `.venv/bin/python -m unittest discover -s tests` findet 0 Tests und endet mit Exit 0.
  - Commit `test: add unittest scaffold`.

---

## Phase 2: Foundational (blockiert alle Stories)

**Purpose**: Teile ohne Veo aus `veo_scene.py` lösen (Umbau ohne Verhaltensänderung), damit die Nummern dort
einhängen können und `veo_scene.py` nicht weiter wächst

- [ ] T003 Vergleichsstand sichern: Szene 705 ohne Veo laut README Schritt 5 mit `-` auswerten.
  - Ziel ist ein Ordner unter `data/work/` außerhalb von `web/data`.
  - Davon `sha256sum` von `meta.json` und `tracks.bin` notieren, lokal und nicht eingecheckt.
- [ ] T004 `tools/own_scene.py` anlegen und aus `tools/veo_scene.py` unverändert hineinverschieben:
  - die Funktionen `own_ball`, `attach_ball`, `own_identities`;
  - die Konstanten `BALL_GAP`, `BALL_REACH`, `BALL_AT_FOOT`, `TEAM_OF_COLOUR`, `KEEPER_INSIDE`, `KEEPER_MIN`,
    `MIN_APPEARANCE`, `OWN_SAME`, `OWN_GAP`, `OWN_ID`.

  `veo_scene.py` importiert sie von dort. Die Docstrings von `veo_scene.py` und `own_scene.py` auf die neue
  Lage anpassen.
- [ ] T005 [P] `tests/test_own_scene.py`:
  - `attach_ball` mit einer synthetischen Fuß- und Ballspur: Ball innerhalb `BALL_REACH` rückt auf
    `BALL_AT_FOOT` an die Fußspitze, weiter weg bleibt er unverändert.
  - `own_ball`: Lücke ≤ `BALL_GAP` wird gerade überbrückt, längere nicht.
- [ ] T006 Szene 705 erneut wie in T003 auswerten. Die Prüfsummen von `meta.json` und `tracks.bin` müssen
  gleich sein. Danach Commit `refactor(scene): move veo-free scene parts to own_scene`.

**Checkpoint**: Szene ohne Veo unverändert, Tests grün; die Stories können beginnen.

---

## Phase 3: User Story 1 – Rückennummer je Spieler aus dem Video (P1) 🎯 MVP

**Goal**: Jede Spur bekommt aus dem Video eine Nummer mit Sicherheit oder bleibt „unbekannt“, ohne Veo.

**Independent Test**: Für die Szene 705 `tools/jersey_reader.py read` aufrufen. Die Konsole nennt je Spur
beste Nummer und Sicherheit; Stichproben am Video stimmen. Spuren ohne lesbaren Rücken bleiben unbekannt.

### Tests für User Story 1

- [ ] T007 [P] [US1] `tests/test_jersey_synth.py`:
  - `make_sample(number, rng)` liefert `uint8[32, 40]`.
  - Gleicher Startwert ergibt gleiche Pixel.
  - Die Klasse 0 („keine Nummer“) ist möglich.
  - Fehlt eine Schrift, kommt eine eigene Ausnahme `FontNotFound` statt eines leeren Bildes. Dazu `fc-match`
    per `unittest.mock` ersetzen.
- [ ] T008 [P] [US1] `tests/test_jersey_reader.py`, je ein Test für:
  - `is_back_view(kp)`: wahr bei `lShoulder.x < rShoulder.x − 2`, Nasen-Sicherheit < 0,5 und Schultern sowie
    Hüften ≥ 0,3; falsch bei Vorderansicht, sicherer Nase oder unsicheren Hüften.
  - `back_quad(kp)`: liefert ein Viereck von der Schulterlinie bis 65 % zur Hüftlinie, Breite 1,15 ×
    Schulterbreite.
  - `back_height(kp)`: unter 24 px gibt es keinen Ausschnitt.
  - `reading_weight(height_px)`: 24 px → 0,3, ≥ 32 px → 1, dazwischen linear.
- [ ] T009 [P] [US1] `tests/test_jersey_identity.py` (Abstimmung, Kader):
  - **Klare Mehrheit**: Eine Spur mit vielen klaren Lesungen 15 bekommt 15.
  - **Ähnliche Ziffern**: Lesungen, die sich auf 6 und 9 verteilen, ergeben unbekannt (FR-003, Szenario 3).
  - **Abhängige Lesungen**: Nur Lesungen in einem einzigen 0,4-s-Fenster ergeben unbekannt (≥ 3 Fenster
    nötig), ebenso drei Fenster innerhalb von 0,8 s (`span_s` ≥ 1 nötig).
  - **„Keine Nummer“**: Lesungen mit p(keine) ≥ 0,5 zählen nicht.
  - **Kader**: Ist er angegeben, wird eine Nummer außerhalb nie vergeben (FR-012).
  - **Schiedsrichter**: Spuren der Mannschaft `referee` bleiben ohne Nummer (FR-006).

### Implementation für User Story 1

- [ ] T010 [P] [US1] `tools/jersey_synth.py`: synthetische Rückenausschnitte nach [research.md](research.md)
  R2.
  - **Schriften**: `find_fonts()` sucht über `fc-match` fette serifenlose Schriften (DejaVu Sans Bold,
    Liberation Sans Bold, DejaVu Sans Condensed Bold) und wirft `FontNotFound`, wenn keine da ist.
  - **Ausschnitt**: `make_sample(number: int, rng: np.random.Generator) -> np.ndarray` mit `number` 0–99,
    0 = keine Nummer. Zufällig gezogen werden:
    - Trikot- und Nummernfarbe mit Mindestkontrast, auch dunkel auf hell;
    - Stofffalten als Helligkeitswellen;
    - Perspektive ±25°, Drehung, Lage, Größe;
    - Verkleinern auf 10–26 px Ziffernhöhe und wieder Vergrößern;
    - Bewegungsunschärfe, Rauschen, JPEG-Qualität 25–80;
    - Verdeckung durch Streifen und abgeschnittene Ziffern.
  - **Ausgabe**: Graustufe 32×40 mit normiertem Kontrast.
  - **Batch**: `batch(n, rng) -> (x, y)` zum Trainieren.
  - Unter 400 Zeilen.
- [ ] T011 [US1] `tools/jersey_reader.py`, Teil Netz und Training (CLI siehe [contracts/cli.md](contracts/cli.md)):
  - **Netz**: kleines CNN mit 100 Ausgängen (0 = keine, n = Nummer n), Eingabe 1×32×40, rund 0,2–0,5 Mio.
    Gewichte.
  - **Training**: `train` mit festem `--seed`, Batches aus `jersey_synth.batch`.
  - **„Keine Nummer“ aus echten Szenen**: optional `--negatives DETEKTIONEN.json …`. Das sind Ausschnitte
    von Spielern, die der Kamera zugewandt sind (`is_back_view` falsch, Nase sicher), nur im Speicher.
  - **Ergebnis**: Ausgabe der Trefferquote auf einem zurückgehaltenen synthetischen Satz. Speichern nach
    `models/jersey-digits.pt` (Standard, relativ zum Repo).
  - GPU, wenn vorhanden, sonst CPU.
- [ ] T012 [US1] `tools/jersey_reader.py`, Teil Ausschnitte:
  - **Funktionen**: `is_back_view`, `back_quad`, `back_height`, `reading_weight` wie in T008.
  - **Ausschnitt**: `crop_back(frame, quad) -> uint8[32, 40]` mit perspektivischer Entzerrung, Graustufe und
    normiertem Kontrast.
  - **Gelenkpunkte**: kommen aus `{det}.keypoints.npz` über `index[frame, lens]` und die Boxnummer
    `row[8]` der Spurzeile (`track_players.detections`, Spalte 8). Linse ist Spalte 3.
  - **Bildzugriff**: wie in `track_players.track_hues` bzw. `tools/veo_looks.py`. Das Video wird einmal
    geöffnet, jedes zweite Bild gelesen.
- [ ] T013 [US1] `tools/jersey_reader.py`, Teil Lesen:
  - **Funktion**: `read_tracks(video, det, keypoints, tracks, model_path) -> list[Reading]`. `Reading` ist
    eine `dataclass` mit den Feldern `track: str`, `frame: int`, `probs: float[100]` („Summe 1“) und
    `weight: float` („0,3 bis 1“).
  - **Ohne Lesung**: Spuren der Mannschaft `referee` werden übersprungen.
  - **Rechnen**: Ausschnitte stapelweise durchs Netz.
  - **Zwischenspeicher**: `{det}.numbers.npz` nach [contracts/numbers-cache.md](contracts/numbers-cache.md)
    mit `stamp` aus den mtime von Video, Detektionen und Modell plus Format-Version. Ist er aktuell, wird
    nicht neu gelesen.
  - **CLI `read`**:
    - gibt je Spur beste Nummer und Sicherheit aus;
    - `--crops ORDNER` schreibt Prüfausschnitte nur, wenn der Ordner unter `data/work/` liegt, sonst Abbruch
      mit Meldung (FR-009).
- [ ] T014 [US1] `tools/jersey_identity.py`, Abstimmung (reine Logik, ohne Datei- oder Videozugriff):
  - **Datentyp**: `TrackNumber` als `dataclass` mit `track`, `ranked: list[tuple[int, float]]`, `windows`
    und `span_s`.
  - **Funktion**: `vote(readings, fps, squad=None) -> dict[str, TrackNumber]`.
  - **Welche Lesungen zählen**: nur mit p(keine) < 0,5; je 0,4-s-Fenster nur die beste.
  - **Spurwert je Nummer**: Σ w · log(p_k + 0,01). Mit Kader werden Nummern außerhalb vor dem Normieren
    entfernt, dann normiert.
  - **Gestützt**: Sicherheit ≥ 0,9, `windows` ≥ 3 und `span_s` ≥ 1. Die Schwellen sind Modulkonstanten mit
    Kommentar.
- [ ] T015 [US1] `tools/jersey_identity.py`: `load_squad(path) -> dict[str, frozenset[int]]` nach
  [contracts/squad-list.md](contracts/squad-list.md).
  - **Erlaubt**: Schlüssel nur `own` und `opponent`; Werte ganze Zahlen 1–99 ohne Doppelte.
  - **Fehler**: Bei Verstoß kommt eine eigene Ausnahme `SquadError` mit Meldung.
  - **Fehlender Schlüssel oder leere Liste**: alle Nummern erlaubt.
- [ ] T016 [US1] Einbindung in `tools/own_scene.py`:
  - **Ablauf**: Nach dem Filtern der Spuren in `own_identities` werden `jersey_reader.read_tracks` und
    `jersey_identity.vote` aufgerufen.
  - **Schlüssel**: Spuren mit gestützter Nummer bekommen `(Mannschaft, Nummer)`, sonst wie bisher
    `(Mannschaft, OWN_ID + k)`.
  - **Bis US2**: Zwei Spuren mit gleichem Schlüssel behalten beide vorläufig `OWN_ID`-Schlüssel (die
    sicherere bekommt die Nummer), bis US2 die Vergabe übernimmt.
  - **Ohne Modell**: Fehlt `models/jersey-digits.pt`, gibt es einen Hinweis, und alle Spuren sind unbekannt
    wie heute.
- [ ] T017 [US1] `tools/veo_scene.py`:
  - **Option**: `--kader KADER.json` annehmen. Sie wird vor der Auswertung mit `load_squad` geprüft und bei
    `SquadError` mit Exit ≠ 0 abgebrochen. Weitergereicht wird sie an `own_identities`.
  - **Uhr**: Die Zeit für das Lesen wird über die vorhandene `clock()` gesondert ausgegeben (SC-005).
  - **Cache-Stempel**: `CACHE_VERSION` erhöhen.
- [ ] T018 [US1] Modell trainieren: `.venv/bin/python tools/jersey_reader.py train --negatives …705… …722…`.
  - Synthetische Trefferquote ≥ 95 %.
  - Dann `read` für beide Szenen laufen lassen und 10 Spuren am Video stichprobenartig prüfen, mit
    `--crops` unter `data/work/`.
  - Ergebnis knapp in den Commit-Text, ohne Bilder.
  - Commit `feat(numbers): read jersey numbers from video with a local recogniser`.

**Checkpoint**: US1 für sich prüfbar: Nummern je Spur auf der Konsole und in `own_identities`, unbekannt
statt geraten.

---

## Phase 4: User Story 2 – Ein Spieler, eine Identität (P2)

**Goal**: Keine Nummer doppelt zur selben Zeit; Stücke mit gleicher Nummer werden ein Spieler.

**Independent Test**: In Szene 705 gegen den Stand vor US2 zählen, in wie viele Identitäten Spieler
zerfallen. Kein Bild hat eine doppelte Nummer je Mannschaft.

### Tests für User Story 2

- [ ] T019 [P] [US2] `tests/test_jersey_identity.py` erweitern (Vergabe, Zusammenführen):
  - **Überlappung**: Zwei zeitlich überlappende Spuren mit derselben besten Nummer → die sicherere behält
    sie. Die andere bekommt ihre zweitbeste nur, wenn auch die gestützt ist, sonst unbekannt (FR-004,
    Szenario 2).
  - **Gleiche Nummer, keine Überlappung**: Zwei Spuren mit derselben Nummer, Lücke mit
    Abstand ÷ Lücke ≤ 8 m/s → ein `Player` mit beiden Stücken (FR-005, Szenario 1).
  - **Zu schnell**: Dasselbe mit > 8 m/s → nicht zusammengeführt, die Nummer bleibt bei der sichereren.
  - **Ohne Nummer**: Unbekannte Spuren werden nie zusammengeführt.
  - **Mannschaften getrennt**: Gleiche Nummer in `own` und `opponent` gleichzeitig ist erlaubt.
  - **Invariante**: In zufälligen Szenarien (fester Startwert) gibt es nie zwei gleichzeitig sichtbare
    Spieler einer Mannschaft mit gleicher Nummer.

### Implementation für User Story 2

- [ ] T020 [US2] `tools/jersey_identity.py`: `Player` als `dataclass` mit `id`, `team`, `tracks`,
  `number: int | None` und `confidence`, dazu `assign(track_numbers, spans, positions) -> list[Player]`.
  - **Vergabe**: je Mannschaft gierig nach Sicherheit absteigend. Konflikt heißt zeitliche Überlappung mit
    einer Spur, die die Nummer schon trägt; dann die zweitbeste, falls gestützt, sonst `None`.
  - **Kommentar**: `ponytail:` mit Ceiling: gierig statt optimaler Zuordnung, Upgrade wäre ganzzahlige
    Optimierung.
- [ ] T021 [US2] `tools/jersey_identity.py`: `merge_by_number(players, positions, fps) -> list[Player]`.
  - **Wann**: gleiche Mannschaft und Nummer, keine Überlappung, Abstand vom Ende zum Anfang ÷ Lücke ≤ 8 m/s
    (Konstante `MERGE_SPEED`).
  - **Ergebnis**: `id` ist die der ersten Spur. `stitch` in `track_players.py` bleibt unverändert.
- [ ] T022 [US2] `tools/own_scene.py`: `assign` und `merge_by_number` statt der vorläufigen Regel aus T016
  verwenden.
  - **Rückgabe**: Ein Spieler mit mehreren Stücken liefert seine Bilder zusammengeführt unter einem Schlüssel
    `(Mannschaft, Nummer)`.
  - **Lücken**: Überbrückt werden sie weiter nur bis `OWN_GAP`. Die vorhandene Entfernung doppelter Spuren
    (`OWN_SAME`) bleibt vor der Vergabe.
- [ ] T023 [US2] Szene 705 und 722 auswerten.
  - Prüfen, dass sich keine Nummer je Mannschaft in einem Bild doppelt.
  - Identitäten je Spieler grob gegen den Stand vor US2 vergleichen (Anzahl der Entitäten).
  - Commit `feat(numbers): keep one identity per jersey number`.

**Checkpoint**: US1 und US2 zusammen; weniger Identitäten, keine Doppel.

---

## Phase 5: User Story 3 – Nummern im Viewer (P3)

**Goal**: Trikot, Schild und Auswahl zeigen die Nummer; unbekannte Spieler sind gekennzeichnet.

**Independent Test**: `?match=veo-szene-705-eigen` öffnen; ein Spieler mit Nummer zeigt sie an allen drei
Stellen, ein unbekannter erscheint als `Wir ? (S4)` ohne Nummer auf dem Trikot.

### Tests für User Story 3

- [ ] T024 [P] [US3] `tests/test_own_scene.py` erweitern: Die Funktion, die eine Entität baut (aus T025),
  liefert:
  - **Nummer bekannt**: `{"id": "own-15", "kind": "player", "team": "own", "number": 15}` ohne `label`.
  - **Nummer unbekannt**: `{"id": "own-1004", …, "label": "S4"}` ohne `number`; Torwart `label: "TW"`.
  - **IDs**: Die Bereiche 1–99 und ≥ 1001 überschneiden sich nicht.
  - **Keine Bilddaten**: Kein Feld enthält Bilddaten (FR-009).

### Implementation für User Story 3

- [ ] T025 [US3] `tools/own_scene.py`: `player_entity(key, keeper, name_index) -> dict` nach
  [contracts/viewer-entities.md](contracts/viewer-entities.md). In `tools/veo_scene.py` (Stelle mit
  `"label": "TW" if key in keepers else f"S{…}"`) diese Funktion verwenden. Prüfen, dass der Rückweg
  `key = (e["team"], int(e["id"].rsplit("-", 1)[1]))` für beide ID-Arten stimmt.
- [ ] T026 [US3] `web/main.js`:
  - **Auswahl**: Spieler ohne `number` zeigen `${team} ? (${label})`, mit Nummer `${team} ${number}`.
  - **Schild**: `numberSprite` bekommt bei fehlender Nummer `?`.
  - **Trikot**: bleibt wie bisher, `create(kit, e.label ? null : e.number, …)`; ohne Nummer also keine Zahl
    auf dem Rücken.
  - **Cache-Version**: In `web/index.html` und den Importen von `?v=12` auf `?v=13` erhöhen.
  - Nur diese wenigen Zeilen, kein Umbau von `main.js`.
- [ ] T027 [US3] Szene 705 und 722 neu auswerten, dann `tools/veo_looks.py` erneut laufen lassen, damit die
  IDs passen.
  - Im Viewer prüfen: einen Spieler mit Nummer, einen ohne, und einem Spieler über die Szene folgen.
  - Ein Bildschirmfoto nur in den Scratchpad, nicht ins Repo.
  - Commit `feat(viewer): show read jersey numbers and mark unknown players`.

**Checkpoint**: Nummern für Trainer sichtbar.

---

## Phase 6: User Story 4 – Trefferquote nachmessen (P4)

**Goal**: Richtig, falsch und unbekannt je Mannschaft, Identitäten je Spieler, doppelte Bilder und Lesezeit
messen, ohne das Ergebnis zu beeinflussen.

**Independent Test**: `tools/jersey_eval.py` für Szene 705 gibt den Bericht aus. `meta.json` hat vorher
und nachher dieselbe Prüfsumme.

### Tests für User Story 4

- [ ] T028 [P] [US4] `tests/test_jersey_eval.py` mit kleinen künstlichen Spuren und Referenzen:
  - Zählung von `correct`, `wrong`, `unknown` je Mannschaft.
  - `visible` zählt nur Referenzspieler mit gut sichtbarem Rücken.
  - `identitiesPerPlayer` zählt eigene Spieler ab 1 s Zuordnung.
  - `duplicateFrames` erkennt eine doppelte Nummer.
  - Schreibversuch des Berichts außerhalb von `data/work/` endet mit Abbruch.

### Implementation für User Story 4

- [ ] T029 [US4] `tools/track_players.py`: Die Zuordnung aus `compare_veo` wird zu
  `match_reference(positions_by_track, truth) -> dict[str, list[tuple[key, int]]]` (Spur → Referenz je
  Bild).
  - Sie gibt zurück statt zu drucken. `compare_veo` nutzt sie und druckt wie bisher; die Ausgabe bleibt
    gleich.
  - Testfall in `tests/test_jersey_eval.py` oder einer eigenen `tests/test_track_players.py`.
- [ ] T030 [US4] `tools/jersey_eval.py` nach [contracts/cli.md](contracts/cli.md) und
  [contracts/eval-report.md](contracts/eval-report.md).
  - **Eingaben**: `meta.json` und `tracks.bin` der fertigen Szene, den Zwischenspeicher `{det}.numbers.npz`
    für die Rückenhöhen und Veo über `veo_tracks` (nur hier importiert).
  - **Rechnen**: über `match_reference` zuordnen und zählen.
  - **Ausgabe**: Konsole, optional `--bericht` nur unter `data/work/`. Es wird nie in den Szenenordner
    geschrieben.
  - **Lesezeit**: `readSeconds` aus einer Log-Zeile von `veo_scene` oder als Angabe `--lesezeit`.
- [ ] T031 [US4] Messen für Szene 705 und 722. Die Prüfsumme von `meta.json` muss vor und nach der Messung
  gleich sein (FR-008). Commit `feat(numbers): measure jersey number accuracy against a reference`.

**Checkpoint**: Alle Stories umgesetzt und messbar.

---

## Phase 7: Polish & Cross-Cutting

**Purpose**: Ziele erreichen, dokumentieren, Verfassung einhalten

- [ ] T032 Schwellen aus [research.md](research.md) R4 nur an Szene 705 einstellen und an Szene 722 prüfen.
  - Ziele: SC-001 ≥ 80 % richtig, SC-002 ≤ 5 % falsch, SC-003 ≤ 1,3 Identitäten, SC-004 0 doppelte Bilder,
    SC-005 ≤ 5 min mehr.
  - Bei Lücken die Rückfallebenen aus R9 in Reihenfolge nehmen; jede Stufe mit Messwerten im Commit-Text.
  - Verfehlte Ziele offen nennen.
- [ ] T033 [P] `docs/adr/0001-rueckennummern-ohne-fremddaten.md` schreiben, mit Kontext, Entscheidung,
  Folgen und verworfenen Alternativen:
  - eigener Erkenner, nur synthetisch und mit Bildern aus den eigenen Videos trainiert;
  - Veo nur als Referenz in getrenntem Werkzeug;
  - alles lokal;
  - keine Namen.

  Commit `docs(adr): record jersey numbers without third-party data`.
- [ ] T034 [P] `README.md` ergänzen:
  - Schritte Training, Lesen, `--kader` und Messen mit `$W`-Variablen wie die vorhandenen Beispiele;
  - Messergebnisse beider Szenen;
  - Grenzen (kleine Rücken, Vorderansichten, Abhängigkeit von unreinen Spuren);
  - Hinweis, dass Modell und Lesungen lokal bleiben.

  Den Satz „Spieler ohne Rückennummer“ in Aufrufzeile und Docstring von `tools/veo_scene.py` anpassen.
- [ ] T035 Prüfen, ob eingecheckte Dateien Bilder enthalten: `git diff --stat main...` und `git ls-files`
  dürfen keine neuen Bilddateien zeigen. Außerdem auf absolute Pfade prüfen:
  `git grep -nE "/home/|~/" -- . ':!specs'` darf nichts finden.
- [ ] T036 Zeilenzahlen prüfen (`wc -l tools/*.py web/*.js`): Neue Module bleiben unter 400 Zeilen,
  `veo_scene.py` ist kleiner als vorher. Weicht etwas ab, Complexity Tracking in [plan.md](plan.md)
  nachführen.
- [ ] T037 [quickstart.md](quickstart.md) vollständig durchgehen (Schritte 0–6). Alle Unit-Tests müssen
  grün sein. Ergebnisse für den späteren PR-Text sammeln.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001–T002)**: sofort.
- **Foundational (T003–T006)**: nach Setup; blockiert alle Stories, weil alle in `own_scene.py` einhängen.
- **US1 (T007–T018)**: nach Phase 2.
- **US2 (T019–T023)**: braucht die Spurnummern aus US1 (T014, T016).
- **US3 (T024–T027)**: Der Viewer-Teil (T026) geht schon nach Phase 2. Mit echten Nummern zeigen lässt er
  sich erst nach US1; sinnvoll ist er nach US2.
- **US4 (T028–T031)**:
  - T028, T029 und das Werkzeug T030 gehen nach Phase 2.
  - Die Messung T031 braucht ausgewertete Szenen mit Nummern (US1, besser US2).
- **Polish (T032–T037)**: nach allen Stories; T032 braucht US4.

### Within Each Story

Tests zuerst schreiben und fehlschlagen sehen, dann umsetzen. Reine Logik vor Einbindung, Einbindung vor dem
Lauf an echten Szenen. Ein Commit je Story-Abschluss (siehe Aufgaben).

### Parallel Opportunities

- T005 parallel zu T004, da eigene Datei, sobald die Funktionsnamen feststehen.
- US1:
  - T007, T008 und T009 parallel, alles Testdateien.
  - T010 parallel zu T014 und T015, weil `jersey_synth.py` und `jersey_identity.py` getrennte Dateien sind.
- T026 (Viewer) parallel zu US1/US2, eigene Datei.
- T028 und T029 parallel zu US2.
- T033 und T034 parallel.

---

## Parallel Example: User Story 1

```text
Task: "T007 tests/test_jersey_synth.py"
Task: "T008 tests/test_jersey_reader.py"
Task: "T009 tests/test_jersey_identity.py (Abstimmung, Kader)"
Task: "T010 tools/jersey_synth.py"
Task: "T014 + T015 tools/jersey_identity.py (vote, load_squad)"
# danach nacheinander: T011 → T012 → T013 (eine Datei) → T016 → T017 → T018
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 und 2 (Umbau ohne Verhaltensänderung, belegt durch gleiche Prüfsumme).
2. US1: Erkenner trainieren, Nummern je Spur lesen, abstimmen.
3. **STOP**: Stichproben am Video. Ist die Lesequalität offensichtlich zu schwach, zuerst R9 Stufe 1
   (Selbsttraining) vor US2.

### Incremental Delivery

US1 (Nummern) → US2 (Identität) → US3 (Viewer) → US4 (Messung) → Feinabstimmung mit Messwerten. Nach jeder
Story ein Commit; der PR geht nach main, sobald ein Remote existiert.

---

## Notes

- [P] = andere Datei, keine offene Abhängigkeit.
- Prüfausschnitte und Berichte nur unter `data/work/`. Bildschirmfotos nur im Scratchpad.
- Veo-Code (`veo_tracks`) wird ausschließlich in `tools/jersey_eval.py` und dem vorhandenen
  `track_players.compare_veo` importiert.
