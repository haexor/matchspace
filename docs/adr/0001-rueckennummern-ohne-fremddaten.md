# ADR 0001: Rückennummern ohne Fremddaten

**Status**: angenommen

**Datum**: 2026-11-23

**Bezug**: [specs/001-rueckennummern](../../specs/001-rueckennummern/spec.md)

## Kontext

Die Spieler einer Szene sollen ihre echte Rückennummer tragen und über die Szene eine Identität
behalten. Bisher kamen Nummern und Identitäten von Veo. Mit eigenen Kameras gibt es keine Veo-Daten mehr.
Die Aufnahmen zeigen Minderjährige; Bilder von ihnen dürfen den Rechner nicht verlassen.

Fertige Texterkennung (TrOCR) las im Vorversuch etwa 4 von 16 Rücken richtig. Die Ziffern sind im Video nur
rund 8–20 Pixel hoch.

## Entscheidung

1. **Eigener Erkenner, lokal**: Ein kleines Faltungsnetz liest Rückenausschnitte (100 Klassen: keine Nummer,
   1–99). Es läuft auf dem eigenen Rechner (GPU oder CPU) und ruft keinen externen Dienst auf.
2. **Training ohne Fremddaten**: Trainiert wird auf künstlich gezeichneten Rücken in zufälligen Farben,
   Schriften und Verschlechterungen. Als Beispiele für „keine Nummer“ dienen außerdem Vorderansichten aus den
   eigenen Videos. Veos Nummern fließen weder ins Training noch in die Vergabe ein.
3. **Veo nur als Referenz**: Ein getrenntes Prüfwerkzeug (`tools/jersey_eval.py`) vergleicht fertige Szenen
   mit Veos Nummern. Die Auswertung importiert keinen Veo-Code im Betrieb ohne Veo.
4. **Lieber unbekannt als falsch**: Eine Nummer wird nur bei klarer, über die Zeit wiederholter Lesung
   vergeben. Zwei Spieler einer Mannschaft tragen nie gleichzeitig dieselbe Nummer.
5. **Keine Bilder, keine Namen**:
   - Ausschnitte bleiben im Speicher oder auf ausdrücklichen Wunsch unter `data/work/`.
   - Zwischenspeicher und Viewer erhalten nur Wahrscheinlichkeiten und Nummern.
   - Ein optionaler Kader enthält nur Nummern.

## Folgen

- **Mit eigenen Kameras**: Das Verfahren funktioniert ohne Anpassung, eine höhere Auflösung verbessert die
  Lesbarkeit.
- **Modell**: `models/jersey-digits.pt` muss einmal trainiert werden (wiederholbar mit festem Startwert);
  es ist nicht eingecheckt.
- **Treffsicherheit**: Sie hängt davon ab, wie gut künstliche Rücken die echten abbilden. Reicht das nicht,
  folgen in dieser Reihenfolge:
  1. Selbsttraining an sehr sicheren eigenen Lesungen;
  2. eine kleine Zahl lokal von Hand beschrifteter Rücken.

  Beides kommt ohne Veo aus.
- **Fern und vorn**: Weit entfernte oder nur von vorn gesehene Spieler bleiben ohne Nummer.

## Verworfene Alternativen

- **Allgemeine Texterkennung (TrOCR)**: zu schwach bei der Ziffergröße, groß und langsam.
- **Externe Dienste**: Bilder Minderjähriger würden den Rechner verlassen.
- **Training auf Veo-Nummern**: Der Erkenner hinge an Veo, und die Messung wäre nicht mehr unabhängig.
- **Fremde Rückennummern-Datensätze**: Lizenz unklar, andere Bildqualität, Download nötig.
