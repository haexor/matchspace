# ADR 0003: Eigene Referenz statt Veo

**Status**: angenommen

**Datum**: 2026-11-23

**Bezug**: [specs/003-eigene-referenz](../../specs/003-eigene-referenz/spec.md),
[ADR 0001](0001-rueckennummern-ohne-fremddaten.md), [ADR 0002](0002-identitaet-ohne-fremddaten.md)

## Kontext

Bis Feature 002 war Veo die Wahrheit für jede Messung. Daran gab es drei Probleme:
- Veo ist nicht immer zuverlässig.
- Veo kennt nur Spieler, denen es selbst eine Nummer gegeben hat.
- Die Messung musste einen Tiefenversatz von rund 0,9 m zwischen Szene und Veo pauschal herausrechnen, ohne zu
  wissen, wer recht hat.

Außerdem hing der Betrieb ohne Veo noch am Veo-Basisspiel (Spielabschnitte, Uhr, Mannschaften) und startete die
Kamerakalibrierung bei Veos Kameralage. Mit eigenen Kameras gibt es keine Veo-Daten.

## Entscheidung

1. **Wahrheit aus eigenen Antworten**:
   - Die Referenz ist die Zuordnung der Auswertung, korrigiert an strittigen Stellen. Strittig sind Verdeckungen,
     Spurenden mitten auf dem Platz, Trennungen und Verbindungen, Nummern und Widersprüche zu Veo.
   - Der Nutzer entscheidet nur diese Stellen, in einem lokalen Markierwerkzeug mit kurzen Videoausschnitten.
   - Je Szene kommen 5 zufällige Kontrollstellen dazu. Sie schätzen, wie viele Fehler außerhalb der strittigen
     Stellen unentdeckt bleiben.
2. **Bewusster Tausch**:
   - Der Nutzer will nur strittige Stellen nacharbeiten. An unauffälligen Stellen folgt die Referenz deshalb der
     eigenen Auswertung.
   - Der Bericht nennt dazu die Abdeckung (offen, unklar, verwaist) und die Schätzung aus den Kontrollstellen.
3. **Messen je Erkennung**: Identität wird an Erkennungen gemessen, nicht an der Lage der Szene. Der pauschale
   Tiefenversatz entfällt.
4. **Lage aus der Platzgeometrie**:
   - Steht ein Fuß auf einer Platzlinie, ist die wahre Lage bekannt. Daran wird jede Lagequelle geprüft.
   - Ergebnis für 705 und 722: Die fertige Szene liegt an den mittleren Linien auf 0,1–0,4 m genau. Boxunterkante
     und Veo setzen die Spieler rund 1 m zu nah an die Kamera.
   - Der Versatz aus Feature 002 war also überwiegend Veos Fehler.
5. **Veo nur als zweite Meinung**:
   - Veo erscheint nur mit `--veo`, als zweite Spalte und als Liste von Widersprüchen.
   - Ohne `--veo` wird kein Veo-Code geladen.
6. **Betrieb ganz ohne Veo**:
   - Eine eigene Spielbeschreibung (`spiel.json`, ohne Personennamen) ersetzt das Veo-Basisspiel.
   - Die Kalibrierung startet aus einem Raster möglicher Kameralagen statt bei Veos Kameralage oder Veos Ecken.
   - Ein Prüflauf mit Audit-Hook weist nach, dass keine Veo-Datei geöffnet wird.
7. **Linsendaten bleiben Eingabe**: Brennweite, Verzeichnung und Lage der Linsen sind Eigenschaften der Kamera und
   kommen mit der Aufnahme. Eigene Kameras brauchen dafür eine eigene Linsenkalibrierung (eigenes Feature).
8. **Datenschutz**:
   - Das Markierwerkzeug läuft nur an `127.0.0.1` und lädt nichts von außen.
   - Die Referenz enthält nur Bild, Linse, Box, Rolle, neutrale Kennung, Nummer und Antwort, keine Bilder und keine
     Namen.

## Folgen

- Messwerte aus Feature 001 und 002, die gegen Veo bestimmt wurden, werden gegen die eigene Referenz neu
  eingeordnet (research.md).
- Nach jeder neuen Auswertung legt `review_spots.py` die Stellen neu an. Entschiedene Stellen werden über ihre
  Boxen wiedergefunden; nur neue sind offen.
- Rund 60 Stellen je 25-Sekunden-Szene. Das ist knapp für 10 Minuten; die Schwelle der Verdeckung ist einstellbar.
- Ergebnisse mit derselben Kamera sind ohne Veo bitgleich zum Lauf mit Veo-Basisspiel.

## Verworfene Alternativen

- **Jede Stichprobe markieren** (alle 2 s jede Person): verlässlicher, aber vom Nutzer als zu viel Handarbeit
  abgelehnt.
- **Fertige Markierwerkzeuge** (CVAT, Label Studio): groß, eigene Datenhaltung, für 60 Fragen je Szene überdimensioniert.
- **Lage gegen Veo prüfen**: Veo ist selbst um rund 1 m versetzt; die Platzgeometrie ist der unabhängige Maßstab.
- **Veos Linsendaten ersetzen**: erst mit eigenen Kameras sinnvoll.
