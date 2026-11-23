---
description: "Aufgabenliste: Eine Identität je Spieler über die ganze Szene"
---

# Tasks: Eine Identität je Spieler über die ganze Szene

**Input**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Die Verfassung verlangt Tests mit jeder Verhaltensänderung, in eigenen Dateien. Werkzeug ist
`unittest`, Aufruf `.venv/bin/python -m unittest discover -s tests`.

**Regeln für alle Aufgaben**: Es gelten dieselben Regeln wie in `specs/001-rueckennummern/tasks.md`:
- Worktree `../matchspace.worktrees/002-spieler-identitaet`;
- Conventional Commits ohne Agentenhinweise;
- keine absoluten Pfade;
- keine Bilder in eingecheckten Dateien oder unter `web/data/`;
- Veo nur in `tools/jersey_eval.py` und `track_players.compare_veo`.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Im Worktree die Verknüpfungen prüfen (`data`, `models`, `.venv`, `web/data`, `web/models`).
  Außerdem prüfen, dass DINOv2-small unter `models/hf` liegt (`HF_HOME` relativ zum Repo, siehe T004);
  `.venv/bin/python -m unittest discover -s tests` muss grün sein.

---

## Phase 2: Foundational (blockiert alle Stories)

**Purpose**: Messung erweitern, Stand vor dem Feature festhalten, Merkmale je Erkennung bereitstellen.

- [X] T002 [P] `tests/test_jersey_eval.py` erweitern, beide Funktionen mit künstlichen Zuordnungen:
  - `wrong_time_share(matched)`: Ein Spieler mit 80 Bildern Hauptperson und 20 Bildern anderer Person
    ergibt 0,2.
  - `switches(matched, fps)`: Wechsel unter 1 s zählen nicht.
- [X] T003 `tools/jersey_eval.py`: Funktionen `wrong_time_share` und `switches` und Felder
  `wrongTimeShare` und `switches` im Bericht, nach [contracts/eval-report.md](contracts/eval-report.md).
  - Danach den Stand vor dem Feature für 705 und 722 messen und den Bericht unter
    `data/work/…/scene_S.identity-before.json` ablegen.
  - Erwartet: falsche Zeit rund 6,5 % und 5,7 %, Identitäten 2,24 und 2,17.
  - Commit `feat(numbers): report wrong-person time and identity switches`.
- [X] T004 [P] `tests/test_appearance.py`:
  - **Ausgabe**: `describe(crops)` liefert Vektoren der Länge 1, Form (n, 768). Dafür wird das Modell
    durch ein kleines Ersatznetz per `unittest.mock` ersetzt, ohne Download.
  - **Zwischenspeicher**: `load_or_compute` liest einen passenden Stempel, rechnet bei einem veralteten
    neu und schreibt keine Bilddaten (nur `frame`, `lens`, `box`, `embedding`, `height`, `stamp`).
- [X] T005 `tools/appearance.py` nach [contracts/appearance-cache.md](contracts/appearance-cache.md) und
  [data-model.md](data-model.md):
  - **Modell**: `MODEL_ID = "facebook/dinov2-small"`, `HF_HOME` relativ zum Repo (`models/hf`).
  - **Merkmale**: `describe(crops)` ergibt Pooler-Ausgabe und Mittel der Bildteile, normiert.
  - **Szene**: `read_scene(video, det_path)` arbeitet alle Erkennungen auf dem Platz in jedem 2. Bild
    ab, mit Box-Ausschnitt 112×224. Die Größe (Schulter bis Knöchel) kommt aus
    `{det}.keypoints.npz`. Ergebnis ist `{det}.appearance.npz`, das Video wird einmal gelesen.
  - **Ohne Modell oder GPU-Fehler**: Hinweis und `None`; der Aufrufer arbeitet dann ohne Aussehen.
  - **Gerüst**: Bildzugriff wie `jersey_reader.read_scene`.
  - Commit `feat(identity): describe player appearance per detection`.

**Checkpoint**: Messung mit falscher Zeit steht, Merkmale sind je Szene im Zwischenspeicher.

---

## Phase 3: User Story 1 – Einem Spieler über die ganze Szene folgen (P1) 🎯 MVP

**Goal**: Stücke mit Lücke werden verbunden, wenn genau ein Kandidat klar passt (Weg, Nummer, Größe,
Aussehen).

**Independent Test**: `jersey_eval.py` für 705 und 722. Die Identitäten je Spieler sinken, die falsche
Zeit steigt nicht über den Stand aus T003.

### Tests für User Story 1

