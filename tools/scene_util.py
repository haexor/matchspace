"""Reine Array-Hilfen der Szenenrechnung (tools/veo_scene.py): Median, Abschnitte, Lücken halten, Umrechnen der Bildrate.

Ohne Datei-, Video- oder Netzzugriff. Tests: tests/test_scene_util.py.
"""
import numpy as np


def running_median(values, window):
    half = window // 2
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.array([np.nanmedian(values[max(0, i - half):i + half + 1]) for i in range(len(values))])


def segments(mask, minimum):
    """Zusammenhängende Abschnitte (Anfang, Ende ausschließlich), in denen mask wahr ist und die mindestens minimum lang sind."""
    start = None
    for i, ok in enumerate(list(mask) + [False]):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start >= minimum:
                yield start, i
            start = None


def hold(values, limit):
    """Füllt Lücken (NaN) entlang der Zeit mit dem nächstgelegenen gültigen Bild, höchstens limit Bilder weit."""
    out = values.copy()
    good = np.flatnonzero(~np.isnan(values.reshape(len(values), -1)[:, 0]))
    if not len(good):
        return out
    for i in np.flatnonzero(np.isnan(values.reshape(len(values), -1)[:, 0])):
        j = good[np.argmin(np.abs(good - i))]
        if abs(j - i) <= limit:
            out[i] = values[j]
    return out


def resample(values, n_out, ratio):
    """Lineares Umrechnen einer Bildfolge (n, ...) auf n_out Bilder; Bild i der Ausgabe liegt bei i * ratio. NaN bleibt NaN."""
    src = np.arange(n_out) * ratio
    a = np.minimum(src.astype(int), len(values) - 1)
    b = np.minimum(a + 1, len(values) - 1)
    w = (src - a).reshape(-1, *([1] * (values.ndim - 1)))
    return values[a] + (values[b] - values[a]) * w


def resample_keypoints(kp, lens, n_out, ratio):
    """Gelenkpunkte (n, 17, 3) und Linse (n,) auf n_out Bilder umrechnen; Bild i der Ausgabe liegt bei i * ratio.

    Zwischen zwei erkannten Bildern derselben Linse wird gemittelt, sonst das nähere genommen."""
    src = np.arange(n_out) * ratio
    a = np.minimum(src.astype(int), len(kp) - 1)
    b = np.minimum(a + 1, len(kp) - 1)
    w = src - a
    ok_a, ok_b = ~np.isnan(kp[a, 0, 0]) & ~np.isnan(lens[a]), ~np.isnan(kp[b, 0, 0]) & ~np.isnan(lens[b])
    near = np.where((w < 0.5) | ~ok_b, a, b)
    out, lens_out = kp[near].copy(), lens[near].copy()
    both = ok_a & ok_b & (lens[a] == lens[b])
    mixed = kp[a] * (1 - w)[:, None, None] + kp[b] * w[:, None, None]
    mixed[:, :, 2] = np.minimum(kp[a, :, 2], kp[b, :, 2])
    out[both] = mixed[both]
    none = ~(ok_a | ok_b) | np.isnan(out[:, 0, 0])
    out[none], lens_out[none] = np.nan, np.nan
    return out, lens_out
