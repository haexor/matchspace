# Contract: Kader (optional)

JSON-Datei, lokal neben den Rohdaten (z. B. unter `data/raw/…`), nicht eingecheckt.

```json
{ "own": [1, 4, 5, 7, 11, 15, 66], "opponent": [] }
```

- Schlüssel `own` und `opponent`, je eine Liste ganzer Zahlen 1–99, ohne Doppelte.
- Fehlender Schlüssel oder leere Liste: alle Nummern 1–99 möglich für diese Mannschaft.
- Andere Schlüssel, Namen oder Werte außerhalb 1–99: Abbruch mit Meldung vor der Auswertung (Prüfung an
  der Grenze, danach vertraut der Code dem Typ).
