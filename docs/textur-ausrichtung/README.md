# Versuchsbericht: Warum die Rückennummer verzerrt und verschmiert ist

Stand 2026-11-26, Nahszene `nah_1466.mp4`.
Die Bilder (`*.png`) liegen lokal unter `data/work/doku-bilder/textur-ausrichtung/` und sind nicht eingecheckt: sie zeigen Videomaterial von Jugendspielern, und das Repository ist öffentlich. Messungen mit dem Rückenaufdruck von own-6, opponent-15, own-15 (weiße Nummer).

## Ausgangslage

Die Ansichten-Textur (`veo_looks.py --ansichten 4 --maske`) holt den Rückenaufdruck aus einem einzelnen Videobild.
Im Viewer ist die Nummer aber schmal, in die Länge gezogen und verwaschen („6“ sieht aus wie „8“).

*Bild (lokal, nicht eingecheckt): `00-viewer-vorher-nachher-ansichten.png` – Viewer vorher/nachher*

## Versuch 1: Raster der Rumpfstellen über das Foto legen

Das Modell legt je Videobild ein Raster aus Rumpfstellen auf den Spieler (rot = Rücken). Zwei fast benachbarte Bilder (21 und 23):
Die „6“ liegt im Raster einmal links, einmal in der Mitte, obwohl sich der Spieler kaum bewegt hat.

*Bild (lokal, nicht eingecheckt): `01-raster-auf-foto-bild21-23.png` – Raster, Bild 21 und 23*
*Bild (lokal, nicht eingecheckt): `02-raster-auf-foto-bild22.png` – Raster, Bild 22*

Gemessen (weiße Pixel des Aufdrucks, Lage im Modell): Streuung des Winkels 16° (own-6), 33° (opponent-15), 29° (own-15).
Wichtig zur Einordnung: Die Kachel hat 64 Texel rund um den Rumpf, also 5,6° je Texel. 16° sind rund 3 Texel, die Nummer ist etwa 8 Texel breit.
Das ist ein Fünftel der Nummernbreite, nicht so breit wie die Nummer. (Meine erste Einschätzung war da zu groß.)

## Versuch 2: Rumpfdrehung je Bild nachfahren (`--drehung`)

Je Bild und Spieler Drehung ±40° suchen, bei der der Rumpf am besten zum Mittel passt; zwei Runden. Standard aus.

| | Streuung vorher | nachher |
|---|---|---|
| own-6, Winkel der Nummer | 16,0° | 13,8° |
| Sprung zu Nachbarbild | 12,3° | 10,1° |

Fast keine Wirkung.

## Versuch 3: Ausrichtung auf ein einziges scharfes Rückenbild

Bild 22 als Bezug; je anderes Rückenbild Drehung ±40° und Verschiebung ±4 px gesucht (118 Bilder).

| | vorher | nachher |
|---|---|---|
| Streuung des Winkels | 16,7° | 17,0° |
| Streuung der Zeile | 5,3 Texel | 6,0 Texel |

Keine Besserung, die Passung bleibt schlecht (Farbabstand 50 bis 60). Der Fehler ist nicht starr (Drehung/Verschiebung), sondern von Bild zu Bild verrauscht.

*Bild (lokal, nicht eingecheckt): `03-rueckenkachel-referenz-vorher-nachher.png` – Rückenkachel: Referenz, Mittel unausgerichtet, ausgerichtet*

## Versuch 4: Haltung zeitlich glätten (Messgerät: `harness.py`, Scratchpad)

Gelenkpunkt-Versatz und/oder Welt-Gelenke mit einem Gauß über die Zeit glätten (σ = 1,5 und 3 Bilder). Messung: Streuung des Nummernwinkels / Sprung zu Nachbarbild (Grad):

| Variante | own-6 | opponent-15 | own-15 | own-5 | opponent-7 |
|---|---|---|---|---|---|
| Ist-Zustand | 16,8 / 9,6 | 18,9 / 13,7 | 18,2 / 11,8 | 4,1 / 3,7 | 26,4 / 13,0 |
| ohne Versatz zu den Gelenkpunkten | 27,5 / 11,9 | 28,5 / 16,0 | 37,5 / 13,8 | 6,3 / 4,4 | 14,9 / 8,9 |
| Versatz geglättet σ=3 | 16,4 / 9,7 | 18,5 / 12,5 | 15,8 / 14,6 | 4,2 / 4,0 | 27,8 / 17,2 |
| Welt-Gelenke geglättet σ=3 | 15,7 / 9,9 | 19,9 / 11,6 | 18,2 / 14,8 | 3,4 / 3,2 | 30,5 / 14,6 |
| beides σ=3 | 16,9 / 9,5 | 18,1 / 11,2 | 15,3 / 12,9 | 3,9 / 3,4 | 26,6 / 11,9 |

Glätten ändert nichts. Das Rauschen ist also kein hochfrequentes Zittern der Gelenke. Der Versatz zu den erkannten Gelenkpunkten hilft (ohne ihn ist es bei 4 von 5 Spielern schlechter).
Nebenbeobachtung: Die Zeilen-Streuung (5 bis 7 Texel) ist größer als die Winkel-Streuung (3 Texel). Vertikal ist die Lage unsicherer als seitlich.
Roh: [exp1-glaettung.log.txt](exp1-glaettung.log.txt). Die weiße Nummernerkennung ist grob (Schriftzug, Verdeckung): Unterschiede unter ca. 3° sind nicht belastbar.

## Versuch 5: Passen Aufnahme-Modell und Viewer-Avatar zusammen?

Fund im Code: Der Viewer (`web/avatar-look.js`) liest die Textur nach dem **Polarwinkel** der Netzpunkte um die Rumpfachse.
`veo_looks.py surface()` schrieb sie nach dem **Parameter der Ellipse**. Beim schmalen Rumpf (0,14 m breit, 0,095 m tief) landen Merkmale
im Viewer um rund 30 % näher an der Rückenmitte, als sie am Spieler sitzen (z. B. 10° Ellipsenparameter = 2,4 cm, im Viewer 1,7 cm).
Behoben: `surface()` nutzt jetzt den Polarwinkel (Radius ρ(φ) = 1/√((cos φ/rz)² + (sin φ/rx)²)).
Die Szenen wurden mit dem Fix neu gerechnet (`veo-szene-nah-polar-ansichten`, `veo-szene-nah-polar-mittel`).

Links alt, rechts mit Polarwinkel (Ansichten-Textur): Die Nummer ist leicht breiter, aber weiter in die Länge gezogen. Der Fehler ist damit nicht behoben.

*Bild (lokal, nicht eingecheckt): `04-viewer-ansichten-alt-vs-polar.png` – Ansichten alt vs. polar*
*Bild (lokal, nicht eingecheckt): `06-rumpfkacheln-alt-vs-polar.png` – Rumpfkacheln alt vs. polar (je Spieler: links alt, rechts polar)*

Für das Mittel mit der sauber gedruckten Viewer-Nummer (Standardweg, links alt, rechts polar) ist kaum ein Unterschied zu sehen:

*Bild (lokal, nicht eingecheckt): `07-viewer-mittel-alt-vs-polar.png` – Mittel alt vs. polar*

## Versuch 6: Schachbrett auf den Avatar

Statt der Videotextur ein Schachbrett (Zellen 8 × 8 Texel, Rückenmitte schwarz, Vorderseite blau, grüne Linie alle 16 Zeilen) in den Atlas gelegt und im Viewer angesehen
(`veo-szene-nah-gitter`).

*Bild (lokal, nicht eingecheckt): `05-viewer-schachbrett-auf-avatar.png` – Schachbrett auf dem Avatar*

Ergebnis: Die Zellen sind an der Rückenmitte etwa doppelt so hoch wie breit (gemessen im Bild: ca. 28 px × 65 px). Das Modell der Aufnahme erwartet für 8 × 8 Texel etwa
7,6 cm × 10,6 cm (Seitenverhältnis 1 : 1,4, bei Spinelänge 0,5 m). Der Avatar zeigt etwa 6,7 cm × 13 cm. Zwei Abweichungen:
- Avatar-Rücken ist flacher/schmaler als die Ellipse im Modell (seitlich 3,4 statt 3,8 cm je 22,5°).
- Die Spinelänge im Avatar ist größer als im Aufnahmemodell (ca. 0,6 statt 0,5 m, grob geschätzt, nicht gemessen).
Zusammen ergibt das eine senkrechte Streckung des Aufdrucks im Viewer um rund 1,3 bis 1,4. Die Zahlen sind aus dem Bild geschätzt.

