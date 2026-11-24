# Plan: Große Dateien teilen

**Spec**: [spec.md](spec.md)

## Vorgehen

1. **Referenz zuerst.** Vor jeder Änderung werden die Ausgaben der unveränderten Fassung gesichert: Szene 705 in
   beiden Betriebsarten (ohne Veo und mit Veo) und neun Ansichten des Viewers aus einem Headless-Browser
   (reproduzierbar mit `--use-angle=gl-egl`).
2. **Wörtlich verschieben.** Code wird in benannte Stufen verschoben, ohne die Logik zu ändern. Wo Zustand geteilt
   wird, trägt ein kleiner Datensatz ihn (`Run`, `Observed`, `Joints`, `Game`, `PoseResult`).
3. **Vergleichen.** Nach jedem Schritt werden die Ausgaben mit der Referenz verglichen (`cmp`), die Berichtstexte
   zeilenweise, die 2D-Gelenkpunkte als Arrays.
4. **Statisch prüfen.** `ruff --select F` auf den geänderten Python-Dateien (undefinierte und ungenutzte Namen).

## Aufteilung

**`tools/veo_scene.py`** (73 Zeilen, nur Ablauf und Aufruf):

| Modul | Zeilen | Inhalt |
|---|---|---|
| `scene_context.py` | 71 | Eingaben und Uhr einer Rechnung (`Run`) |
| `scene_boxes.py` | 277 | Boxen verketten, Veo oder eigenes Tracking zuordnen, Ausreißer entfernen, glätten |
| `scene_keypoints.py` | 311 | Gelenkpunkte, Suche ohne Box, Lücken füllen, Bodenphasen |
| `scene_positions.py` | 186 | Spielstand und eigene Position |
| `scene_poses.py` | 137 | Haltung je Figur |
| `scene_output.py` | 98 | Schreiben der Szene und Bericht |
| `scene_util.py` | 68 | reine Array-Hilfen (mit Tests) |

**`tools/pose_limits.py`** (424): Das Festhalten der Füße (`contacts`, `body_pace`, `step_plan`, `plant_feet`) ist in
`tools/foot_planting.py` (212). `_runs` ist als `runs` öffentlich, weil `pose_fit.py` es mitbenutzt.

**`web/main.js`** (454): `track.js` (86, Spieldaten und Posen), `stadium.js` (250, Platz, Kulisse, Tore),
`props.js` (49, Nummernschild und Ball), `looks.js` (53, Videotextur und Trikot je Spieler).

**`web/avatar.js`** (368): `avatar-body.js` (149, umformen und anziehen), `avatar-look.js` (105, Videotextur und Shader).
Die Skriptversion im Viewer steigt auf 14, damit Browser keine alte Mischung aus zwischengespeicherten Dateien laden.

## Ergebnisse

- `veo_scene.py`, beide Betriebsarten, Szene 705: `tracks.bin`, `meta.json`, `poses/000.bin`, alle 160 und 90 Arrays der
  2D-Gelenkpunkte **bitgleich**; Berichtstexte gleich bis auf eine Zeile (die Suche ohne Box kam aus dem Zwischenspeicher,
  den der Referenzlauf erst angelegt hatte).
- `synth_poses.py` auf dem synthetischen Spiel: `meta.json` und alle Pose-Blöcke bitgleich.
- Viewer: neun Ansichten pixelgleich.
- Nach der Teilung von `pose_limits.py` und dem Beheben des Fehlers unten: Szene 705 in beiden Betriebsarten wieder in allen Dateien und
  Arrays **bitgleich**, Berichte gleich.

## Fehler, die beim Prüfen auffielen

- Beim Auslagern des Fußblocks hatte ich `_runs` in `runs` umbenannt, aber einen weiteren Aufruf in `pose_limits.py`
  übersehen. Die Unit-Tests zeigten das nicht (diese Funktion hat keinen Test), erst der Lauf von `synth_poses.py`
  (`NameError`). Daraufhin: `ruff --select F` auf alle geänderten Dateien, und der Lauf der Szenen nach der Teilung
  von `pose_limits.py` wurde wiederholt.

## Bekannte Grenzen

- Für `web/*.js` gibt es keine Unit-Tests und keine lokale JS-Laufzeit. Den Maßstab bilden die Ansichten; Pfade, die sie
  nicht ausführen (Wiedergabe, Bedienung, Ich-Perspektive), prüft nur die Sichtung der Verschiebung und eine eigene
  Namensprüfung. Ein Linter lag nicht lokal vor, ein Aufruf von `bunx eslint` wurde abgelehnt und nicht umgangen.
- Die Teilung begann ohne Spec-Kit-Durchlauf (Spec, Plan, Freigabe), weil der Plan schon in Feature 001 stand und der
  Nutzer freie Hand gab. Spec, Plan und Aufgaben sind hier nachgetragen.
