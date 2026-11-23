---
description: "Aufgabenliste: Eigene Referenz statt Veo"
---

# Tasks: Eigene Referenz statt Veo

**Input**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Die Verfassung verlangt Tests mit jeder Verhaltensänderung, in eigenen Dateien. Werkzeug ist
`unittest`, Aufruf `.venv/bin/python -m unittest discover -s tests`.

**Regeln für alle Aufgaben**:
- Worktree `../matchspace.worktrees/003-eigene-referenz`;
- Conventional Commits ohne Agentenhinweise;
- keine absoluten Pfade;
- keine Bilder in eingecheckten Dateien oder unter `web/data/`;
- Veo nur mit `--veo` und im Vergleichslauf;
- Bildschirmfotos und Bildausschnitte nur im Scratchpad.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Im Worktree die Verknüpfungen prüfen (`data`, `models`, `.venv`, `.specify`, `web/data`, `web/models`);
  `.venv/bin/python -m unittest discover -s tests` muss grün sein.

---

## Phase 2: Foundational (blockiert US1 und US2)

**Purpose**: Die Zuordnung der Auswertung (welche Erkennung gehört zu welchem Spieler) liegt als Datei vor.

- [X] T002 [P] `tests/test_own_scene.py` erweitern, `write_identity(path, players, events, numbers, fps)`:
  - **Form**: Die geschriebene Datei hat die Felder aus [data-model.md](data-model.md) „Zuordnung der Auswertung“
    (`fps`, `players` mit `team`, `keeper`, `number`, `detections` als [[Bild, Linse, Box]] zeitlich geordnet,
    `events`, `numbers`, `stamp`).
  - **Stempel**: Der Stempel ändert sich, wenn sich eine Erkennung eines Spielers ändert, sonst nicht.
  - **Inhalt**: keine Bilddaten, keine Bodenlagen.
- [X] T003 `tools/own_scene.py`:
  - `split_and_link` gibt Trennungen und Verbindungen als Ereignisse zurück (`{kind, frame, players, reason}`).
  - `with_numbers` schreibt `{det}.identity.json`; Spielernamen wie im Viewer (`own-7`, `opponent-1003`).
  - **Prüfung**: Beide Szenen neu auswerten. `tracks.bin` hat dieselbe Prüfsumme wie vorher, es ändert sich kein
    Verhalten.
  - Commit `refactor(identity): write the player assignment of a scene`.

**Checkpoint**: Für 705 und 722 liegt `{det}.identity.json` vor.

---

## Phase 3: User Story 1 – Strittige Stellen selbst entscheiden (P1) 🎯 MVP

**Goal**: Das Werkzeug findet die strittigen Stellen und die Kontrollstellen. Der Nutzer entscheidet sie mit
wenigen Tasten, und die Antworten bleiben gespeichert.

**Independent Test**: Für 705 alle Stellen entscheiden und die Zeit stoppen. Jede Stelle hat eine Antwort, und die
Referenzdatei enthält keine Bilder und keine Namen.

### Tests für User Story 1

- [X] T004 [P] [US1] `tests/test_reference.py` (reine Logik), mit künstlichen Spielern aus Erkennungen:
  - **Abschnitte**: Eine Stelle schneidet die Beteiligten in vorher und nachher.
  - **Antworten**:
    - „wie vorgeschlagen“: jeder bleibt seine Person;
    - „vertauscht“: über Kreuz;
    - „andere Person“: neue Person;
    - „unklar“: Abschnitte nach der Stelle zählen nicht, bis eine spätere Antwort sie anbindet;
    - Spurbeginn: einer endenden Spur zugeordnet ergibt dieselbe Person.
  - **Personen**: Union-Find über mehrere Stellen; Abschnitte ohne Antwort bleiben eigene Personen.
  - **Nummern**: Eine vom Nutzer angegebene Nummer gilt für die ganze Person.
  - **Wiederfinden**: Nach neuer Auswertung mit anderen Spielernamen wird eine Antwort über ihre Anker (gleiches
    Bild, Boxüberlappung > 50 %) wiedergefunden. Ohne passende Box ist sie verwaist.
  - **Widersprüche (FR-015)**: dieselbe Person zur selben Zeit an zwei Orten, dieselbe Nummer bei zwei Personen
    einer Mannschaft, eine Person in zwei Mannschaften.
  - **Wiederholung**: Antworten mit `repeat` zählen nicht für die Referenz.
