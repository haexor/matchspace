# Contract: Zwischenspeicher der Lesungen `{det}.numbers.npz`

Liegt neben den Detektionen unter `data/work/` (nicht eingecheckt). Enthält keine Bilddaten.

| Schlüssel | Form | Bedeutung |
|-----------|------|-----------|
| `track` | str[R] | Spur-ID je Lesung |
| `frame` | int32[R] | Bild der Szene |
| `probs` | float16[R, 100] | Index 0 = keine Nummer, n = Nummer n |
| `weight` | float32[R] | Gewicht aus der Rückenhöhe |
| `stamp` | float64[4] | mtime von Video, Detektionen, Modell; Format-Version |

Ist `stamp` veraltet, wird neu gelesen. Spur-IDs beziehen sich auf die Spuren vor dem Zusammenführen.
