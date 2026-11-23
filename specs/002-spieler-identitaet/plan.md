# Implementation Plan: Eine Identität je Spieler über die ganze Szene

**Branch**: `002-spieler-identitaet` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-spieler-identitaet/spec.md`

## Summary

Heute zerfällt ein echter Spieler in rund 2,2 Identitäten, und 5,7–6,5 % der Spielerzeit gehören der
falschen Person. Die Hauptursache sind Spurwechsel im Gedränge, nicht Lücken ([research.md](research.md)
R0).

Der Plan:
1. **Trennen**: Spurwechsel an Kontaktstellen erkennen und die Spuren dort trennen (Belege: Bewegung,
   Nummer, Aussehen aus derselben Sekunde).
2. **Verbinden**: alle Stücke vorsichtig verbinden, vor allem über Laufweg und Rückennummer.
3. **Nummern je Spieler**: über die Lesungen aller Stücke abstimmen.

Das Aussehen ist bei rund 55 Pixeln Spielerhöhe nur ein schwaches Merkmal (AUC 0,6–0,7, R1). Es entscheidet
deshalb nur mit und nie allein. Ein Verhältnistest lässt unklare Fälle getrennt.

## Technical Context

**Language/Version**: Python 3.12 (`.venv`); Viewer unverändert

**Primary Dependencies**:
- vorhanden: NumPy, SciPy, OpenCV, Torch (CUDA), Transformers;
- neu ist nur das Modell DINOv2-small (Apache-2.0, lokal unter `models/hf`, nicht eingecheckt), keine neue
  Bibliothek.

**Storage**: Zwischenspeicher `{det}.appearance.npz` je Erkennung unter `data/work/`; Ausgabe wie bisher
(`web/data/…`)

**Testing**: `unittest`, `tests/test_identity_link.py`, `tests/test_appearance.py`; Ende-zu-Ende nach
[quickstart.md](quickstart.md)

**Target Platform**: Linux mit NVIDIA-GPU; ohne GPU langsamer

**Project Type**: Kommandozeilen-Werkzeuge (`tools/`)

**Performance Goals**: Merkmale je Szene rund 30 s (gemessen: rund 4200 Ausschnitte); Trennen und
Verbinden unter 5 s; gesamt deutlich unter 5 Minuten mehr (SC-005)

**Constraints**:
- keine Bilder nach außen, keine neuen Bilddaten im Viewer;
- Veo nur in `jersey_eval.py`;
- lieber getrennt als vertauscht (SC-002 vor SC-001).

**Scale/Scope**: zwei Referenzszenen, je rund 40 Spuren, rund 7 Wechsel und 5–8 Lücken

Offene Punkte (NEEDS CLARIFICATION): keine. Ob das Aussehen bei Wechseln trägt, entscheidet ein fester
Messpunkt am Anfang der Umsetzung (R3).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Geprüft gegen `.spaex/constitution.md`.

| Regel (Modalität) | Stand | Nachweis |
|---|---|---|
| Worktree auf Topic-Branch (MUST) | ✅ | `../matchspace.worktrees/002-spieler-identitaet`, Branch `002-spieler-identitaet` auf `001-rueckennummern` |
| Conventional Commits, keine Selbstreferenz (MUST) | ✅ | wie in 001 |
| Tests in eigenen Dateien (MUST) | ✅ | `tests/test_identity_link.py`, `tests/test_appearance.py`, Erweiterung `tests/test_jersey_eval.py` |
| Dateien über 500 Zeilen (MUST) | ✅ | neue Module je < 400 Zeilen; `veo_scene.py` wird nicht angefasst; Aufteilung der Altlasten bleibt Folgefeature (siehe 001) |
| Umbau getrennt von Verhalten (SHOULD) | ✅ | `own_scene.with_numbers` wird in kleinen Schritten erweitert, Abstimmung je Spieler als eigener Commit |
| ADR (MUST) | ✅ geplant | `docs/adr/0002-identitaet-ohne-fremddaten.md`: Bildmerkmale aus einem allgemeinen Modell, nur lokal und je Szene; Weg und Nummer vor Aussehen |
| Keine absoluten Pfade, keine Geheimnisse (MUST NOT) | ✅ | Modellordner über `HF_HOME` relativ zum Repo |
| PR nach main (MUST) | ⚠️ offen | kein Remote; Branch baut auf 001 auf |
| Phasen-Disziplin (MUST) | ✅ | baut auf 001 auf, das für beide Szenen läuft |
| graphify-first (MUST) | ✅ mit Hinweis | Graph-Snapshot vorhanden, aber vor 001 gebaut; Abfrage plus Prüfung von Hand, siehe unten |
| Ponytail: keine neue Abhängigkeit (Leitlinie) | ✅ | Transformers schon installiert; nur Modellgewichte |
| Datenschutz (Projektvorgabe) | ✅ | Merkmalsvektoren nur unter `data/work/`, nicht im Viewer, nicht weitergegeben; keine Gesichter, keine Namen |

**Geprüfte Kandidaten** (graphify plus Code von Hand):

| Kandidat | Entscheidung |
|---|---|
| `track_players.stitch` | verbindet beim Tracking Stücke nach Farbe und Erreichbarkeit, ohne Vorsicht und ohne Nummern; bleibt, `identity_link` arbeitet danach auf den fertigen Spuren |
| `jersey_identity.merge_by_number`, `_join_fragments`, `assign` | werden weiterverwendet; die Abstimmung läuft künftig je Spieler statt je Spur (Erweiterung von `vote`-Aufrufen, keine Kopie) |
| `jersey_reader.read_scene`, `crops_at`, `readings_for_tracks` | Muster für den Zwischenspeicher je Erkennung; `appearance.py` folgt ihm und nutzt den Bildzugriff gleich |
| `track_players.track_hues`, `veo_keypoints.torso_colour` | Farbmittel; laut Messung zu schwach (R1), werden nicht erweitert |
| `own_scene.drop_same_place` | bleibt für doppelte Spuren derselben Person |

**Ergebnis**: Gate bestanden.

## Project Structure

### Documentation (this feature)

```text
specs/002-spieler-identitaet/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/            # cli, eval-report, appearance-cache
├── checklists/requirements.md
└── tasks.md              # /speckit-tasks
```

### Source Code (repository root)

```text
tools/
├── appearance.py        # NEU: Bildmerkmale (DINOv2-small) und Größe je Erkennung, Zwischenspeicher
├── identity_link.py     # NEU: Kontakte, Wechselprüfung, Trennen, Verbinden mit Verhältnistest; CLI zum Prüfen
├── own_scene.py         # ÄNDERUNG: Ablauf Trennen → Verbinden → Nummern je Spieler
├── jersey_identity.py   # ÄNDERUNG (klein): Abstimmung über mehrere Stücke eines Spielers
└── jersey_eval.py       # ÄNDERUNG: wrongTimeShare, switches

