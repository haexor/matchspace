# Feature 004: Große Dateien teilen

**Status**: umgesetzt und geprüft
**Bezug**: Verfassung („Lines of code are a signal, not a rule“: Dateien deutlich über 500 Zeilen MÜSSEN geteilt
werden oder einen dokumentierten Grund samt Plan haben), [Feature 001, Complexity Tracking](../001-rueckennummern/plan.md)

## Anlass

Vier handgepflegte Dateien lagen deutlich über 500 Zeilen. Feature 001 hat sie begründet und einen Plan genannt
(„Folgefeature Szenenauswertung in Stufen aufteilen“); die Features 002 und 003 haben sie nicht angefasst.

| Datei | Zeilen vorher | Problem |
|---|---|---|
| `tools/veo_scene.py` | 902 | `main()` ist ein Block von rund 600 Zeilen mit sieben Stufen |
| `web/main.js` | 856 | Laden, Platz, Akteure, Aussehen, Bedienung und Bildschleife in einer Datei |
| `tools/pose_limits.py` | 617 | Gelenkgrenzen und das Festhalten der Füße (eigener Schrittplaner) |
| `web/avatar.js` | 614 | Gelenke abbilden, Modell umformen und anziehen, Videotextur samt Shader |

## Ziel

Jede dieser Dateien wird an echten Verantwortungsgrenzen geteilt, nicht an Zeilenzahlen. **Das Verhalten bleibt
bitgleich**: Es ist ein reiner Umbau, kein Feature.

## Nicht-Ziele

- Keine Änderung an Algorithmen, Schwellen oder Ausgabeformaten.
- Kein Umbau der Tests der Features 001 bis 003.
- Vendorte Dateien (`web/vendor/`) und erzeugte Dateien bleiben unberührt.

## Anforderungen und Erfolgskriterien

- **FR-001**: Keine handgepflegte Quelldatei liegt über 500 Zeilen. *Erreicht: größte Datei 454 Zeilen.*
- **FR-002**: Die Szenenrechnung liefert in beiden Betriebsarten (ohne und mit Veo) bitgleich `tracks.bin`, `poses/`,
  `meta.json` und die 2D-Gelenkpunkte. *Erreicht, auch nach der Teilung von `pose_limits.py`.*
- **FR-003**: Die synthetischen Haltungen (`synth_poses.py`) bleiben bitgleich. *Erreicht.*
- **FR-004**: Der Viewer zeigt neun Referenzansichten pixelgleich (Übersicht zweier Szenen, Draufsicht, zwei
  Nahaufnahmen des Körpermodells, Skelette, einfache Figuren, ohne Bedienelemente, synthetisches Spiel). *Erreicht.*
- **FR-004a**: Die Ich-Perspektive hängt von der Bildzeit ab und ist auch in der Referenz nicht reproduzierbar; sie
  wurde nur auf Unversehrtheit geprüft.
- **FR-005**: Verschobene, rein rechnende Funktionen bekommen Tests, wo es keine gab (`scene_util`, `scene_boxes`,
  `foot_planting`). *Erreicht: 36 neue Tests.*
- **FR-006**: README und Verweise in den Dokumenten stimmen mit der neuen Aufteilung überein.

## Annahmen

- „Bitgleich“ ist der Maßstab, weil `veo_scene.py` keine Tests hat und jede stille Abweichung die Qualität der
  Szenen verändern würde.
