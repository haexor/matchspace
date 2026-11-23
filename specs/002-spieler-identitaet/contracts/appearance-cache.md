# Contract: Zwischenspeicher `{det}.appearance.npz`

Liegt neben den Detektionen unter `data/work/` (nicht eingecheckt). Er enthält keine Bilder, nur
Merkmalsvektoren und Größen je Erkennung (siehe [../data-model.md](../data-model.md)). Er wird nicht in
Viewer-Daten übernommen und nicht weitergegeben. Die Vektoren beschreiben Kleidung und Gestalt bei rund 55
Pixeln und dienen nur dem Verbinden innerhalb einer Szene.

Ist `stamp` veraltet (Video, Detektionen, Modell oder Format), wird neu gerechnet.