- [X] T005 [P] [US1] `tests/test_review_spots.py`, mit künstlichen Zuordnungen:
  - **Verdeckung**: Boxen derselben Linse überlappen um mehr als 30 % der kleineren Box, dann gibt es eine Stelle.
    Bei 20 % oder in verschiedenen Linsen nicht.
  - **Spurende**: ein Ende mehr als 1 m innerhalb der Linien gibt eine Stelle. Am Rand des Platzes und am Anfang
    oder Ende der Szene nicht.
  - **Zusammenfassen**: Stellen mit gemeinsamen Spielern unter 1 s Abstand werden eine.
  - **Ereignisse**: Trennung, Verbindung, „Nummer prüfen“ (einmal je Spieler mit Nummer, an der besten
    Rückenlesung) und „Nummer unsicher“ (Sicherheit 0,5–0,9 aus mindestens 2 Fenstern).
  - **Kontrollstellen**: 5 je Szene, nur in Abschnitten ohne Grund, mit festem Startwert wiederholbar.
  - **Reihenfolge**: nach `priority` absteigend.
  - **Ergänzen**: Ein zweiter Lauf behält vorhandene Antworten, ordnet sie den neuen Stellen zu und meldet verwaiste.
  - **Ausschnitt**: `from`/`to` liegen 1,5 s vor und nach der Stelle; `crop` umfasst alle Beteiligten.

### Implementation für User Story 1

- [X] T006 [US1] `tools/reference.py` (reine Logik) nach [data-model.md](data-model.md):
  - `Spot`, `Answer` und `Person` als `dataclass`;
  - `segments(identity, spots)`, `persons(identity, spots, answers)`;
  - `refind(answers, identity)`, `conflicts(...)`.
- [X] T007 [US1] `tools/review_spots.py` nach [contracts/cli.md](contracts/cli.md):
  - `find_spots(identity, det, cam, readings, fps)` mit den Gründen aus [research.md](research.md) R1, dazu
    `control_spots(..., seed, n=5)`;
  - **CLI**: schreibt oder ergänzt `{det}.reference.json` atomar und gibt die Zahl der Stellen je Grund und offen
    aus.
  - `--veo`: zusätzlich Stellen „Veo sieht anders“. Ohne die Angabe wird nichts von Veo importiert.
- [X] T008 [US1] Stellen für 705 und 722 erzeugen und zählen (Erwartung 30–50 je Szene).
  - Liegen es deutlich mehr: Schwellen der Verdeckung in [research.md](research.md) R1 nachstellen und
    begründen.
  - Commit `feat(reference): find contested spots for manual review`.

### Tests und Umsetzung Markierwerkzeug

- [X] T009 [P] [US1] `tests/test_review_server.py`, Server in einem Thread auf freiem Port:
  - **Video**: `GET /video` mit `Range: bytes=0-99` ergibt 206 mit 100 Bytes.
  - **Stellen**: `GET /spots` liefert Stellen und Antworten.
  - **Antwort**: `POST /answer` speichert, und die Datei ist danach gültiges JSON.
  - **Fehler**: Eine fehlerhafte Antwort ergibt 400; ein Pfad wie `/../data` ergibt 404.
  - **Erreichbarkeit**: Der Server lauscht nur an `127.0.0.1`.
- [X] T010 [US1] `tools/review_server.py` nach [contracts/review-api.md](contracts/review-api.md) (nur
  Standardbibliothek; atomares Schreiben über temporäre Datei und Umbenennen).
