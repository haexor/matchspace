# Contract: Zwischenspeicher der Lesungen `{det}.numbers.npz`

Liegt neben den Detektionen unter `data/work/` (nicht eingecheckt). Enthält keine Bilddaten.

| Schlüssel | Form | Bedeutung |
|-----------|------|-----------|
| `frame` | int32[R] | Bild der Szene |
| `lens` | int8[R] | Linse (0 links, 1 rechts) |
| `box` | int32[R] | Nummer der Box in der Linse (wie in den Detektionen) |
| `height` | float32[R] | Schulter bis Hüfte in Pixeln |
| `probs` | float16[R, 100] | Index 0 = keine Nummer, n = Nummer n |
| `stamp` | float64[4] | mtime von Video, Detektionen, Modell; Format-Version |

Ist `stamp` veraltet, wird neu gelesen. Gespeichert wird je Erkennung, nicht je Spur: Den Spuren werden die
Lesungen erst beim Abstimmen über Bild, Linse und Box zugeordnet; das Gewicht folgt aus `height`.