**Korrektur (nach Versuch 7):** Direkt am Netz gemessen sind die Zellen 1,1 cm hoch und 1,4 cm breit je Texel, also fast quadratisch. Die Schätzung aus dem Bild war zu grob (Perspektive, Maßstab), und diese Erklärung der Verzerrung war falsch.

## Versuch 7: Aufnahme direkt auf dem echten Avatar-Netz (wie bei Videospielen)

Die Frage, ob das Aufnahmemodell vom Viewer-Netz abweicht, habe ich so beantwortet, dass es sie gar nicht mehr gibt:
- `tools/avatar_bake.py` liest aus dem laufenden Viewer (Haken `?bake=1` in `web/main.js`) das Netz in der Grundhaltung und je Bild die Knochenmatrizen aller Figuren (250 Bilder, 20 Figuren, rund 100 s).
- `tools/avatar_mesh.py` rechnet zu jedem Texel der Kachel das Dreieck des Netzes (aus den Texturkoordinaten des Viewers) und daraus je Bild Weltpunkt und Normale mit den Hautgewichten des Viewers.
- `veo_looks.py --netz PKL` legt die Videobilder auf genau diese Punkte. Wo das Netz keine Fläche hat (unterhalb der Hüfte, über den Schultern), bleibt das alte Modell.
- Prüfung: Hüfte (t=0) und Schulter (t=1) des Netzes liegen bis auf 2 cm auf den Gelenkpunkten der Daten; die Spine ist im Netz 0,389 m, in den Daten 0,414 m.
- Zeilenabstand im Netz 1,1 cm, Spaltenabstand am Rücken 1,4 cm (Verhältnis 0,8; ein 15 Texel breiter und 18 Zeilen hoher Aufdruck ist damit etwa 1 : 1 breit zu hoch).

Ergebnis: Die Nummer sieht fast gleich aus (links Zylinder mit Polarwinkel, rechts echtes Netz). Der Unterschied von Modell und Netz war also **nicht** die Hauptursache.

*Bild (lokal, nicht eingecheckt): `08-viewer-netzaufnahme-vs-zylinder.png` – Netzaufnahme vs. Zylinder*

## Versuch 8: Was die Nummer wirklich schmal gemacht hat

Einzelbild (Bild 22, own-6) in die Kachel gelegt, oben mit Zylinder, unten mit Netz: Die Nummer ist dort 15 Texel breit und 18 Zeilen hoch, also normal proportioniert.
In der fertigen Ansichten-Textur war sie nur etwa 7 Texel breit. Der Grund steht im Filter von `view_texture`: Werte, die mehr als `VIEW_OUTLIER` vom unscharfen Mittel abweichen, zählen nicht.
Weißer Aufdruck auf rotem Trikot liegt 150 bis 300 vom Mittel entfernt (das Mittel ist an der Stelle rosa). Mit 110 blieb nur die Mitte der Nummer stehen: schmal und hoch.

*Bild (lokal, nicht eingecheckt): `09-einzelbild-atlas-zylinder-oben-netz-unten.png` – Einzelbild im Atlas*

Filter für den Rumpf praktisch aus (400): Die Nummer wird breit und zusammenhängend, der Sponsor-Schriftzug darüber lesbar (rechts):

*Bild (lokal, nicht eingecheckt): `10-viewer-filter-110-vs-aus.png` – Filter 110 vs. aus*

Nebenwirkung: Ohne Filter färben Fremdfarben den Kopf (grüner Spieler mit rotem Gesicht, links). Deshalb jetzt je Teil: Rumpf 400, Kopf 110 (rechts).

*Bild (lokal, nicht eingecheckt): `11-viewer-kopf-ohne-filter-vs-kopf-gefiltert.png` – Kopf ohne Filter vs. gefiltert*

## Versuch 9: Nur ein Bild für den Rücken (`--tiefe 1`)

Bis zu zwei weitere Bilder durften Lücken des besten Bilds füllen (`--tiefe 3`). Mit `--tiefe 1` kommt der Rücken nur aus dem besten Bild. Das Ergebnis im Viewer ist gleich:
Die Nummer stammt schon bei Tiefe 3 aus einem einzigen Bild. Die Unschärfe liegt also nicht am Mischen, sondern am Quellbild.

*Bild (lokal, nicht eingecheckt): `13-viewer-tiefe3-vs-tiefe1.png` – Tiefe 3 vs. Tiefe 1*

Umlauf um own-6 mit der Textur aus einem Bild (Drehung −90° bis 225°): Von hinten ist die Nummer als weißer Block mit dunklen Stellen zu sehen, aus schrägen Winkeln wirkt sie wegen der Perspektive schmal.

*Bild (lokal, nicht eingecheckt): `12-viewer-umlauf-eins-ansichten.png` – Umlauf*

## Versuch 10: Scharfes Foto statt Videobildern (Bild-KI)

Der Nutzer hat den kleinen Veo-Ausschnitt von opponent-15 (148 × 166 px, [23](23-eingabe-veo-ausschnitt-opponent-15.png)) mit Nano Banana zu einer scharfen Rückansicht aufbereitet ([22](22-eingabe-ki-rueckansicht-opponent-15.png)).
Die Schrift darüber ist erfunden, die Nummer stimmt. `tools/looks_from_photo.py` legt dieses Foto auf den Avatar:
- Person und Trikot im Foto finden (`models/yolo11x-seg.pt`, grüne Pixel in der Personenmaske). Saum und Kragen bestimmen die Höhe, die Breite auf halber Rumpfhöhe die Breite: das Trikot im Foto wird auf das Trikot des Avatars gelegt (wie bei einer von Hand gelegten UV-Abwicklung).
- Jeder Texel des Rückens (Netz in der Grundhaltung, `AvatarMesh.rest_points`) liest die Farbe an seiner Stelle im Foto (Kachel in vierfacher Größe).
- Farben auf die Videotextur angleichen (Quantile je Kanal), nur Trikotbereich, bis 75° um die Rückenmitte, weich in die Videotextur ausgeblendet.

*Bild (lokal, nicht eingecheckt): `18-foto-abbildung-auf-avatar.png` – Abbildung auf dem Foto*
*Bild (lokal, nicht eingecheckt): `19-foto-rumpfkachel-vorher-nachher.png` – Rumpfkachel: Video (links), Foto (rechts)*

Im Viewer (links Video, rechts Foto; grüner Spieler = opponent-15):

*Bild (lokal, nicht eingecheckt): `20-viewer-video-vs-foto.png` – Video vs. Foto*
*Bild (lokal, nicht eingecheckt): `21-viewer-umlauf-foto.png` – Umlauf*

Ergebnis: Rücken scharf, „15“ und Schrift lesbar, von allen Seiten stabil.

Offen bei diesem Weg: nur Rücken des Rumpfes; Vorderseite, Seiten, Arme, Hose, Kopf aus je einem eigenen Foto; die Schrift ist von der KI erfunden (Sponsor); Hals und Übergang zur Videotextur an den Seiten leicht sichtbar.

## Versuch 11: Automatisierung (Stand)

Ziel: pro Spieler automatisch passende Fotos aus dem Video heraussuchen, von einer Bild-KI zu scharfen Ansichten aufbereiten lassen (mit bekannter Nummer und bekanntem Trikottext im Prompt) und auf den Avatar legen.
- `tools/photo_candidates.py` (fertig): wählt aus den Szenendaten je Spieler die besten Ausschnitte für hinten/vorn/links/rechts (Frontalität, Größe in Pixeln, freistehend, vollständig im Bild, schärfstes unter den besten) und schneidet sie aus dem Video zu. Nahszene: 8 von 19 Spielern haben eine brauchbare Rückansicht oder mehr, der Rest steht zu weit weg (unter 60 px). Über das ganze Spiel (Spielerzuordnung über Szenen hinweg) wird es mehr.
- `tools/looks_from_photo.py` (fertig für Rumpf hinten): legt ein Foto auf den Avatar.
- `web/spieler.html` (fertig): ein Spieler einzeln als 3D-Modell mit Drehteller, freier Kamera, Haltung aus wählbarem Bild.
- Offen: KI-Anbindung (Anbieter austauschbar, Zwischenspeicher, Probelauf ohne Aufruf), Prompt aus Fakten (Nummer, Farben, Trikottext je Mannschaft, Haar und Gesicht aus dem Ausschnitt), Auflegen von Vorderseite, Hose, Armen und Kopf (Gesicht, Haare).

