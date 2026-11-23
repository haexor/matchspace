# ADR 0002: Eine Identität je Spieler ohne Fremddaten

**Status**: angenommen

**Datum**: 2026-11-23

**Bezug**: [specs/002-spieler-identitaet](../../specs/002-spieler-identitaet/spec.md),
[ADR 0001](0001-rueckennummern-ohne-fremddaten.md)

## Kontext

Ohne Veo zerfiel ein echter Spieler über eine 25-Sekunden-Szene in rund 2,2 eigene Spieler, und 6–7 % der
Spielerzeit gehörten der falschen Person. Die Messung zeigte, warum: Es gibt kaum echte Lücken. Meist folgt
eine Spur im Gedränge erst Spieler A und dann Spieler B, oft über die Mannschaftsgrenze hinweg.

Die Spieler sind im Video rund 55 Pixel hoch. Farben, Größe und allgemeine Bildmerkmale unterscheiden
Mitspieler bei dieser Auflösung nur schwach (AUC 0,45–0,70, research.md R1). Die Aufnahmen zeigen
Minderjährige; Bilder dürfen den Rechner nicht verlassen.

## Entscheidung

1. **Erst trennen, dann verbinden**:
   - Trägt eine Spur mindestens 1 s lang das Trikot der anderen Mannschaft, folgt sie dort nicht mehr ihrer
     Person; sie wird getrennt. Ein solcher Abschnitt wird zu einem Stück der anderen Mannschaft, außer dort
     läuft schon eine Spur dieser Mannschaft.
   - Lesen sich die Rücken vor und nach einem Kontakt zweier Mitspieler als verschiedene sichere Nummern, wird
     ebenfalls getrennt.
2. **Weg und Nummer vor Aussehen**: Stücke werden über den Laufweg verbunden (erreichbar, nahe an der
   erwarteten Lage), dieselbe sichere Rückennummer zählt stark, verschiedene verbieten. Aussehen und Größe
   entscheiden nur mit.
3. **Im Zweifel getrennt**: Verbunden wird nur, wenn der beste Kandidat deutlich günstiger ist als der
   zweitbeste (Verhältnistest), in beide Richtungen. Eine Figur, die verschwindet und neu auftaucht, ist
   besser als eine, die zur falschen Person springt.
4. **Bildmerkmale nur lokal und je Szene**: Das allgemeine Bildmodell DINOv2-small (Apache-2.0) liegt lokal
   unter `models/hf` und ist nicht eingecheckt. Gespeichert werden nur Merkmalsvektoren und Größen je
   Erkennung (`{det}.appearance.npz` unter `data/work/`), keine Bilder. Sie gelten nur innerhalb einer Szene
   und kommen nicht in die Viewer-Daten.
5. **Veo nur zum Messen**: `tools/jersey_eval.py` misst falsch zugeordnete Zeit und Wechsel gegen Veo; der
   Betrieb ohne Veo liest nichts von Veo.

## Messpunkt zur Wechselerkennung

Vor dem Einbau wurden alle Kontaktstellen beider Szenen gegen die bekannten Wechsel geprüft (research.md R3):

- Das Aussehen aus derselben Sekunde und die Laufrichtung erkennen Wechsel nicht zuverlässig. Die Spieler
  laufen beim Wechsel gemeinsam, und die Bildmerkmale unterscheiden Mitspieler kaum.
- Die Nummer greift selten, weil die Teile um einen Kontakt zu kurz für eine sichere Nummer sind.
- Die Trikotfarbe jeder Erkennung zeigt Wechsel über die Mannschaftsgrenze sicher an.

Das Aussehen bleibt deshalb nur beim Verbinden.

## Ergebnis

Gemessen gegen Veo, mit herausgerechnetem festem Tiefenversatz der Szene (rund 0,9 m):

| Szene | falsch zugeordnete Zeit | Wechsel ≥ 1 s | Identitäten je Spieler | Nummern |
|---|---|---|---|---|
| 705 | 6,9 % → 5,8 % | 9 → 7 | 2,22 → 2,22 | 7, keine falsch |
| 722 | 5,7 % → 2,9 % | 5 → 1 | 2,11 → 2,22 | 7, keine falsch |

- Die falsche Zeit sinkt deutlich, in 722 unter das Ziel von 3 %; 705 verfehlt es (Wechsel unter Mitspielern).
- Die Identitäten je Spieler sinken nicht (Ziel 1,5): Das Trennen erzeugt neue Stücke, und kaum eine Lücke
  ist eindeutig genug zum Verbinden.
- Im Viewer bleibt die Figur an 4–6 von 10 früheren Bruchstellen beim richtigen Spieler (Ziel 8). Ein Sprung
  auf eine falsche Person war in den Stichproben nicht zu sehen, meist endet die Figur.

## Folgen

- **Wechsel innerhalb einer Mannschaft** ohne lesbare Nummer bleiben unerkannt. Das ist der größte Rest.
- **Mit eigenen Kameras** wird das besser:
  - Mehrere Blickwinkel trennen Spieler, die sich aus einer Richtung verdecken (Kreuzpeilung), sodass
    Spuren im Gedränge seltener wechseln.
  - Höhere Auflösung macht Nummern häufiger lesbar und das Aussehen trennschärfer.
  - Dann lohnt es sich, das Aussehen schon beim Tracking zu nutzen statt erst danach.
- **Modell**: DINOv2-small muss einmal lokal heruntergeladen werden; fehlt es, wird ohne Aussehen getrennt und
  verbunden (mit Hinweis).
- **Rechenzeit**: rund 55 s je Szene für die Bildmerkmale (einmal, danach Zwischenspeicher).

## Verworfene Alternativen

- **Farbmittel je Spur als Hauptmerkmal**: Bei einheitlichen Trikots trennen sie Mitspieler nicht (AUC um 0,5).
- **Spezielles Wiedererkennungsmodell (OSNet o. ä.)**: auf Fußgängern mit 128–256 Pixeln trainiert, Gewichte nur
  aus Drittquellen; erst sinnvoll, wenn allgemeine Bildmerkmale bei höherer Auflösung nicht reichen.
- **Globale Zuordnung aller Stücke (Netzfluss)**: besser bei vielen gleichzeitigen Lücken, aber ohne eingebaute
  Vorsicht; bei 0–5 klaren Lücken je Szene nicht nötig.
- **Aussehen schon beim Tracking**: der grundsätzlichere Weg, aber ein Umbau von `track_players.py`; erst mit
  eigenen Kameras.