- [X] T011 [US1] `web/review/index.html`, `review.js`, `review.css`:
  - **Anzeige**: Liste der Stellen mit Grund und Stand. Je Stelle spielt der Ausschnitt in Schleife; Linse
    ausgeschnitten und vergrößert, Boxen der Beteiligten mit Buchstaben, vorher und nachher.
  - **Tasten**:
    - `Enter`: wie vorgeschlagen;
    - `V`: vertauscht;
    - je Buchstabe zuordnen, `A` andere Person, `U` unklar;
    - Ziffern: Nummer;
    - `←`/`→` blättern, Leertaste Pause.
  - **Rückmeldung**: Warnungen aus der Antwort anzeigen; Fortschritt „offen n“; nach dem Neuladen weiter bei der
    nächsten offenen Stelle.
  - **Datenschutz**: keine externen Ressourcen (keine CDN, keine Schriften).
- [X] T012 [US1] Prüfen von Hand:
  - Server für 705 starten und mit Chromium headless ein Bildschirmfoto einer Stelle machen (nur Scratchpad).
  - Ansehen: Boxen sitzen auf den Spielern, Buchstaben sind lesbar.
  - Commit `feat(reference): local review tool for contested spots`.
- [ ] T013 [US1] **Nutzerschritt** (Anleitung an den Nutzer, Umsetzung wartet darauf):
  - strittige Stellen von 705 und 722 entscheiden, Zeit stoppen;
  - je Szene 5 Stellen ein zweites Mal entscheiden (Wiederholung, SC-004).

  Ergebnis: Dauer, Anteil „unklar“, Übereinstimmung der Wiederholungen. Festhalten in [research.md](research.md).

**Checkpoint**: Für beide Szenen gibt es eine eigene Referenz.

---

## Phase 4: User Story 2 – Gegen die eigene Referenz messen (P2)

**Goal**: Alle Kennzahlen kommen aus der eigenen Referenz. Veo steht nur als zweite Spalte daneben.

**Independent Test**: Der Bericht für 705 ist ohne und mit `--veo` erzeugt. Unter `own` sind die Werte gleich,
nur der zweite Bericht hat `veo` mit einer Widerspruchsliste.

- [X] T014 [P] [US2] `tests/test_jersey_eval.py` erweitern (künstliche Zuordnung und Referenz):
  - **Kennzahlen**: Identitäten je Person, falsche Zeit, Wechsel und Nummern gegen Personen der Referenz;
    Abschnitte nach „unklar“ zählen nicht.
  - **Abdeckung**: Offene und verwaiste Stellen werden gezählt; die Schätzung aus den Kontrollstellen ist der
    Anteil mit Fehler.
  - **Veo-Spalte**: Abgleich über die rohen Bodenpunkte ohne Versatz; ein Widerspruch wird gelistet.
  - **Ohne Veo**: Fehlt `--veo`, wird `veo_tracks` nicht importiert (Test über `sys.modules`).
- [X] T015 [US2] `tools/jersey_eval.py` nach [contracts/eval-report.md](contracts/eval-report.md) und
  [contracts/cli.md](contracts/cli.md):
  - neue Aufrufform `DETEKTIONEN.json KAMERA.json [--veo …]`;
  - Messung je Erkennung;
  - `depth_offset` und `shift_depth` entfallen; die Tests aus Feature 002 dazu werden durch die neuen ersetzt.
- [ ] T016 [US2] 705 und 722 ohne und mit `--veo` messen.
  - Werte aus Feature 001 und 002 neu einordnen: falsche Zeit, Wechsel, Identitäten und Nummern laut eigener
    Referenz gegen laut Veo.
  - Festhalten in [research.md](research.md).
  - Commit `feat(numbers): measure against the own reference, Veo as second opinion`.

---

## Phase 5: User Story 3 – Lage am Boden ohne Veo prüfen (P3)

**Goal**: Es ist geklärt, welche Lagequelle in der Tiefe richtig liegt. Die fertige Szene wird korrigiert, falls
sie falsch liegt.

**Independent Test**: Der Bericht `lines` für beide Szenen hat mindestens 20 Linienstellen und Median und Streuung
je Quelle.