## Versuch 12: Bild-KI-Vergleich über OpenRouter (6 Fälle × 6 Modelle)

`tools/photo_ai_bench.py` (Schlüssel aus `.env`), Ergebnisse unter `data/work/ki-bench/` (nicht im Repo, Kinderbilder), Bilder je Fall: `ki-vergleich-*.png` in diesem Ordner.
Prompt aus Fakten (Ansicht, Nummer, Trikotfarben, Schrift je Mannschaft), mit Hinweis, Pose und Drehung des Ausschnitts zu ignorieren und exakt von hinten/vorn/seitlich zu stehen.
Urteil: Claude Sonnet 5.5 als Richter (urteilt sehr nachsichtig, kaum Unterschiede bei Foto und Fehlern). Kosten: von OpenRouter (`kosten.jsonl`).

| Modell | USD/Bild | Nummer/Schrift richtig (von 6) | Bemerkung |
|---|---|---|---|
| meta/muse-image | 0,010 | 5/5, 5/5 | billigster; nach Prompt-Zusatz gerade; Gesichter und Hintergründe natürlich |
| openai/gpt-image-2.5-flare | 0,010–0,054 (im Mittel 0,020) | 5/6, 5/6 | Kosten schwanken je Aufruf |
| openai/gpt-image-2.5-sunburst | 0,010–0,054 (im Mittel 0,026) | 6/6, 6/6 | |
| google/gemini-nano-banana-2.1 | 0,039 | 6/6, 6/6 | schnellster (11 s); bei own-5 geht die Figur statt zu stehen |
| black-forest-labs/flux-3-image | 0,048 | 5/6, 6/6 | setzt bei opponent-7 eine falsche Nummer auf die Brust |
| x-ai/grok-imagine-image-2.0 | 0,070 | 4/6, 4/6 | teuerster, öfter falsche Nummer/Schrift |
| microsoft/mai-image-2.7 | – | – | Inhaltsmoderation blockiert (Kind im Eingabebild) |

Wichtig: Bei kleinen Ausschnitten (own-5: 80 px hoch, opponent-7 Vorderansicht: 108 px) erfindet jedes Modell Gesicht, Haarfarbe und Hautton, und die Modelle erfinden verschiedene Personen. Trikotfarbe, Nummer und Schrift sind zuverlässig (stehen im Prompt), die Person nicht.

## Was bleibt

- **Behoben:** Die Nummer ist nicht mehr zu schmal. Das war der Filter, nicht die Haltung und nicht das Netz.
- **Weiter unscharf:** Ein „6“ ist nur ein weißer Block mit dunklen Stellen. Der Spieler ist 85 bis 140 px hoch, die Nummer im Video etwa 8 × 12 px. Mehr Schärfe gibt es nur über mehrere Bilder, und die liegen durch die Rumpflage um ±3 Texel seitlich und ±5 Texel senkrecht auseinander (Versuche 1 bis 4).
- **Pragmatische Lösung:** Schriftzug und Stoff aus dem Video, Nummer als saubere Schrift vom Viewer drucken (Nummer ist bekannt). Dafür muss `looks_clean.py` nur das Nummernfeld überdecken und nicht den ganzen Rücken.
- **Nicht gelöst:** Unterarmflecken (Armhaltung); Rumpflage je Bild (Verwindung, nicht starr).
- **Tauglich als Werkzeug:** `avatar_bake.py` und `avatar_mesh.py` sind jetzt da und können später auch für Arme und Beine genutzt werden (`--netz`), gleiche Textur-Koordinaten wie im Viewer.

## Hinweis zum Prüfen

Port 8765 wird gerade von einer anderen Sitzung belegt (`matchspace.worktrees/main-view/web`, ohne meine Änderungen an `web/avatar.js`/`web/looks.js`).
Dort zeigt der Viewer bei Ansichten-Szenen zusätzlich die gedruckte Nummer. Für diesen Bericht läuft ein eigener Server: `cd web && python3 -m http.server 8777`,
Vergleichsseite: `http://localhost:8777/data/vergleich.html?a=SZENE&b=SZENE`.

## Versuch 13: Bild-KI-Anbindung (`tools/photo_ai.py`)

Rangliste des Vergleichs (6 Fälle, Urteil des Sprachmodells + deine Sterne): 1. GPT Image 2.5 Sunburst (92,5; 5,0 Sterne), 2. Nano Banana 2.1 (90,0), 3. GPT Image 2.5 Flare (87,3), 4. Meta Muse (86,3; mit 0,010 USD je Bild am billigsten), 5. FLUX 3 (81,6), 6. Grok Imagine 2.0 (77,8; teuerste, Nummer/Schrift oft falsch).

Die Anbindung nutzt Sunburst, Muse als Ersatz bei Ablehnung/Ausfall. Je Spieler und Ansicht wird zwischengespeichert (Prüfsumme aus Prompt und Ausschnitt): ein zweiter Lauf kostet nichts, geänderter Prompt erzeugt nur die betroffenen Bilder neu.

Lauf auf der Nahszene (11 Spieler, hinten + vorn, 17 Bilder + 8 Wiederholungen der Vorderseite nach Promptänderung): 0,32 + 0,12 USD, im Mittel 0,019 USD je Bild (Sunburst schwankt zwischen 0,010 / 0,017 / 0,054 je Aufruf).
Ergebnis: `ki-pipeline-uebersicht.png` (Rückseiten, Nummer und Schrift stimmen), `ki-pipeline-vorn.png` (Vorderseiten).
Erste Vorderansichten erfanden Brustlogos und eine falsche Nummer auf der Brust (opponent-1001: hinten 42, vorn 14); seitdem sagt der Prompt, was vorn auf dem Trikot steht (`front` in teams.json, Standard: schlicht, kein Aufdruck).
Konsistenz: Die Vorderansicht bekommt die fertige Rückansicht als zweites Bild (Haare, Hautton, Statur wie dort; `ki-pipeline-hinten-vorn.png`). Kosten dieses Durchlaufs 0,12 USD für 6 Vorderansichten (Ø 0,020).
Offen: Das Gesicht bleibt ein plausibler Ersatz aus einem 40-px-Gesicht, keine Ähnlichkeit. Bei Spielern ohne bekannte Nummer (Kennung ab 1000) liest das Modell die Nummer aus dem Ausschnitt und druckt sie trotz Anweisung teils (own-1006: 7, own-1007: 9, opponent-1001: 42); das ist nicht geprüft und kann falsch sein. Die Nummer muss aus dem Kader oder einer Ziffernerkennung kommen. Die Rückenschrift in teams.json ist noch Test-Text.

## Versuch 14: Rück- und Vorderansicht der Bild-KI auf den Avatar (`tools/looks_from_photo.py`)

Statt Schrift-/Trikotmasken (funktionierten nur für grüne Trikots) legt die Pose (`yolo11x-pose`: Schultern, Hüften, Knie, Knöchel; dazu Scheitel aus der Personenmaske) das Avatar-Netz ins Foto: senkrecht stückweise linear, die Breite je Ebene aus dem Abstand der Gelenke links/rechts. Die KI-Ansichten stehen gerade, die Gelenke werden mit Sicherheit 1,0 gefunden. Rumpf, Kopf, Ober- und Unterschenkel lesen ihre Farbe im Foto (nur innerhalb der Personenmaske); der Blendwinkel wählt je Texel Rück- oder Vorderansicht (weich bis 75°, an den Seiten bleibt die Videotextur). Arme bleiben aus dem Video (Grundhaltung des Avatars ist eine T-Haltung).
Stolpersteine: Die Personenmaske bricht bei `imgsz=1280` an den Shorts ab (Beine fehlten, Gewicht 0), bei 640 ist sie vollständig; Mannschaftsfarbe darf nicht in den Code (alte Fassung ging nur für Grün).
Aufruf für alle Spieler eines KI-Ordners: `looks_from_photo.py SZENE NETZ.pkl --ki data/work/ki-ansichten --ausgabe web/data/veo-szene-nah-ki`.
Ergebnis: `ki-viewer-vergleich.png` (Zeilen: Videotextur / KI-Textur; Spieler opponent-7 und own-1006 in sechs Drehwinkeln): Rückenschrift, Nummer, Haare und Gesicht scharf, Kragen und Beine ohne Videoverwaschung. Im Viewer: `spieler.html?match=veo-szene-nah-ki&player=own-5`.
Grenzen: Arme (Unterarmflecken) unverändert; Füße/Schuhe aus dem Video; Naht Rumpf/Beine sichtbar möglich; Nummern von Spielern ohne Kader-Nummer sind KI-Lesungen.