tests/
├── test_identity_link.py
├── test_appearance.py
└── test_jersey_eval.py  # erweitert

docs/adr/0002-identitaet-ohne-fremddaten.md
README.md
```

**Structure Decision**: Es bleibt die flache Struktur unter `tools/`. Videozugriff (`appearance.py`) ist
getrennt von reiner Logik (`identity_link.py`), Einbindung in `own_scene.py`.

## Ablauf

```text
own_identities (Spuren) ─▶ appearance.read_scene ({det}.appearance.npz) + jersey_reader.read_scene ({det}.numbers.npz)
   ─▶ identity_link.contacts ─▶ Wechselprüfung (Bewegung, Nummer, Aussehen) ─▶ split
   ─▶ identity_link.link (Weg, Nummer, Aussehen, Größe; Verbote; Verhältnistest) ─▶ Spieler aus Stücken
   ─▶ jersey_identity.vote je Spieler ─▶ assign ─▶ merge_by_number ─▶ veo_scene (unverändert)
jersey_eval (getrennt): Identitäten, falsche Zeit, Wechsel, Nummern
```

## Reihenfolge der Umsetzung (für /speckit-tasks)

1. `feat(numbers):` Messbericht um `wrongTimeShare` und `switches` erweitern. Danach den Stand vor dem
   Feature messen.
2. `feat(identity):` `appearance.py` mit Zwischenspeicher und Tests.
3. **Messpunkt R3**: Wechselprüfung an den bekannten Wechseln und Kontakten. Kriterium: mindestens 5 von
   7 erkannt, höchstens 1 falsche Trennung je Szene. Danach entscheiden: Aussehen in der Wechselprüfung ja
   oder nein.
4. `feat(identity):` `identity_link.py` (Trennen, Verbinden) mit Tests; Einbindung in `own_scene`;
   Nummern je Spieler.
5. Gewichte und Schwellen an Szene 705 einstellen und an 722 prüfen; Viewer-Stichproben (SC-004).
6. `docs:` ADR 0002, README, Ergebnisse.

## Complexity Tracking

| Abweichung | Warum nötig | Einfachere Alternative verworfen, weil |
|---|---|---|
| Neues Modell (DINOv2-small, rund 90 MB Gewichte) | Farbmittel trennen Mitspieler nicht (AUC rund 0,5); allgemeine Bildmerkmale etwas besser (0,6–0,7) und bei Bildern aus derselben Sekunde voraussichtlich deutlich besser | Nur Weg und Nummer: Wechsel ohne Nummernbeleg blieben unerkannt. Ob das Modell bleibt, entscheidet der Messpunkt in Schritt 3; reicht es nicht, wird es wieder entfernt. |
| PR nach main noch nicht möglich | kein Remote | wie in 001 |
