# Spieler steuern (Vorschau)

`web/spielen.html?match=SZENE&player=own-6` zeigt einen Spieler mit seinem Outfit auf dem Platz der Szene und lässt ihn selbst laufen. Die T-Haltung mit allen Schichten (Körper, Kleidung) steht in `web/spieler.html?...&tpose=1&kit=1` (Link „Steuern“ führt hierher, „T-Haltung ansehen“ zurück).

## Bedienung

| Taste | Wirkung |
|---|---|
| W A S D (oder Pfeile) | laufen, relativ zur Kamera (W läuft vom Betrachter weg) |
| Umschalt | sprinten (kostet Atem, die Leiste links unten zeigt ihn) |
| Leertaste | springen |
| E | schießen (Ball in Blickrichtung, wenn er in Reichweite liegt) |
| Maus ziehen, Rad | Kamera drehen, Abstand |

Der Ball rollt, bremst und wird beim Laufen vor dem Fuß mitgenommen; wie eng, hängt vom Dribbling des Spielers ab.

## Aufbau

- `web/profile.js`: FIFA-artige Werte je Spieler (0 bis 99: Tempo, Beschleunigung, Wendigkeit, Sprungkraft, Ausdauer, Dribbling, Zweikampf, Schuss, Passspiel) und die Umrechnung in körperliche Größen (Höchsttempo, Beschleunigung, Drehrate, Sprunghöhe, Sprintdauer, Schussgeschwindigkeit, Ballbindung). Die Umrechnung ist stetig und monoton. Heute haben alle dieselben Werte (70, das sind etwa 26 km/h Höchsttempo); später stehen sie je Spieler in der Szene (`entities[].profile.ratings` in `meta.json`) und jeder bewegt sich anders. Zweikampf und Passspiel sind angelegt, aber noch ohne Wirkung (es gibt noch keine Gegner und keine Mitspieler zum Steuern).
- `web/movement.js`: reine Rechnung ohne Grafik: Beschleunigen und Bremsen, Drehen, Sprint mit Ausdauer, Sprung mit Schwerkraft, einfacher Ball.
- `web/runner.js`: Laufanimation: aus Schrittphase, Tempo und Luftanteil entstehen die Gelenkpunkte, die der Avatar sonst aus den Körperposen der Szene bekommt (`avatar.setPose`). Das Becken sitzt so, dass der tiefste Fußpunkt den Boden berührt; Rumpfneigung, Armschwung gegen die Beine und Kniebeugung wachsen mit dem Tempo.
- `web/spielen.js`: Platz (`web/stadium.js`), Kamera, Eingabe, Anzeige.

## Spielbewertung

`tools/player_rating.py SZENE [--schreiben]` misst je Spieler aus den Bahnen: Laufstrecke, Höchsttempo (98. Perzentil des geglätteten Tempos), Sprints, größte Beschleunigung, Ballkontakte (`ballContacts`). Daraus:

- **Profilwerte**, soweit messbar: Tempo (Höchsttempo, gleiche Skala wie `physicsOf`), Beschleunigung, Ausdauer (Laufstrecke je Minute im Vergleich zu den anderen). Dribbling, Zweikampf, Schuss und Passspiel lassen sich noch nicht messen und bleiben bei der Voreinstellung; sie werden nicht geraten.
- **Spielbewertung 1 bis 10**: das gewichtete Mittel der Abstände zum Durchschnitt aller Spieler des Spiels (in Standardabweichungen) über Laufstrecke je Minute, Höchsttempo, Sprints und Ballkontakte; 6 ist Durchschnitt. Sie sagt also, wie ein Spieler im Vergleich zum Rest gespielt hat.

Beides braucht Zeit und Vergleichsspieler (`MIN_SECONDS` = 30 s gesehene Zeit, `MIN_PEERS` = 4). Die Szenen heute sind 10 bis 25 s lang: Dort entstehen nur die Messwerte (Strecke, Höchsttempo, Sprints), keine Werte und keine Bewertung. Gemacht ist es für ganze Spiele.

## Ziel (weit voraus)

Ein richtiges Fußballspiel: Spieler steuern ihren Charakter selbst oder lassen ihn selbstständig spielen, und vergangene Spiele lassen sich nachspielen, mit den Werten und Bewertungen, die aus den echten Spielen gemessen wurden. Bausteine dafür stehen schon: gemessene Bahnen (`tracks.bin`), Körperposen, Kleidung (`web/garments.js`), Bewegung und Profil (diese Seite). Es fehlen unter anderem: mehrere gleichzeitig gesteuerte oder von einer KI gesteuerte Spieler, Zweikämpfe, Pässe, Tore und Regeln, Spielstand, und das Nachspielen einer Szene mit einem eigenen Spieler darin.

## Grenzen

- Die Laufanimation ist berechnet, nicht aus echten Bewegungen: Sie sieht nach Laufen und Sprung aus, aber nicht nach der Eigenart eines Spielers.
- Kein Zusammenstoß mit anderen Spielern, keine Regeln, kein Aus: Der Spieler läuft bis kurz hinter die Seitenlinien (4 m), der Ball prallt dort ab.
- Keine automatischen Tests für die Seite (das Repository hat keine für `web/`); die Rechnung der Bewertung ist in `tests/test_player_rating.py` getestet.