## Versuch 15: Ein Befehl je Szene (`tools/looks_ki.py`)

`looks_ki.py VIDEO DET KAMERA HINTERGRUND SZENE NETZ.pkl TEAMS.json --arbeit ORDNER --ausgabe AUSGABESZENE [--trocken]` verbindet die drei Schritte: Ausschnitte wählen (`photo_candidates`), Bild-KI (`photo_ai`, mit Zwischenspeicher und Kostengrenze), Ansichten auf die Avatare (`looks_from_photo --ki`). `--trocken` wählt nur die Ausschnitte und nennt Bilderzahl und Kosten (hier: 17 Bilder, Ø 0,56 USD, Obergrenze 0,92 USD), ohne KI-Aufruf. Geprüft: Lauf aus dem Zwischenspeicher erzeugt dieselbe `looks.png` wie die Einzelschritte (byte-gleich), Kosten 0.

## Versuch 16: Mannschaftsdaten selbst erkennen (`tools/team_detect.py`, `tools/team_text.py`)

Veo liefert im Export nur Altersklasse und Farben (`ownColor`, `opponentColor`), keine Vereinsnamen. `team_detect.py` erkennt deshalb aus dem Video:
- **Farben** (Trikot, Hose, Stutzen) aus der Videotextur nach Farbton/Sättigung benannt (Video macht Weiß bläulich und dunkel, der Farbton bleibt). Ergebnis: Gegner grün/weiß/weiß, wir rot/rot/rot.
- **Lange schwarze Ärmel** aus den echten Ausschnitten (dunkler Anteil an den Rumpfseiten, Median über die Spieler), nicht aus der Textur (Unterarme dort durch die Armflecken verunreinigt).
- **Rückenschrift:** `team_text.py` entzerrt die Rückenpartie aus vielen Bildern (`team-text-stapel.png`, Schultern/Hüfte aus der Haltung, ECC-Ausrichtung); ein Bildmodell liest nur, was zu sehen ist (`?` für Unleserliches). Ergebnis hier: Gegner „SV E…“ (Sicherheit 0,3–0,35), wir „?E??A“ (0,15–0,2): nicht lesbar (Schrift 3 px stark, nur 8 Rückenansichten, die Haltung ist je Bild leicht verdreht, das Mitteln wird unscharf). Übernommen wird der Text erst ab Sicherheit 0,7 und ohne `?`, sonst bleibt der Rücken ohne Schrift (`backTextRead` hält die Lesung fest).
Die Test-Schrift („SV Eilendorf“, „SV Beispiel“) war frei erfunden und stimmte nicht mit dem echten Aufdruck („SV E…“) überein.

Prompt-Korrektur: Bei unbekannter Nummer und ohne Schrift sagt der Prompt jetzt „Rücken völlig glatt, nichts drucken“; vorher druckte das Modell trotz „keine Nummer“ eine (8, 0, 9) und bei opponent-1001 sogar „SC Leipzig“. Ergebnis: `ki-ruecken-ohne-text.png`.
`looks_ki.py` braucht keine `teams.json` mehr (ARBEIT/teams.json wird erkannt und lässt sich dort korrigieren).

## Versuch 17: Rückenschrift aus mehr Bildern derselben Kamera (`team_text.py --szene` mehrfach)

Frage: Wird die Schrift lesbar, wenn man mehr Beobachtungen derselben Kamera zusammenlegt? Alle vorhandenen Szenen (Nahszene, Panorama 705 und 722), je Mannschaft 67–79 entzerrte Rückenpartien aus 13–14 Spielern, gemeinsam ausgerichtet (Verschiebung, ECC) und gemittelt. Ergebnis (`team-text-alle-szenen.png`): nein.
- Das Mittel ist unschärfer als die besten Einzelbilder (Pose und Perspektive je Bild verschieden, eine reine Verschiebung reicht zum Ausrichten nicht).
- Das Bildmodell liest aus dem Stapel gar nichts (Sicherheit 0,05); aus den Einzelausschnitten der Nahszene kam „SV E…“ (0,3). Mehr Bilder bringen mit dieser Kamera keine neue Information: die Schrift ist 2–4 px hoch, die Grenze liegt in der Auflösung.
- Die Panoramaszenen enthalten Spieler bis 115 px Höhe, aber ohne erkennbare Schrift.
Folge: Mehr Auflösung (nahe Kamera, zweite Perspektive) ist der Hebel, nicht mehr Bilder. Ein Mittel aus mehreren Kameras kann erst nach echter Registrierung (Perspektive je Bild, nicht nur Verschiebung) helfen; bei der Verschiebung allein bleibt es unscharf.
Stolperstein: Bei Panoramaszenen gehört das Video aus `det["video"]` (z. B. `data/work/.../scene_705.mp4`), nicht das ganze Panorama; sonst stimmen die Bildnummern nicht (Rasen statt Rücken).

## Versuch 18: Veo-`standard`-Video als zweite Perspektive?

Der Export (`export.json`, `videos[0].url`) enthält die öffentliche Adresse des `standard`-Videos (1920×1080, 30 fps, 3,4 GB, folgt der Aktion). Ein Ausschnitt von 25 s um die Nahszene (Sekunde 1470) lässt sich ohne Anmeldung direkt aus dem Stream schneiden (`ffmpeg -ss 1470 -i URL -t 25 -c copy`, 19 MB).
Messung (jedes 15. Bild, Personen nach Trikotfarbe grün/rot gefiltert): Spieler im Median 67 px hoch, >100 px in 45 von 50 Bildern mindestens einer, >120 px in 26 von 50. Das entspricht unserer Nahszene aus dem Panorama (120–131 px), also keine bessere Auflösung. Für 3-px-Schrift reicht das nicht. Das `standard`-Video ist damit eine zweite, unabhängige Sicht (andere Winkel, andere Momente), aber kein Auflösungsgewinn.

## Versuch 19: Arme aus den KI-Ansichten (`looks_from_photo.py`)

Der Avatar steht in T-Haltung, die Arme im Foto hängen. Jeder Armknochen (Schulter–Ellbogen, Ellbogen–Handgelenk) wird in der Bildebene (Drehung um die Tiefenachse, die Vorderseite bleibt vorn) aus der T-Lage in die Richtung der Pose-Punkte gedreht und auf deren Länge skaliert (`project_arm`). Ergebnis: `ki-arme-vergleich.png`: kurzer Ärmel, schwarzer Unterärmel, Hände, statt der Armflecken aus dem Video.
Was nötig war (Reihenfolge der Fehler):
1. Farbkorrektur nicht aus der Videotextur des Arms: Sie ist selbst verunreinigt (Armflecken); mit ihr wurden Arme des Gegners grün. Auch die Kurve vom Rumpf (fast nur Rot/Grün) verfärbt Schwarz und Haut. Es gilt jetzt ein einziger Helligkeitsfaktor (Verhältnis Video/Foto am Rumpf).
2. Blendwinkel bis 115° (Armseiten, die weder Vorder- noch Rückfoto frontal sieht, sind fast einfarbig).
3. Dünne Arme: Rand der Maske weg, Randtexel lesen den nächsten Punkt im Ärmelinneren (`snap_inside`).
4. Gelbgrüne Streifen am Arm: Die Personenmaske füllt die Lücke zwischen Arm und Körper, dort steht Rasen. Alles in Rasenfarbe (Lab-Abstand < 22 zum Median außerhalb der Person) zählt bei den Armen nicht zur Person.
Offen: Füße/Schuhe aus dem Video; Seitenansichten nicht eingebunden.

## Versuch 20: Seitenansichten und Füße