- [X] T017 [P] [US3] `tests/test_line_check.py` mit künstlicher Kamera (aus `veo_camera`, vereinfachte Linsen):
  - **Treffer**: Ein Fußgelenk, das auf die Projektion von `touch+` fällt, ist eine Linienstelle mit dem
    Linienpunkt als wahrer Lage.
  - **Fehler je Quelle**: Eine Lage 0,8 m weiter von der Kamera ergibt einen Tiefenfehler von +0,8 und quer 0.
  - **Ausschlüsse**: Ein Fuß, der sich über 3 Bilder um mehr als 2 Pixel bewegt, zählt nicht; ebenso ein
    Linienpunkt, der im Hintergrundbild nicht hell ist.
  - **Begrenzung**: höchstens 3 Stellen je Spieler und Sekunde.
- [X] T018 [US3] `tools/line_check.py` nach [contracts/cli.md](contracts/cli.md):
  - wiederverwendet werden `veo_camera.model_lines`, `project`, `to_ground` und `brightness`;
  - Quellen: Szene (`tracks.bin`), Boxunterkante, Fußpunkt aus Gelenkpunkten, Veo mit `--veo`.
- [X] T019 [US3] Beide Szenen prüfen und auswerten:
  - **Kontrollbild**: Ausschnitte einiger Linienstellen im Scratchpad ansehen.
  - **Entscheidung**: Trägt die Szene, Veo oder keiner den Versatz von 0,9 m?
  - **Festhalten** in [research.md](research.md).
  - Commit `feat(scene): check ground positions against pitch lines`.
- [X] T020 [US3] Entfällt: Die fertige Szene trägt den Fehler nicht (research.md R5, Ergebnis). Nur wenn die fertige Szene den Fehler trägt:
  - Ursache in `tools/veo_scene.py` beheben (vermutlich `feet_on_ground`) und mit einem Test in
    `tests/test_line_check.py` absichern.
  - Beide Szenen neu auswerten. Danach erneut `line_check.py`, `review_spots.py` (Antworten müssen wiedergefunden
    werden, FR-006) und `jersey_eval.py` laufen lassen.
  - Commit `fix(scene): place players at their feet in depth`.

---

## Phase 6: User Story 4 – Betrieb ganz ohne Veo (P4)

**Goal**: Eine Szene lässt sich ohne Veo-Dateien auswerten, mit derselben Lage und Uhr wie bisher.

**Independent Test**: Der Prüflauf unter `no_veo_check.py` läuft für beide Szenen durch. `tracks.bin` ist gleich,
und die Uhr stimmt.

- [X] T021 [P] [US4] `tests/test_own_match.py`:
  - **Spielordner**: Eine Spielbeschreibung ergibt `meta.json` mit Abschnitten samt `videoStartS`, Platzmaßen aus
    der Kamera, Mannschaften und ohne Bewegungsdaten.
  - **Ablehnung**: ungültige Farbe, absteigende Abschnitte, Personennamen in Feldern, die keine haben dürfen
    (nur `name`, `teams.*.name`).
  - **Uhr**: Die Uhr einer Szene ab Videosekunde 705 ist `clockStartS + (705 − videoStartS)`.
- [X] T022 [P] [US4] `tests/test_no_veo_check.py`:
  - Ein Kindprozess, der eine Datei in einem verbotenen Ordner öffnet, bricht mit Fehler ab.
  - Eine ausdrücklich freigegebene Datei darf gelesen werden.
  - Ausgabeordner mit `veo-` im Namen sind nicht betroffen.
- [ ] T023 [US4] `tools/own_match.py` nach [contracts/match-description.md](contracts/match-description.md).
  - Dazu `data/work/veo-2026-11-01/spiel.json` anlegen.
  - Die Anstoßzeiten bestätigt der Nutzer am Video; bis dahin als unbestätigt markieren.
- [X] T024 [US4] `tools/veo_scene.py`:
  - Im Betrieb ohne Veo nur Spielabschnitte, Uhr, Platz, Mannschaften und Quelle aus dem Spielordner lesen, keine
    Bewegungsdaten.
  - Den Abschnitt über den letzten Anstoß vor der Szene bestimmen.
