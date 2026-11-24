"""Misst die automatische Ballerkennung gegen die Referenz (tools/ball_reference.py).

Zielwerte (specs/005-beste-szenen/spec.md, SC-003): mittlerer Zeitfehler höchstens 3 Bilder, mindestens 80 % der Referenzkontakte gefunden,
höchstens 15 % der erkannten Kontakte erfunden. Die Werte werden auch ausgewiesen, wenn sie verfehlt werden.
"""
import numpy as np

TOLERANCE_FRAMES = 4      # so weit darf ein erkannter Kontakt neben dem Referenzkontakt liegen und zählt noch als derselben
SURE = 0.5                # ab dieser Sicherheit zählen erkannte Kontakte als „sicher“ (auch eigene Zahl dazu)


def match(found: list, truth: list, tolerance: int = TOLERANCE_FRAMES) -> list:
    """Paart erkannte (Bildnummern) mit Referenzkontakten: je Referenzkontakt höchstens ein erkannter, der nächste zuerst.
    Rückgabe: Liste (Index erkannt, Index Referenz)."""
    pairs = sorted(((abs(f - t), i, j) for i, f in enumerate(found) for j, t in enumerate(truth) if abs(f - t) <= tolerance))
    used_f, used_t, out = set(), set(), []
    for _, i, j in pairs:
        if i not in used_f and j not in used_t:
            used_f.add(i)
            used_t.add(j)
            out.append((i, j))
    return out


def evaluate(contacts: list, reference: dict, fps: float, tolerance: int = TOLERANCE_FRAMES) -> dict:
    """contacts: erkannte (ball_events.Contact); reference: Datei laut ball_reference. Kontakte in als „nicht erkennbar“ markierten
    Abschnitten zählen weder als gefunden noch als erfunden."""
    unseen = [tuple(u) for u in reference.get("unseen", [])]
    skip = lambda f: any(a <= f <= b for a, b in unseen)  # noqa: E731
    truth = [c for c in reference["contacts"] if not skip(c["frame"])]
    found = [c for c in contacts if not skip(c.frame)]
    pairs = match([c.frame for c in found], [t["frame"] for t in truth], tolerance)
    errors = np.array([found[i].frame - truth[j]["frame"] for i, j in pairs], float)
    kinds = [(found[i].kind, truth[j]["kind"]) for i, j in pairs if truth[j]["kind"] in ("touch", "pass", "shot")]
    kind_ok = sum(a == b for a, b in kinds)
    matched_found = {i for i, _ in pairs}
    sure = [i for i, c in enumerate(found) if c.confidence >= SURE]
    return {
        "referenz": len(truth), "erkannt": len(found), "gefunden": len(pairs),
        "gefundenAnteil": round(len(pairs) / len(truth), 3) if truth else None,
        "erfunden": len(found) - len(pairs),
        "erfundenAnteil": round((len(found) - len(pairs)) / len(found), 3) if found else None,
        "erfundenSicherAnteil": round(sum(i not in matched_found for i in sure) / len(sure), 3) if sure else None,
        "zeitfehlerMittelBilder": round(float(np.abs(errors).mean()), 2) if len(errors) else None,
        "zeitfehlerMittelSekunden": round(float(np.abs(errors).mean()) / fps, 3) if len(errors) else None,
        "zeitfehlerVorzeichenBilder": round(float(errors.mean()), 2) if len(errors) else None,
        "artRichtigAnteil": round(kind_ok / len(kinds), 3) if kinds else None,
        "verpasst": [truth[j]["frame"] for j in range(len(truth)) if j not in {j for _, j in pairs}],
    }


def meets_targets(result: dict) -> dict:
    """Gegen die Zielwerte aus SC-003; None, wo nichts zu messen war."""
    f, e, t = result["gefundenAnteil"], result["erfundenAnteil"], result["zeitfehlerMittelBilder"]
    return {"gefunden>=80%": None if f is None else f >= 0.8, "erfunden<=15%": None if e is None else e <= 0.15,
            "zeitfehler<=3Bilder": None if t is None else t <= 3}


def height_error(fitted_z: np.ndarray, reference_apex: float) -> float:
    """Fehler der Scheitelhöhe eines bestätigten Flugs in Metern (positiv: zu hoch geschätzt)."""
    return float(np.nanmax(fitted_z) - reference_apex)