`photo_ai.py` erzeugt jetzt auch links/rechts (in Stufen: Rücken, Vorderseite mit dem Rücken als Referenz, Seiten mit Vorder- und Rückseite als Referenzen; der Prompt nennt die Blickrichtung: von links schaut die Figur nach Bildlinks). 18 Seitenansichten kosteten 0,41 USD (Ø 0,023). Haare, Gesicht, Statur und Kleidung passen zu den anderen Ansichten.
`looks_from_photo.py`: In der Seitenansicht trägt die Bildbreite die Tiefe (z des Avatars): `u = u_Ebene + Richtung · (z − z_Ebene) · Maßstab`. Die Blickrichtung (Nase gegen Hüfte) entscheidet, welche Seite das Foto wirklich zeigt. Der hängende Arm verdeckt in der Seitenansicht die Rumpfseite: dort wird nichts gelesen (Armband aus den Pose-Punkten). Füße kommen jetzt auch aus den Fotos.
Fehler, bis es stimmte:
1. Seitenansicht ließ grüne Flecken an Shorts und Stutzen entstehen: Die Personenmaske füllt die Lücke zwischen den Beinen. Dieselbe Rasenmaske wie bei den Armen (`snap_inside`) gilt jetzt für Arme, Beine, Füße und alle Seitenansichten.
2. Rasenfarbe aus dem ganzen Hintergrund war ein Mittel aus Himmel, Bäumen und Gras (own-1006): nur der untere Bildteil zählt.
3. Quantilkurve je Teil aus der verunreinigten Videotextur zog Knieschoner ins Grüne, ein Kanalfaktor färbte die Haut am Knie leuchtend grün. Beine, Füße und Seitenansichten bekommen deshalb nur einen Helligkeitsfaktor; der Kopf behält die Quantilkurve (sonst gelbe Gesichter).

## Versuch 21: Die KI-Bilder unverändert nutzen, nichts mitteln, kein Video als Füllung

Rückmeldung zu Versuch 20: Arme und Schuhe passten nicht, das schwarze Unterziehshirt verschwamm mit dem roten Trikot, und die Texturen wirkten wieder schwammig. Ursache: Der Übertragungsschritt rechnete erneut Mittelwerte und Angleichungen (Farbkurven und Faktoren gegen die Videotextur, gewichtetes Überblenden mit dem Video, Füllen aus Nachbarn). Außerdem war der Helligkeitsfaktor der Arme falsch gerechnet (Median über alle Kanalwerte zusammen ist bei Rot fast null, die Vorderseite jedes Arms wurde schwarz).
Jetzt (`looks_from_photo.py`):
- Jeder Texel liest seine Farbe unverändert aus dem einen Foto, das ihn am frontalsten sieht (Vorder-/Rückfoto bevorzugt, `FRONTAL_BIAS`); nur an einer schmalen Naht (`SEAM`) wird überblendet. Keine Farbangleichung an das Video, keine Videotextur dazwischen.
- Arme aus einem Foto (sonst Zacken, weil die Ärmellänge in den Fotos leicht abweicht); der von den hängenden Armen verdeckte Rumpf wird aus dem Median der Foto-Texel derselben Zeilen gefüllt, der Hals über den Rand-Fix (nächster Körperpunkt ohne Rasenfarbe).
Und die Fotos selbst (`photo_ai.py`, `photo_candidates.py`):
- Ansichten ohne Videoausschnitt erzeugt GPT Image aus den fertigen Ansichten desselben Spielers (hinten/vorn, eine Seite); die zweite Seite ist die gespiegelte erste (kostenlos).
- Kleinere Schwellen für die Ausschnitte (`--min-hoehe 36 --min-frontal 0.7`): 18 von 19 Spielern der Nahszene bekommen vier KI-Ansichten (vorher 11 mit teils nur einer Ansicht). Kosten dieses Durchgangs 1,18 USD (davon 0,42 USD durch erneutes Erzeugen der Seiten, nachdem ihre Referenzbilder dazugekommen waren).
- Ergebnis: Kopf, Arme, Beine und Füße zu 100 %, Rumpf zu 92 bis 95 % aus den Fotos (der Rest vom Arm verdeckt, aus den Foto-Texeln gefüllt). Nur Spieler ganz ohne Ausschnitt (1 von 19) und Sohlen/Kopfoberseite kommen nicht aus Fotos.
Offen: Gesichter von Spielern mit sehr kleinem Ausschnitt sind erfunden (plausibel, keine Ähnlichkeit); beim Gegner bleibt am Hals ein grünlicher Rest; Knie (Haut zwischen Shorts und Stutzen) wirkt stellenweise fleckig; der Saum hat kleine dunkle Stellen.

## Versuch 22: Kopf, Hals und Ränder (Nachbesserung zu Versuch 21)

Rückmeldung: Hals und Kopf wirkten falsch, teils „zwei Nasen, vier Augen“, und die Trikots hatten Löcher. Was die Nahaufnahmen im Viewer zeigten und was geändert wurde (`looks_from_photo.py`):
1. **Zwei Nasen**: Die Seitenfotos legten Augen und Nase versetzt neben das Gesicht. Der Kopf liest sie jetzt nur noch im schmalen seitlichen Streifen (`HEAD_SIDE_NZ`, Ohren, Schläfen), das Gesicht kommt allein aus dem Vorderfoto. Außerdem las der Kopf über `snap_inside` dunkle Haar-/Rasenpixel in das Gesicht (Flecken unter den Augen): Der Kopf liest jetzt direkt (nur Pixel in der Maske).
2. **Scheitel grün/weiß**: Der Scheitel liegt im Foto am Rand der Maske, dort steht Rasen oder Himmel zwischen den Haaren. Die letzten Kopfzeilen setzen die Haarzeile darunter fort (`CROWN_T`).
3. **Hals**: Er liest den nächsten Pixel mit Hautton (Farbart a/b in Lab nahe der Gesichtshaut desselben Spielers, `skin_reference`, `skin_like`); Trikot, Kragen und Haar fallen heraus. Die Seiten der Halsröhre lesen ebenfalls das Vorder-/Rückfoto (vorher Lücken, aus dem Trikot gefüllt: Zackenring).
4. **Himmel als Hintergrund**: Vor Himmel, Bäumen oder Zaun (statt Rasen) lasen Lücken zwischen Arm und Rumpf weiße Flecken. `grass_mask` bestimmt den Hintergrund jetzt auch zeilenweise aus dem Foto (Pixel rechts/links der Person).
5. **Arme**: Nur die Knochenachse wird abgebildet (die Röhre hat entlang der Achse ihre Farbe): kein Zackenrand mehr.
6. **Rumpflücken** (vom Arm verdeckt) füllt der Median der direkten Nachbarn, nicht der ganzen Zeile (die Rückennummer zog Weiß in die Seiten).
Verworfen: Halshaut schon ab `t > 1.05` oder mit Radiusbedingung (grüne/rosa Flecken an den Schultern).
Offen (Geometrie, keine Textur): An Ellbogen, Hüfte, Schulterrand und zwischen Kopf und Hals durchdringen sich die Röhren des Avatars (Arm im Rumpf, Hals im Kopf); die Teile zeigen sich dort gegenseitig durch (schwarze/rote Zacken, rosa Streifen am Saum). Das lässt sich nur im Netz oder in der Pose beheben. Das Gesicht belegt nur etwa 40 Pixel der Kopfkachel.

## Versuch 23: Saubere Teilegrenzen im Netz und größerer Kopfbereich