- [X] T025 [US4] `tools/no_veo_check.py` nach [contracts/cli.md](contracts/cli.md) (`sys.addaudithook`,
  `--verbiete`, `--erlaube`, führt das Werkzeug mit `runpy` aus).
- [X] T026 [US4] `tools/veo_camera.py`:
  - **Start**: aus einem Gitter von Kameralagen (Höhe 4–15 m, 2–20 m hinter der Seitenlinie, entlang der Linie, Blick
    zur Mitte); die beste nach Handpunkt-Fehler.
  - **Ohne Veo**: `read_veo` nur noch für die Linsendaten; `-` statt Handpunkten bricht mit klarer Meldung ab.
  - **Prüfung**: Die neue Kamera liegt höchstens 0,1 m und 0,1° neben `camera.json`, bei gleichem Linienfehler.
  - Commit `feat(camera): calibrate without Veo start values`.
- [X] T027 [US4] Vergleichslauf:
  - Eigenen Spielordner anlegen (`own_match.py`, `veo_ground.py`, `veo_backdrop.py`).
  - Beide Szenen unter `no_veo_check.py --verbiete web/data/veo-2026-11-01` auswerten.
  - `tracks.bin` mit dem Lauf gegen das Veo-Basisspiel vergleichen (gleiche Prüfsumme); die Uhr in `meta.json`
    vergleichen.
  - Commit `feat(scene): run scenes from an own match description`.

---

## Phase 7: Polish & Cross-Cutting

- [X] T028 [P] `docs/adr/0003-eigene-referenz.md` schreiben:
  - Veo nur als zweite Meinung;
  - Wahrheit aus eigenen Antworten an strittigen Stellen, mit Kontrollstellen;
  - Lage aus der Platzgeometrie;
  - Linsendaten der Kamera bleiben Eingabe;
  - bewusster Tausch „nur strittige Stellen“.
- [X] T029 [P] `README.md`:
  - **Ablauf**: Markieren, Messen, Lageprüfung, Betrieb ohne Veo, `spiel.json`.
  - **Veraltete Angaben**: Messwerte „gegen Veo“ neu einordnen; Hinweis auf Veo-Startwerte und Uhr streichen.
- [X] T030 Prüfungen:
  - Unit-Tests grün;
  - `git ls-files` ohne neue Bilddateien;
  - `git grep -nE "/home/|~/" -- . ':!specs'` leer;
  - neue Module unter 400 Zeilen;
  - die Seite lädt nichts von außen (`grep -n "http" web/review/*`).
- [ ] T031 [quickstart.md](quickstart.md) durchgehen.
  - Messwerte und verfehlte Ziele in [research.md](research.md) und am Ende dieser Datei festhalten.
  - Commit `docs: record own reference results`.

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2**: T003 braucht T002.
- **US1**:
  - nach Phase 2;
  - T006 nach T004, T007 nach T005 und T006;
  - T010 nach T009, T011 nach T010;
  - T013 (Nutzer) nach T012.
- **US2**: nach US1 einschließlich T013, weil ohne Antworten nichts zu messen ist.
- **US3**: braucht nur Phase 1. Kann laufen, während der Nutzer markiert. T020 nur, wenn T019 einen Fehler der Szene
  zeigt.
- **US4**: braucht nur Phase 1. T027 nach T023–T026.
- **Polish**: nach allen Stories.

### Parallel Opportunities

- T004 ∥ T005 (verschiedene Testdateien);
- T009 ∥ T006/T007;
- US3 und US4 ∥ T013 (Nutzer markiert);
- T021 ∥ T022;
- T028 ∥ T029.

## Implementation Strategy

- **MVP**: Phase 2 und US1. Danach könnt ihr markieren.
- **Während des Markierens**: US3 (Lage) und US4 (ohne Veo), beide unabhängig von euren Antworten.
- **Danach US2**: messen gegen die eigene Referenz. Wenn US3 eine Korrektur der Szene ergeben hat, wird mit der
  korrigierten Szene gemessen; die Antworten bleiben über ihre Anker gültig.