- [X] T006 [P] [US1] `tests/test_identity_link.py` (Verbinden), mit künstlichen Stücken als
  `{Bild: (x, y)}` plus Merkmalen:
  - **Ein Kandidat**: Eine Lücke von 2 s und 4 m mit einem einzigen erreichbaren Kandidaten wird
    verbunden.
  - **Nicht erreichbar**: 40 m in 1 s werden nicht verbunden (Szenario P1/2).
  - **Gleichzeitig**: Länger als 0,5 s gleichzeitig zu sehen wird nie verbunden (Szenario P1/3).
  - **Zwei ähnliche Kandidaten**: Abstand zum Zweitbesten unter dem Verhältnis 2 bedeutet getrennt
    (Szenario P2/1).
  - **Verbote**: Verschiedene sichere Nummern verbieten (P2/2), ebenso andere Mannschaft (P2/3),
    Torwart mit Feldspieler und zwei Schiedsrichter miteinander.
  - **Nummern**: Dieselbe sichere Nummer verbindet auch bei langer Lücke, sofern erreichbar.

### Implementation für User Story 1

- [X] T007 [US1] `tools/identity_link.py`, Teil Verbinden (reine Logik):
  - **Datentypen**: `Piece`, `Look` und `Link` als `dataclass` nach [data-model.md](data-model.md).
  - **Kosten**: `link_cost(a, b, fps)` für das Ende von a und den Anfang von b. Aus der Laufrichtung der
    letzten 0,5 s wird die erwartete Lage am Anfang von b berechnet. Ihre Unsicherheit ist 1,5 m plus
    2 m/s × Lücke, gedeckelt bei 8 m/s × Lücke. Kosten = Abstand ÷ Unsicherheit, dazu Aussehen
    (1 − Kosinus, Gewicht `LOOK_WEIGHT`) und Größe (relativer Unterschied, Gewicht `HEIGHT_WEIGHT`).
    Dieselbe sichere Nummer zieht `NUMBER_BONUS` ab. Verbote ergeben `inf`.
  - **Verbinden**: `link(pieces, looks, numbers, fps) -> list[list[str]]`, gierig nach Kosten, nur mit
    `margin ≥ MIN_MARGIN` (2) in beide Richtungen (bestes Ende für einen Anfang und umgekehrt).
  - **Kommentar**: `ponytail:` mit Ceiling (gierig statt Netzfluss).
- [X] T008 [US1] `tools/own_scene.py`:
  - **Ablauf**: In `with_numbers` vor der Nummernvergabe Merkmale laden (`appearance.read_scene`), die
    Spuren zu Stücken machen, `identity_link.link` aufrufen und Spieler aus verbundenen Stücken bilden.
    Die Rückgabeform bleibt gleich (Bilder der Stücke vereinigt unter einem Schlüssel).
  - **Ohne Merkmale**: Verbunden wird nur mit Weg und Nummer.
  - **Konsole**: nennt die Zahl der Verbindungen.
- [X] T009 [US1] `tools/identity_link.py`, CLI nach [contracts/cli.md](contracts/cli.md): Kontakte,
  Trennungen (ab US2) und Verbindungen mit Kosten und Abstand zum Zweitbesten ausgeben; zum Prüfen.
- [X] T010 [US1] Szene 705 auswerten und messen. Die Gewichte (`LOOK_WEIGHT`, `HEIGHT_WEIGHT`,
  `NUMBER_BONUS`, `MIN_MARGIN`) an 705 einstellen, dann 722 prüfen. Commit
  `feat(identity): link track pieces of the same player` mit Messwerten.

**Checkpoint**: Lücken werden vorsichtig überbrückt.

---

## Phase 4: User Story 2 – Lieber getrennt als vertauscht (P2)

**Goal**: Spurwechsel an Kontaktstellen erkennen und trennen (FR-011), danach neu verbinden.

**Independent Test**: `wrongTimeShare` und `switches` im Bericht sinken gegenüber T003.

### Messpunkt (vor dem Einbau)

- [X] T011 [US2] Entscheidung zur Wechselprüfung, mit `tools/identity_link.py` und Veo nur als Referenz:
  - **Kandidaten**: alle Kontaktstellen (unter 1,5 m, gleiche Mannschaft) in 705 und 722.
  - **Belege je Kontakt**:
    - Bewegung: Verlängerung der Laufrichtung, gerade gegen vertauscht;
    - Nummer: Abstimmung vorher gegen nachher;
    - Aussehen: Merkmale je 1 s vorher und nachher, gegen das Gegenüber in derselben Zeit.
  - **Auswertung**: gegen die bekannten Wechsel aus T003.
  - **Kriterium**: mindestens 5 von 7 Wechseln erkannt, höchstens 1 falsche Trennung je Szene.
  - **Ergebnis**: Welche Belege das Kriterium erfüllen, kommt in [research.md](research.md) R3. Trägt das
    Aussehen nicht, bleibt es nur für das Verbinden, oder `appearance.py` wird ganz entfernt, falls es dort
    auch nichts bringt.

### Tests für User Story 2

- [X] T012 [P] [US2] `tests/test_identity_link.py` erweitern (Trennen):
  - **Kontakte**: `contacts(pieces, fps)` findet Annäherungen unter 1,5 m derselben Mannschaft, nicht
    über Mannschaften hinweg.
  - **Tausch**: Zwei Spuren tauschen an einem Kontakt ihre Wege (gerade Linien, die sich kreuzen und
    vertauscht weiterlaufen). Beide werden getrennt und über Kreuz neu verbunden (Grenzfall „Spurwechsel
    in beide Richtungen“).
  - **Vorbeilaufen**: Zwei Spuren laufen ohne Tausch dicht vorbei, nichts wird getrennt (Grenzfall
    „Kurzer Kontakt ohne Wechsel“).
  - **Nummer**: Ein Wechsel mit Nummernbeleg (vorher sicher 7, nachher sicher 9) wird getrennt.