Die Zacken an Ellbogen, Knie und Hals (Versuch 22, „offen“) kamen nicht aus der Textur, sondern aus der Teilung des Viewer-Netzes (`web/avatar-look.js`): Jeder Netzpunkt gehört nach dem größten Hautgewicht zu einem Teil der Textur, der Shader bekommt Teil und Koordinaten (Winkel, t) der drei Punkte eines Dreiecks und interpoliert sie. Punkte am Gelenk rechneten ihre Koordinaten für das Nachbarteil: zwei Achsen mischten sich im Dreieck, der Rand zwischen Sockenband und Haut oder Ärmel und Unterärmel lief als Sägezahn in Dreiecksgröße.
Jetzt (`splitSeams`):
- An Gelenken (Oberarm/Unterarm, Oberschenkel/Unterschenkel) ist die Grenze eine Ebene senkrecht zur Achse des oberen Teils. Dreiecke, die sie schneiden, werden an der Ebene geteilt (neue Punkte je Seite, Lage und Normale interpoliert, Hautgewichte vom näheren Punkt). Die Grenze ist ein glatter Ring.
- An den übrigen Teilegrenzen (Rumpf/Oberschenkel, Hals/Kopf) gehört ein Dreieck zum Teil der Mehrheit seiner Punkte; die fremden Punkte bekommen Kopien mit den Koordinaten dieses Teils.
- Das Netz hat danach mehr Punkte; `tools/avatar_bake.py` liest es unverändert aus (neu backen: `avatar_bake.py SZENE OUT.pkl --von 0 --bis 1`, für Spielerfotos reicht ein Bild).
Größerer Kopf: Das Gesicht belegte nur etwa 32 Pixel der Kopfkachel. Der Kopfbereich liegt jetzt in der freien rechten unteren Ecke der Kachel (`veo_looks.SEGMENTS`, 256 × 256 statt 128 × 128 Pixel bei Kachel 512), das Gesicht bekommt etwa 64 Pixel. Szenen im alten Layout werden von `looks_from_photo.migrate_layout` beim Übertragen umgestellt (Kopfbereich hochskaliert kopiert, Meta angepasst); der Viewer liest die Rechtecke aus dem Meta.
Bleibt: Durchdringungen, wo sich Teile wirklich durchstoßen (Unterarm hinter dem Rumpf an der Hüfte).

## Versuch 24: Frisur liegt am Kopf an

Rückmeldung: Bei manchen Spielern sah das Haar wie ein hoher Bienenkorb aus. Ursache ist die Geometrie, nicht die Textur: Die Frisuren des Modells (`Hair_SimpleParted`, `Hair_Buzzed`) stehen am Scheitel bis zu 4 cm vom Kopf des Körpernetzes ab (bei 1,78 m Höhe Haar ±9 cm breit, Kopf ±6,5 cm) und bilden eine Haube mit Absatz über den Ohren.
Jetzt (`hugHead` in `web/avatar.js`, beim Laden des Modells): Jeder Haarpunkt, der weiter als `HAIR_THICKNESS` (1,2 cm) vom nächsten Kopfpunkt des Körpernetzes liegt, wird auf diese Dicke herangezogen, danach neue Normalen. Ansatz und Seiten der Frisur bleiben, der Überstand verschwindet; Textur und Farbe unverändert (aus dem Foto, wie bisher).
Verworfen: Frisur von oben stauchen (Ansatz rückt hoch, aber die Haube bleibt breit); 2,5 cm Dicke (Bienenkorb bleibt sichtbar).
Offen: Die Frisurform ist weiterhin die des Modells (zwei Stile), nicht die des Spielers; Locken oder lange Haare kommen nur als Farbe.

## Versuch 25: Augen und Ohren des Fotos auf die des Netzes legen, schlankerer Hals

Rückmeldung zu Versuch 24: Der Kopf hatte vier Ohren, vier Augenbrauen und einen Stiernacken. Ursache war die Abbildung (`looks_from_photo.fit`), nicht die Haare: Als obere Ebene der Kopfabbildung gilt der Scheitel der Personenmaske, also die Haarspitze des Fotos, und die wurde auf den Scheitel des Schädelnetzes gelegt. Das Foto zeigt die Haare mit Volumen (hier etwa 4 bis 5 cm über dem Schädel); alles darunter, Augen, Brauen und Ohren, rutschte dadurch auf dem Avatar nach unten. Das Netz hat seine Augenhöhlen und Ohren an der richtigen Stelle (1,70 m bei Kopfgelenk 1,60 m) und zeigte dort Stirn und Haar: zweites Augenpaar, zweites Brauenpaar und ein Ohr aus Foto neben dem Ohr des Netzes.
Jetzt: Die Augenpunkte der Posenerkennung (`eye_line`) sind eine weitere Abbildungsebene auf der Augenhöhe des Netzes (`EYE_ABOVE_HEAD`). Von vorn nur bei sicheren Augen (beide ≥ 0,5), von der Seite reicht ein sicheres Auge (≥ 0,3); von hinten bleibt es beim Scheitel (die Augenpunkte wären geraten). Gesicht, Brauen und Ohren sitzen damit auf denen des Netzes.
Stiernacken: `NECK_T` von 1,15 auf 1,22. Die Schulterkante des Netzes (±19 cm Breite bei 1,52 m, Hals ±6 cm) wurde als Haut gelesen und wirkte wie ein breiter Hals; jetzt deckt das Trikot sie. Mit 1,3 erscheint ein roter Streifen seitlich am Hals.
Bleibt: kleine dunkle Flecken am Ohr (Seitenfoto), Haaransatz im Nacken als Zackenlinie, die Frisurform ist weiterhin die des Modells.

## Versuch 26: Ohren passend, keine schwarzen Striche am Ohr

Rückmeldung zu Versuch 25: Die Ohren passen noch nicht ganz, schwarze Zacken vor dem Ohr. Zwei Ursachen:
1. **Ohrhöhe**: Das Ohr sitzt im Foto etwa 2,4 cm unter der Augenlinie, am Netz nur 1,3 cm; mit der Augenhöhe allein lag das Foto-Ohr gut 1 cm unter dem Netzohr. Im Seitenfoto gilt jetzt das Ohr als Abbildungsebene (`ear_point`, Ohrpunkte der Posenerkennung ≥ 0,4, Ohrmitte des Netzes `EAR_Y`/`EAR_Z`); ohne sicheres Ohr bleibt die Augenhöhe.
2. **Schwarze Striche** (Haarsträhnen, Ohrrand, Ohrring des Seitenfotos, auf die Wange vor dem Ohr gestreckt): `remove_ear_flecks` füllt kleine dunkle Flecken (unter 150 Texel zusammenhängend, Helligkeit unter 60) in der Ohrgegend aus der Umgebung; die Ohrgegend ist über die Netzpunkte des Kopfes definiert (`EAR_ZONE`), Augen und Brauen liegen außerhalb. Große dunkle Flächen (Haar) bleiben.
Ergebnis in der Nahszene: je ein Ohr aus dem Foto auf dem Netzohr, saubere Wange; beide Seiten und acht weitere Spieler angesehen.
Nachtrag (zweites Ohr): Auch danach blieb ein ohrförmiges Gebilde neben dem Ohr, von hinten schräg gesehen. Zwei Ursachen: (1) Die Frisur (`Hair_SimpleParted`) reicht an den Seiten bei |x| 0,07 bis 0,078 m und Höhe 1,69 bis 1,75 m über den oberen Teil des Ohrs (Strähnenrand am Ohr); `clearEars` in `web/avatar.js` lässt Haardreiecke, deren Mitte im Ohrbereich liegt, weg. (2) Das Netzohr bekam aus Vorder- und Rückfoto dunkle Haarrippen über seine Rückseite gestreckt; Texel des Netzohrs (`EAR_MESH_X`, `EAR_MESH_Y`) lesen jetzt nur die Seitenfotos.
Nachtrag (Ohren in Haarfarbe): Das Netzohr zeigte weiter ein dunkles, gerippt gestreiftes Gebilde. Die Texel des Netzohrs sahen kein Foto sauber (Vorder-/Rückfoto ausgeschlossen, im Seitenfoto verdecken Haare das Ohr) und wurden von der Lückenfüllung mit der Haarfarbe der Nachbarn gefüllt. Jetzt malt `paint_ear` sie zuletzt in der Hautfarbe der Wange (Median der Texel an der Vorderseite des Kopfes neben dem Ohr, `CHEEK_*`), danach entfernt `remove_ear_flecks` einzelne dunkle Punkte am Rand. Die Ohrform kommt vom Netz. Die Frisur lässt Dreiecke mit einem Punkt im Ohrbereich weg (`EAR_CLEAR`). Verworfen: Ohrmaske breiter (färbt Haar über dem Ohr als Hautblock).
`remove_ear_flecks` entfernt dazu dünne dunkle Striche (unter etwa 5 Texeln breit), die am Haar hängen und deshalb zu einem großen dunklen Zusammenhang gehören (bei own-15 schwarze Striche vor dem Ohr).

## Versuch 27: Das Gesicht kommt vom Modell

