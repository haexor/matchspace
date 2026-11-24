# Aufgaben: Beste Szenen vor der Kamera

Plan: [plan.md](plan.md), Spec: [spec.md](spec.md). Format: `- [ ] Tnnn [P] [USn] Beschreibung mit Pfad`. `[P]` = parallel möglich.

## Phase 1: Grundlage

- [x] T001 Worktree `../matchspace.worktrees/005-beste-szenen`, Branch, Spec, Plan.
- [x] T002 Spielliste und Adresse des Panoramas vom 2026-11-01 über den lesenden Zugang holen (nichts davon im Repository).
- [x] T003 Nahzone und Pixelgrößen aus dem Kameramodell berechnen (Plan, Tabelle).
- [x] T004 Vorauswahl aus dem Basisspiel (grobe Skizze) und sieben Abschnitte à 45 s unter `data/raw/veo/2026-11-01/scenes/` holen.
- [ ] T005 Graphify-Abfrage zu Ballspur, Referenz und Review (Wiederverwendung prüfen), Ergebnis in `research.md` notieren.

## Phase 2: US1 – Szenenfinder (P1)

- [x] T006 [US1] `tests/test_scene_finder.py`: Fensterbildung, Zusammenlegen überlappender Fenster, Nahzonenmaß, Punkte steigen mit Nähe und Ballanteil.
- [x] T007 [US1] `tools/scene_finder.py`: Vorauswahl aus dem Basisspiel (Ball in Nahzone, Spieler am Ball, Tempowechsel) in Fenstern; Zusammenlegen.
- [x] T008 [US1] `tools/scene_finder.py`: eigene Bewertung je Abschnitt aus Personenerkennung und eigener Ballspur (Ballanteil, Spielerhöhe des Ballführers, Ballgröße, Beteiligte, Naht).
- [x] T009 [US1] Die sieben Abschnitte auswerten (`veo_detect.py`, `veo_ball.py`), Rangliste `ranking.json` mit Standbildern, Zahlen gegen SC-001 prüfen.
- [x] T035 [US1] Ballsuche verbessert: ruhender Ball (`rest_fill`) und lokale Nachsuche in Ausschnitten (`tools/ball_gapfill.py`), Herkunft je Bild in `source`; Tests `tests/test_ball_gapfill.py`, `tests/test_veo_ball.py`. Messung mit versteckten Bildern: 91 % wiedergefunden, Median-Fehler 0,3 px. Fehltreffer (orangene Markierung, Hand) fallen über den Weißanteil (`tools/ball_look.py`) und feste Stellen heraus.
- [ ] T010 [US1] Ergebnis dem Nutzer zeigen (Standbilder, Zahlen), drei bis fünf Szenen gemeinsam auswählen.
- [ ] T011 [US1] README: Abschnitt „Beste Szenen finden“ mit Aufrufen (ohne Zugangsdaten).

## Phase 3: US2 – Referenz für Ballkontakte (P2)

Entscheidung des Nutzers (2026-11-24): Der Nutzer markiert einmalig für die gewählten Szenen (und später höchstens zum
Nachtrainieren oder bei neuer Kamera), nicht vor jedem Spiel. Damit es wenig Arbeit ist, zeigt der Ballmodus die
automatisch erkannten Kontakte als Vorschläge zum Bestätigen oder Verwerfen und zum Korrigieren der Zeit.