### Implementation für User Story 2

- [X] T013 [US2] `tools/identity_link.py`, Teil Trennen:
  - **Kontakte**: `contacts(pieces, fps)`.
  - **Prüfung**: `swap_evidence(contact, pieces, looks, readings)` mit den Belegen, die in T011 das
    Kriterium erfüllt haben.
  - **Trennen**: `split(pieces, contacts) -> pieces` erzeugt Stücke `{Spur}/{k}`.
  - **Lesungen**: Die Rückenlesungen werden mit den Stücken getrennt.
- [X] T014 [US2] `tools/own_scene.py`: Ablauf Trennen → Verbinden → Nummern. Die Konsole nennt Kontakte,
  Trennungen und Verbindungen.
- [X] T015 [US2] Szene 705 und 722 auswerten und messen (`wrongTimeShare`, `switches`, Identitäten).
  Schwellen der Wechselprüfung an 705, Prüfung an 722. Commit
  `feat(identity): split tracks at identity switches` mit Messwerten.

**Checkpoint**: weniger falsche Zeit, kein Rückschritt bei den Identitäten.

---

## Phase 5: User Story 3 – Mehr Spieler mit Nummer (P3)

**Goal**: Nummern werden je Spieler über alle Stücke abgestimmt.

**Independent Test**: Die richtigen Nummern je Szene sind mindestens 7, die falschen höchstens 5 %.

- [ ] T016 [P] [US3] `tests/test_jersey_identity.py` erweitern: Ein Spieler aus drei Stücken mit je zwei
  Fenstern derselben Nummer bekommt die Nummer, jedes Stück allein nicht (Szenario P3/1).
- [ ] T017 [US3] `tools/own_scene.py` und `tools/jersey_identity.py`: Die Lesungen eines Spielers werden
  unter einem Namen zusammengefasst, dann laufen `vote`, `assign` und `merge_by_number` auf
  Spielerebene. Kein neuer Abstimmungscode: Die Zuordnung Lesung → Spieler geschieht über
  `readings_for_tracks` mit dem Spielernamen.
- [ ] T018 [US3] Szenen auswerten, `veo_looks.py` laufen lassen und messen. Danach die Stichproben im
  Viewer: 10 frühere Bruchstellen je Szene (SC-004), Bildschirmfotos nur im Scratchpad. Commit
  `feat(identity): vote jersey numbers over all pieces of a player`.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T019 [P] `docs/adr/0002-identitaet-ohne-fremddaten.md` schreiben:
  - Weg und Nummer vor Aussehen;
  - Bildmerkmale nur lokal und je Szene;
  - Messwerte aus R1 und T011;
  - Ausblick auf mehrere Kameras (Kreuzpeilung, höhere Auflösung).
- [ ] T020 [P] `README.md`: Abschnitt „Identität ohne Veo“ mit Ablauf, CLI, Messwerten und Grenzen;
  dazu der Lizenzhinweis zu Ultralytics YOLO (AGPL-3.0) bei den Werkzeugen.
- [ ] T021 Prüfungen:
  - Unit-Tests grün;
  - `git ls-files` ohne neue Bilddateien;
  - `git grep -nE "/home/|~/" -- . ':!specs'` leer;
  - neue Module unter 400 Zeilen.
- [ ] T022 [quickstart.md](quickstart.md) durchgehen. Messwerte und verfehlte Ziele in
  [research.md](research.md) und am Ende dieser Datei festhalten. Commit `docs: record identity results`.

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2** (T003 braucht T002; T005 braucht T004).
- **US1 (T006–T010)**: nach Phase 2.
- **US2**:
  - T011 nach T005 und T009 (CLI zum Auswerten);
  - T012–T015 nach T011, weil der Messpunkt entscheidet, welche Belege eingebaut werden.
- **US3 (T016–T018)**: nach US1. Sinnvoll nach US2, weil getrennte Stücke ihre eigenen Lesungen haben.
- **Polish**: nach allen Stories.

### Parallel Opportunities

- T002 ∥ T004 (verschiedene Testdateien);
- T006 ∥ T005;
- T012 ∥ T011-Auswertung;
- T016 ∥ T013;
- T019 ∥ T020.

## Implementation Strategy

- **MVP**: Phase 2 und US1. Lücken werden vorsichtig verbunden; die Messung zeigt, wie viel das allein
  bringt.
- **Danach US2**: der Messpunkt T011 zuerst. Fällt er negativ aus, wird nur mit Nummernbeleg getrennt,
  und SC-002 wird offen als verfehlt berichtet.
- **Danach US3**: Nummern je Spieler, dann Viewer-Stichproben.