Rückmeldung: Lieber alle Gesichter gleich, aber vollständig und nicht gruselig, als vier Augen und sechs Ohren. Später, wenn ein gutes Bild des Gesichts da ist, wird das Gesicht entsprechend modelliert und eingefärbt.
Das Avatar-Netz ist schon diese Figur (zwei Ohren, zwei Augen, Nase, Mund); Doppelte entstanden nur, weil das Foto Augen, Brauen, Mund und Ohren als Farbe mitbrachte und sie neben die des Netzes legte. Jetzt (`model_face` in `looks_from_photo.py`):
- Die Gesichtsfläche (Vorderseite des Kopfes von der Stirn bis zum Kinn, `FACE_*`) bekommt die Hautfarbe des Spielers (Median der Wange im Foto), mit weichem Übergang zu Haar und Ohren.
- Die Lippen (`LIPS_*`) bekommen einen Ton darüber (`LIP_TINT`).
- Der Viewer zeigt die Augen und Brauen des Modells wieder: Die Szene trägt `looks.faceFromModel`, `web/looks.js` setzt dann `photo` nicht (der Viewer blendet die Modellaugen nur aus, wenn das Gesicht aus dem Foto kommt, ältere Szenen bleiben also unverändert).
Das Foto liefert damit Hautton, Haarfarbe und die Textur außerhalb des Gesichts. Ausbau später: Gesicht an Landmarken des Fotos formen (Augenabstand, Nasenbreite, Kinn) und einfärben.
Nachtrag (Hals): Der Hals wirkte aufgesetzt und der Nacken unproportional: Das Foto gab Hals und Schulterkante in einem anderen, fleckigen (rosa) Hauton als das Gesicht. Jetzt trägt der ganze Hals dieselbe Hautfarbe wie das Gesicht, die `skin_reference` aus Nase und Wange des Vorderfotos (`skin_bgr`): am Rumpf ab `MODEL_NECK_T` (1,53 m, Halsansatz, `model_neck`), am Kopf rundum unter der Haarkante (`NECK_LOW`, in `model_face`). Die Form des Halses (steile Schulterkante bei 1,52 m) ist die des Modells.

## Versuch 28: Hals als weicher Übergang von Schulter zu Kopf

Rückmeldung: Hals und Nacken wirkten gruselig, ohne fließenden Übergang. Drei Ursachen und Maßnahmen:
1. **Form** (`web/avatar-body.js`, `NECK_TAPER`): Der Rumpf lief vom Schulteransatz (1,47 m) bis zum Kinn (1,62 m) nicht zu, der Hals stand als Zylinder auf einer flachen Schulterkante. Jetzt verjüngt sich der Rumpf dort weich auf 82 % der Breite und Tiefe.
2. **Farbe** (`looks_from_photo.model_neck`): Nur die Röhre des Halses (Ellipse um die Halsachse, ab 1,505 m) hat die Hautfarbe des Spielers; die Schulterkante ringsum bleibt Trikot, der Kragen läuft als Ring um den Hals (vorher: Haut über die ganze Schulterkante, wie ein Trichter). Auch das Foto-gelesene Rosa an Nacken und Schulter entfällt.
3. **Zackenlinie im Nacken** (Naht zwischen Kopf- und Rumpfkachel): Der Viewer liest am Rand der Netzfläche Texel daneben (Filter, Dreiecksnähte); dort stand die Farbe der Füllung als dunkler Streifen. `spread_into_gaps` zieht die Hautfarbe 17 Texel über den Rand der Netzfläche hinaus (Kopf und Hals).
Dazu: Die Frisur wird im Nacken bei 1,675 m gerade abgeschnitten (`HAIR_BOTTOM`; vorher Zacken der Haarsträhnen).
Wichtig: Die Form des Netzes hat sich geändert; das Netz für die Übertragung muss neu gebacken werden (`tools/avatar_bake.py SZENE AUSGABE.pkl --von 0 --bis 1`), sonst liegen Fotos und Netz am Hals leicht daneben.
Nachtrag (Stufe am Halsausschnitt): Quer über den Hals lief ein V-förmiger Grat (Sprung). Ursache war nicht der Hals, sondern das Trikot: Im Netz trägt es 1,6 cm auf (`dress`, `PAD.shirt`), und zwar schlagartig ab dem Halsausschnitt (V-förmig, `fields` in `web/avatar.js`); die Haut davor blieb flach, die Trikotpunkte standen 1,6 cm höher. Jetzt läuft die Aufpolsterung über `PAD_RAMP` (3 cm) zum Rand aus, am Ausschnitt, an den Ärmeln und am Saum. Die Haut am Hals (`model_neck`) endet an genau demselben Ausschnitt wie das Trikot im Viewer (`NECKLINE`), statt an einer eigenen Höhe: Der Kragenring liegt dort, wo die Geometrie endet. Netz neu gebacken (Form geändert).

## Versuch 29: Rückenpartie mit scharfer Nummer als eigenes Bild

Rückmeldung: Die Trikottextur ist schwammig, die Nummer unscharf. Ursache: Die Rumpfkachel hat 256 Texel um den ganzen Körper; die Rückennummer (etwa 20 cm breit) bekommt daraus rund 40 Texel, das Foto aber bietet etwa 150 Pixel. Gleichzeitig filtert der Viewer die Kachel bilinear.
Jetzt (`back_patch` in `tools/looks_from_photo.py`, Schicht im Körpershader in `web/avatar.js`): Aus dem Hinterfoto wird die Rückenpartie (30 × 30 cm um die Höhe zwischen Schulter und Hüfte, `BACK_*`) mit derselben Abbildung wie die Kachel in 256 × 256 Pixeln als eigenes Bild abgelegt (`backs.png`, ein Feld je Spieler, `looks.backPatch` im Meta mit Höhe, Feldgröße und Maß). Der Viewer legt sie auf die Rückseite des Trikots (gleiche ebene Abbildung wie die erzeugte Nummer, weicher Rand von 3 cm, nur auf der Rückseite und nur auf dem Trikot); die Kachel darunter bleibt. Szenen ohne `backPatch` bleiben wie bisher.
Ergebnis: Die Nummer hat scharfe Kanten (own-15). Offen für das Trikot: Zacken und dunkle Flecken an der Schulter, Löcher an Saum und Hüfte, weiche Trikotfläche außerhalb der Rückenpartie.

## Versuch 30: Löcher, Zacken und Flecken in Trikot und Hose

Rückmeldung: Trikot und Hose haben noch Löcher. Zacken am Saum, ein Hautstreifen an der Hüfte, Risse am Knie. Mit eingefärbten Kacheln: Sie entstehen nicht in einer Kachel, sondern überall, wo das Foto Saum, Hüfte und Knie nicht genau trifft oder der Arm etwas verdeckt, und dann Haut oder Schwarz im Stoff steht.
Jetzt (`garment_cleanup` in `tools/looks_from_photo.py`, `GARMENT_*`): Das Netz kennt je Texel, was dort getragen wird (`wear` des Viewers, jetzt mit im gebackenen Netz: `avatar_bake.py` liest das Attribut, `AvatarMesh.texel_wear` gibt es je Texel). Für Rumpf, Oberschenkel und Waden:
1. Texel von Trikot, Hose und Stutzen, die hautfarben oder viel dunkler als der Stoff sind (unter 70 % seiner Helligkeit, nur bei hellem Stoff) bekommen die Stoffarbe (Median der übrigen Texel des Stücks). Muster (Streifen, Nummer, Kragen) sind weder hautfarben noch dunkel und bleiben; Halsausschnitt und Kragen (ab 1,49 m) bleiben ganz.
2. An der Naht von Trikot und Hose (±12 cm um die Hüfte, 0,954 m) bekommen Texel, deren Farbe näher an der des anderen Stücks liegt, die Farbe ihres Stücks: der Saum wird eine gerade Linie.
3. Texel ohne Kleidung (Beine zwischen Hose und Stutzen, Knie) bekommen insgesamt die Hautfarbe des Spielers (flach: Das Foto gibt dort nur Schatten, Schmutz, Reste von Hose und Stutzen).
Mit den Ergebnissen aus Versuch 29 (scharfe Rückennummer) sind Trikot und Hose sauber, aber flacher. Offen: Der Saum hängt am Foto etwas franselig (Mischfarben in der Naht), dünne Linien in der Hose, Schuhe.