- [ ] T012 [US2] `tests/test_ball_reference.py`: Speichern, Laden, Wiederfinden nach neuer Auswertung, keine Namen und Bilder in der Datei.
- [ ] T013 [US2] `tools/ball_reference.py`: Format und Wiederfinden (Spieleranker wie in `reference.py`).
- [x] T014 [US2] Vorschläge für Kontakte aus der Ballspur (Knicke, Tempowechsel) in `tools/ball_events.py` (Grundstufe, wird in Phase 4 verfeinert); wird vor dem Ballmodus gebaut.
- [ ] T015 [US2] Ballmodus im Review-Werkzeug: `web/review/ball.js`, Ergänzungen in `index.html`, `review.css`, `tools/review_server.py`. Vorschläge bestätigen/verwerfen, Zeit korrigieren, Kontakt neu setzen, Körperteil, Pass, Schuss, Verlust, Gewinn, „Ball nicht erkennbar“.
- [ ] T016 [US2] Gemeinsam mit dem Nutzer die gewählten Szenen markieren; Zeit stoppen (SC-002: höchstens rund 10 Minuten je Szene). Dazu die Plausibilitätsprüfung ohne Referenz (Tempoänderung nur an Kontakten mit nahem Fuß); Veos Pass- und Ballbesitzdaten nur als zweite Meinung.

## Phase 4: US3 – Ball und Ballführung (P3)

- [ ] T017 [US3] `tests/test_ball_physics.py`: Parabelanpassung an synthetischen Strahlen (bekannte Höhe), Rollen mit Reibung, Aufspringen, zu kurzer Flug bleibt „unbekannt“.
- [ ] T018 [US3] `tools/ball_physics.py`: Flug, Rollen, Aufspringen, Höhe aus der Wurfparabel.
- [ ] T019 [US3] `tests/test_ball_events.py`: Kontakte, Pässe, Schüsse auf synthetischen Spuren mit bekannten Kontakten.
- [ ] T020 [US3] `tools/ball_events.py`: Ereignisse mit Zeit, Spieler, Körperteil und Sicherheit.
- [ ] T021 [US3] `tools/ball_eval.py`: Zeitfehler, gefundene und erfundene Kontakte, Spieler und Körperteil, Höhenfehler (SC-003, SC-004).
- [ ] T022 [US3] `tools/ball_motion.py`: Ballspur aus Physik zwischen den Ereignissen, Kennung „erschlossen“; Dribbling mit Abstand zwischen den Berührungen.
- [ ] T023 [US3] Anbindung in `scene_output.py` und `own_scene.py` (Ballspur mit Höhe und Kennung; `attach_ball` nur noch ohne erkannte Kontakte); Viewer färbt erschlossene Abschnitte und zeigt die Höhe.
- [ ] T024 [US3] Messung an den markierten Szenen, Bericht mit erreichten Werten und ehrlichen Grenzen.

## Phase 5: US4 – Texturen aus den nächsten Bildern (P4)

- [ ] T025 [US4] `tests/test_match_looks.py`: Auswahl nach Spielerhöhe, Mittelung, Rückennummer nur bei sicherer Lesung.
- [ ] T026 [US4] `tools/match_looks.py` und Änderung der Bildauswahl in `tools/veo_looks.py`.
- [ ] T027 [US4] Texturen für die Spieler der gewählten Szenen bauen, mit der Szenentextur vergleichen (Auflösung, Schärfe, Nummer).

## Phase 6: US5 – Bewegung am Kontakt (P5)

- [ ] T028 [US5] Lizenzen möglicher Bewegungsquellen prüfen, `research.md` ergänzen (nichts verwenden ohne Prüfung).
- [ ] T029 [US5] `tests/test_duel_events.py` und `tools/duel_events.py`: Zweikampf und Foul aus den Bahnen.
- [ ] T030 [US5] Gelenkpunkte am Kontakt in voller Auflösung (Ausschnitte), Schwungfenster ohne Fußfesthalten, Anpassung am Kontakt (`pose_fit.py`, `foot_planting.py`).
- [ ] T031 [US5] Schuss- und Zweikampfszene mit dem Video vergleichen, Durchdringungsprüfung.

## Phase 7: Abschluss

- [ ] T032 Umbau-Sicherheit: Szenen 705 und 722 und neun Viewer-Ansichten vor und nach den Änderungen vergleichen.
- [ ] T033 README, Plan und Aufgaben nachführen, Spec-Status setzen.
- [ ] T034 PR eröffnen.