## Versuch 31: Kleidung als eigene Hüllen, ein Kit-Blatt je Mannschaft

Rückmeldung: Das Trikot sieht nicht gut aus, schwammig, Shirt nicht von der Hose getrennt, die Stutzen gehen in die Schuhe über. Wunsch: Die Bild-KI zeichnet erst ein ordentliches Bild der Kleidung, und die Figur trägt sie in der T-Haltung als eigenes Teil. Das Kit ist je Mannschaft gleich; es unterscheidet sich nur nach Größe, Rückennummer (und Rückenschrift) und dem, was ein Spieler zusätzlich trägt.
Umsetzung:
1. `tools/kit_sheet.py MANNSCHAFT ...` (Standardmodell wie `photo_ai.py`, rund 0,04 bis 0,08 USD je Mannschaft): aus den vier Ansichten eines Spielers der Mannschaft ein Blatt mit sechs Stücken auf hellem Grund: Trikot vorn/hinten (ohne Nummer), Hose vorn/hinten, Stutzen links/rechts. `--szene web/data/SZENE` legt das Blatt (mit nach außen fortgesetzten Rändern, `extend_edges`), die Rechtecke der Stücke (`boxes_of`: sechs Zusammenhänge gegen den Grund, sonst Fehler) und die Form des Trikots (`shirt_shape`: Rumpfränder, Ärmelansatz und Bündchen aus der Silhouette) in der Szene ab (`looks.kit.teams` in `meta.json`).
2. `tools/kit_player.py SZENE --quelle VIDEOSZENE`: Was ein Spieler zusätzlich trägt, aus seiner Textur gelesen: dunkles Unterhemd mit langen Ärmeln (Unterarm nicht hautfarben und dunkel), Schuhfarbe; Handschuhe nur mit Option (in der Videokachel ist die Hand wenige Pixel groß, die Erkennung unzuverlässig). Gelesen wird die Videokachel, nicht die der KI-Ansichten (die zeigt, was das Modell aus der Mannschaftsangabe macht: dieselben Ärmel für alle, erfundene Schuhe). Die Hautfarbe (`looks.skin`) schreibt `looks_from_photo.py`. Ergebnis `looks.kit.players.SPIELER` mit `baseLayer`, `gloves`, `boots`.
3. `web/garments.js`: Jedes Stück ist ein Netz am Skelett des Körpers: die Dreiecke des Körpers werden an der Nulllinie des Kleidungsfelds (Trikot, Hose, Stutzen, Schuh aus `fields` in `web/avatar.js`) sauber geschnitten (`clip`), um 0,6 bis 1,8 cm entlang der Normale abgehoben. Trikot, Hose und Stutzen bekommen die Textur des Mannschaftsblatts über die Lage in der Grundhaltung (vorn/hinten nach der Normale; Ärmel entlang ihrer Achse nach der gemessenen Trikotform); Unterhemd, Handschuhe und Schuhe sind einfarbig.
4. `web/looks.js` (`kitFor`): je Spieler ein Canvas aus dem Mannschaftsblatt mit seiner Rückennummer (hell auf dunklem, dunkel auf hellem Stoff, aus der Rückenmitte gemessen). Die Rückenschrift steht im Blatt, wenn die Mannschaft eine hat (`backText`); Namen je Spieler gibt das Video nicht her.
5. Viewer: `spieler.html?...&kit=1` (Schalter „Kit aus KI-Blatt“), zusammen mit `&tpose=1` und `&layer=skin|cloth`. Der Körper bleibt unter den Hüllen unaufgepolstert.
Ergebnis: Trikot (Nummer je Spieler), Hose, Stutzen, Schuhe und Unterhemd getrennt, ohne Zacken am Saum und ohne Übergang Stutzen/Schuh; beide Mannschaften mit je einem Blatt.
Offen: Nähte an den Körperseiten (vorn/hinten nach der Normale), Schulterkappe, Schuhe nur einfarbig (die Videokachel mischt Rasen und Sock in die Farbe), Handschuhe, Bewegung (Hüllen folgen den Hautgewichten des Körpers, keine Stoffphysik).
Nachtrag (weniger Muskeln): Im Kit-Modus (`&kit=1`) entfällt das Aufpolstern des Körpers unter Trikot und Hose (`dress(..., padded=false)`, die Hüllen tragen selbst auf); das Muskelrelief wird weiter geglättet. Der Oberkörper unter dem Trikot wirkt dadurch schmaler und glatter. Arme und Beine behalten das Relief des Modells (`SLIM` in `web/avatar-body.js`).

## Versuch 32: Kit nachgeschärft (Ärmel, Saum, Schuhe), schlankere Arme

Rückmeldung: Arme noch deutlich zu muskulös ("Fußballer, keine Bodybuilder"), Trikot und Hose verschwimmen, die Ärmel sehen nicht schön aus, die Schuhe sehen aus wie Socken. Maßnahmen:
1. **Arme und Beine** (`web/avatar-body.js`): `SLIM` für Oberarm 0,66, Unterarm 0,76, Oberschenkel 0,82, Wade 0,86. Dazu `FLATTEN`: Der Querschnitt eines Glieds wird zu einem Anteil auf den mittleren Radius seiner Höhe gezogen (zwölf Abschnitte von Gelenk zu Gelenk); Bizeps und Wade werden zu glatten Röhren, Unterarm weniger als Oberarm.
2. **Ärmel**: Rumpf- oder Ärmelabbildung gilt je Dreieck (nach der Mitte), nicht je Eckpunkt. Dreiecke an der Ärmelnaht mit beiden Abbildungen spannten Teile des Blatts auf und zogen helle Splitter über die Schulter. Der Ansatz des Ärmels im Blatt war nach dem Mittelwert der Randzeilen falsch (Ausreißer am Saum zogen ihn nach unten, `shirt_shape`); jetzt die Mitte des zusammenhängenden Bereichs (`_run_around`), dazu `sleeveW` (Ärmelhöhe am Ansatz und am Bündchen): Der Viewer hält die Abbildung innerhalb der Ärmelfläche.
3. **Vorder-/Rückseite je Dreieck**: Auch die Wahl Vorder- oder Rückseite des Blatts gilt je Dreieck (Seitennaht war ein Streifen). Der Rumpf tastet 4 % innerhalb des Rands des Blatts ab (der Rand ist ein heller Saum).
4. **Hose**: Der Umriss der Hose wird je Höhe aus dem Blatt gemessen (`shorts_shape`, `shape.shortsFront/shortsBack`); die Hülle tastet innerhalb dieses Umrisses ab und weder den Spalt zwischen den Beinen noch den Grund (heller Fleck am Bund). `remove_specks` nimmt kleine kompakte helle oder dunkle Flecken (Etikett an der Hose) aus dem Blatt; Streifen und Bündchen bleiben (Füllgrad, Seitenverhältnis).
5. **Saum**: Das Trikot steht unten 1,2 cm ab (`HEM_FLARE`) und hat eine dunklere Saumkante; die Hose ist darunter dunkler (`shade`, Eckpunktfarbe, Schatten des Überhangs). Trikot und Hose in derselben Farbe trennen sich damit.
6. **Schuhe**: Der Schuh endet 2,5 cm tiefer als das Schuhfeld (`BOOT_DROP`; der Stutzen läuft entsprechend tiefer), hat eine überstehende Sohle (`SOLE`), eine dunkle Stollenplatte und eine leicht hellere Schnürung. Die Zonen entstehen im Fragmentshader aus Höhe und Normale der Grundhaltung (Farbwechsel je Eckpunkt zackte, weil das Netz des Fußes grob ist). Sohle hell bei dunklem Schuh, dunkel bei hellem.
7. **Prüfen**: `spieler.html?...&cam=Höhe,Abstand,Richtung` richtet die Kamera auf einen Körperausschnitt (zum Prüfen von Saum, Ärmeln, Schuhen).
Offen: Zwischen Ärmel und Rumpf bleibt eine Stufe im Ton (Ärmel etwas dunkler als der Rumpf im Blatt), Schuhe nur einfarbig mit Zonen, kein Schuh je Spieler aus einem Blatt; die Arme verändern das Netz: Das Netz für die Übertragung wurde nicht neu gebacken (Hautfarbe an Armen und Händen liegt dadurch bis etwa 1 cm daneben).
