"""Künstliche Rückenausschnitte zum Trainieren des Nummernlesers (tools/jersey_reader.py).

Gezeichnet wird ein Trikotrücken in zufälligen Farben mit Nummer (1–99) oder ohne (Klasse 0), danach so
verschlechtert wie im Videostrom eines Spielfelds: Spieler sind nur rund 55 Pixel hoch, der Rücken 18–40.
Keine Fremddaten, keine Bilder echter Spieler: Das Ergebnis hängt weder von Veo noch von bestimmten
Trikotfarben ab.

Schriften kommen aus dem System (fc-match), damit kein Pfad im Code steht.
"""
import functools
import string
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CROP_H, CROP_W = 40, 32       # Ausschnitt hochkant: Schulterlinie bis Hüfte
CLASSES = 100                 # 0 = keine Nummer, n = Nummer n
NO_NUMBER = 0
SCALE = 4                     # gezeichnet wird in vierfacher Größe, dann verkleinert
FONT_NAMES = ("DejaVu Sans:bold", "DejaVu Sans:condensed:bold", "Liberation Sans:bold", "Noto Sans:bold",
              "Open Sans:condensed:bold", "Open Sans:condensed:extrabold")
SMALL_HEIGHT = (20, 44)       # Höhe des Ausschnitts im Video in Pixeln: 1,2 × Schulter bis Hüfte (gelesen ab 18 px)
NONE_SHARE = 0.2              # Anteil der Beispiele ohne Nummer in einem Stapel
MIN_VISIBLE = 0.8             # weniger sichtbare Nummer (verdeckt, abgeschnitten) gilt als „keine Nummer“: nicht raten
STRETCH = (0.45, 1.1)         # Breite der Ziffern: Trikotnummern sind oft schmal und hoch


class FontNotFound(RuntimeError):
    """Keine passende fette, serifenlose Schrift im System."""


@functools.cache
def find_fonts() -> tuple[str, ...]:
    """Dateien der Schriften aus FONT_NAMES, die fc-match wirklich findet (nicht nur einen Ersatz)."""
    found = []
    for name in FONT_NAMES:
        try:
            res = subprocess.run(["fc-match", "-f", "%{family[0]}|%{file}", name], capture_output=True, text=True,
                                 check=True, timeout=10)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
            raise FontNotFound(f"fc-match nicht nutzbar: {err}") from err
        family, _, path = res.stdout.partition("|")
        if family and family.lower() in name.lower() and path not in found:
            found.append(path)
    if not found:
        raise FontNotFound(f"keine der Schriften {FONT_NAMES} installiert")
    return tuple(found)


def normalise(gray: np.ndarray) -> np.ndarray:
    """Kontrast je Ausschnitt strecken (2. bis 98. Perzentil auf 0–255): macht den Leser farbunabhängig."""
    lo, hi = np.percentile(gray, (2, 98))
    if hi - lo < 1:
        return np.zeros_like(gray, dtype=np.uint8)
    return np.clip((gray.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)


def _colour(rng: np.random.Generator) -> np.ndarray:
    hsv = np.uint8([[[rng.integers(0, 180), rng.integers(0, 256), rng.integers(40, 256)]]])
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0].astype(np.float32)


def _luma(rgb: np.ndarray) -> float:
    return float(rgb @ np.array([0.299, 0.587, 0.114]))


def _kit(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Trikot- und Schriftfarbe mit deutlichem Helligkeitsunterschied; meist helle Schrift auf dunklerem Stoff."""
    while True:
        shirt = _colour(rng)
        ink = np.float32([245, 245, 245]) - rng.uniform(0, 40, 3) if rng.random() < 0.6 else _colour(rng)
        if rng.random() < 0.2:
            shirt, ink = ink, shirt
        if abs(_luma(shirt) - _luma(ink)) >= 60:
            return shirt, ink


def _text_layer(text: str, font_path: str, height_px: float, stretch: float, stroke: int,
                size: tuple[int, int], centre: tuple[float, float]) -> np.ndarray:
    """Deckkraft (0–1) eines Textes, dessen Ziffern height_px hoch sind, um centre (x, y) zentriert."""
    font = ImageFont.truetype(font_path, max(int(height_px * 1.35), 4))
    box = font.getbbox(text, stroke_width=stroke)
    tw, th = box[2] - box[0], box[3] - box[1]
    img = Image.new("L", (tw + 4 * stroke + 4, th + 4 * stroke + 4), 0)
    ImageDraw.Draw(img).text((2 * stroke + 2 - box[0], 2 * stroke + 2 - box[1]), text, font=font, fill=255,
                             stroke_width=stroke, stroke_fill=255)
    img = img.resize((max(int(img.width * stretch * height_px / max(th, 1)), 1),
                      max(int(img.height * height_px / max(th, 1)), 1)), Image.BILINEAR)
    layer = np.zeros(size[::-1], np.float32)
    x0, y0 = int(centre[0] - img.width / 2), int(centre[1] - img.height / 2)
    src = np.asarray(img, np.float32) / 255.0
    xa, ya = max(x0, 0), max(y0, 0)
    xb, yb = min(x0 + img.width, size[0]), min(y0 + img.height, size[1])
    if xb > xa and yb > ya:
        layer[ya:yb, xa:xb] = src[ya - y0:yb - y0, xa - x0:xb - x0]
    return layer


def _one_with_flag(font: ImageFont.FreeTypeFont, stroke: int, flag: float) -> Image.Image:
    """Eine „1“ wie auf vielen Trikots: senkrechter Strich mit großem schrägem Anstrich, ohne Fuß. flag: Länge des
    Anstrichs als Anteil der Höhe. Die Systemschriften zeichnen die 1 anders; ohne diese Form liest das Netz
    eine Trikot-1 als 7."""
    box = font.getbbox("1", stroke_width=stroke)
    h = box[3] - box[1]
    stem = max(int(h * 0.16) + stroke, 2)
    lead = int(h * flag)
    img = Image.new("L", (lead + stem + 4, h + 2), 0)
    draw = ImageDraw.Draw(img)
    x = lead + 2
    draw.rectangle((x, 1, x + stem, h), fill=255)
    draw.polygon([(x + stem, 1), (x, 1), (2, 1 + int(lead * 0.7)), (2, 1 + int(lead * 0.7) + stem), (x, 1 + stem)], fill=255)
    return img


def _number_layer(number: int, font_path: str, digit_h: float, stretch: float, stroke: int, gap: float,
                  size: tuple[int, int], centre: tuple[float, float], flag: float = 0.0) -> np.ndarray:
    """Deckkraft einer Nummer, Ziffer für Ziffer gesetzt: Abstand gap (Anteil der Ziffernhöhe) frei wählbar;
    flag > 0 zeichnet jede 1 als Trikot-1 mit Anstrich dieser Länge."""
    font = ImageFont.truetype(font_path, max(int(digit_h * 1.35), 4))
    glyphs = []
    for ch in str(number):
        box = font.getbbox(ch, stroke_width=stroke)
        img = Image.new("L", (box[2] - box[0] + 2, box[3] - box[1] + 2), 0)
        ImageDraw.Draw(img).text((1 - box[0], 1 - box[1]), ch, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
        if ch == "1" and flag > 0:
            img = _one_with_flag(font, stroke, flag)
        f = digit_h / max(img.height, 1)
        glyphs.append(np.asarray(img.resize((max(int(img.width * f * stretch), 1), max(int(digit_h), 1)), Image.BILINEAR),
                                 np.float32) / 255.0)
    space = int(gap * digit_h)
    width = sum(g.shape[1] for g in glyphs) + space * (len(glyphs) - 1)
    strip = np.zeros((glyphs[0].shape[0], max(width, 1)), np.float32)
    x = 0
    for g in glyphs:
        strip[:, x:x + g.shape[1]] = np.maximum(strip[:, x:x + g.shape[1]], g[:, :max(min(g.shape[1], strip.shape[1] - x), 0)])
        x += g.shape[1] + space
    layer = np.zeros(size[::-1], np.float32)
    x0, y0 = int(centre[0] - strip.shape[1] / 2), int(centre[1] - strip.shape[0] / 2)
    xa, ya = max(x0, 0), max(y0, 0)
    xb, yb = min(x0 + strip.shape[1], size[0]), min(y0 + strip.shape[0], size[1])
    if xb > xa and yb > ya:
        layer[ya:yb, xa:xb] = strip[ya - y0:yb - y0, xa - x0:xb - x0]
    return layer


def _blend(img: np.ndarray, alpha: np.ndarray, colour: np.ndarray) -> np.ndarray:
    return img * (1 - alpha[..., None]) + colour * alpha[..., None]


def _render(number: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Trikotrücken in SCALE-facher Größe (RGB, float32), dazu Deckkraft der Nummer und Maske der Verdeckung."""
    H, W = CROP_H * SCALE, CROP_W * SCALE
    fonts = find_fonts()
    shirt, ink = _kit(rng)
    outside = np.float32([rng.uniform(30, 80), rng.uniform(80, 150), rng.uniform(20, 70)])   # meist Rasen
    if rng.random() < 0.3:
        outside = _colour(rng)
    img = np.empty((H, W, 3), np.float32)
    img[:] = outside
    # Rumpf als Trapez, Arme an den Seiten (Haut, Ärmel oder Trikot)
    top_w, bottom_w = rng.uniform(0.75, 1.0) * W, rng.uniform(0.6, 0.85) * W
    cx = W / 2 + rng.uniform(-0.06, 0.06) * W
    body = np.zeros((H, W), np.uint8)
    poly = np.int32([[cx - top_w / 2, 0], [cx + top_w / 2, 0], [cx + bottom_w / 2, H], [cx - bottom_w / 2, H]])
    cv2.fillPoly(body, [poly], 1)
    img[body > 0] = shirt
    for side in (-1, 1):
        if rng.random() < 0.6:
            arm = shirt if rng.random() < 0.4 else np.float32([rng.uniform(120, 230), rng.uniform(80, 180), rng.uniform(60, 150)])
            x = cx + side * (top_w / 2 + rng.uniform(-0.05, 0.08) * W)
            cv2.line(img, (int(x), int(rng.uniform(0, 0.2) * H)), (int(x + side * rng.uniform(-0.1, 0.1) * W), int(rng.uniform(0.5, 1.0) * H)),
                     arm.tolist(), int(rng.uniform(0.08, 0.16) * W))
    # Aufdruck über der Nummer (Verein, Sponsor) oder Brust-Wappen
    if rng.random() < 0.6:
        word = "".join(rng.choice(list(string.ascii_uppercase + "  "), rng.integers(3, 9)))
        layer = _text_layer(word.strip() or "SV", str(rng.choice(fonts)), rng.uniform(0.06, 0.11) * H,
                            rng.uniform(0.7, 1.1), 0, (W, H), (cx, rng.uniform(0.17, 0.3) * H))
        img = _blend(img, layer, ink)
    digits = np.zeros((H, W), np.float32)
    if number != NO_NUMBER:
        digit_h = rng.uniform(0.33, 0.5) * H
        digits = _number_layer(number, str(rng.choice(fonts)), digit_h, rng.uniform(*STRETCH),
                               int(rng.integers(0, 3)) * SCALE // 2, rng.uniform(-0.04, 0.2), (W, H),
                               (cx + rng.uniform(-0.06, 0.06) * W, rng.uniform(0.5, 0.66) * H),
                               rng.uniform(0.2, 0.5) if rng.random() < 0.5 else 0.0)
        img = _blend(img, digits * rng.uniform(0.75, 1.0), ink)
    elif rng.random() < 0.3:   # Vorderseite: kleines Wappen links oben
        cv2.circle(img, (int(cx + rng.uniform(0.1, 0.25) * W), int(rng.uniform(0.2, 0.35) * H)),
                   int(rng.uniform(0.05, 0.1) * W), ink.tolist(), -1)
    # Stofffalten: Helligkeitswellen auf dem Trikot
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    k = rng.uniform(0.01, 0.05) * 4 / SCALE
    folds = 1 + rng.uniform(0, 0.15) * np.sin(k * (xx * np.cos(a := rng.uniform(0, np.pi)) + yy * np.sin(a)) + rng.uniform(0, 6.3))
    img *= folds[..., None] * rng.uniform(0.7, 1.15)
    # Verdeckung durch einen Arm oder Mitspieler
    cover = np.zeros((H, W), np.float32)
    if rng.random() < 0.25:
        colour = _colour(rng) if rng.random() < 0.5 else np.float32([rng.uniform(120, 230), rng.uniform(80, 180), rng.uniform(60, 150)])
        p0 = (int(rng.uniform(0, W)), int(rng.uniform(0, H)))
        p1 = (int(rng.uniform(0, W)), int(rng.uniform(0, H)))
        thick = int(rng.uniform(0.08, 0.2) * W)
        cv2.line(img, p0, p1, colour.tolist(), thick)
        cv2.line(cover, p0, p1, 1.0, thick)
    return np.clip(img, 0, 255), digits, cover


def _jitter(img: np.ndarray, rng: np.random.Generator, visible: np.ndarray) -> tuple[np.ndarray, float]:
    """Schräglage, Drehung und ungenaue Gelenkpunkte: leicht verzerrter, verschobener Bildausschnitt. Gibt dazu
    zurück, wie viel der sichtbaren Nummer (visible) im Ausschnitt bleibt."""
    H, W = img.shape[:2]
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    turn = rng.uniform(-0.25, 0.25)          # Drehung des Körpers: eine Seite schmaler
    shift = rng.uniform(-0.1, 0.1, 2) * (W, H)
    scale = rng.uniform(0.85, 1.15)
    tilt = np.deg2rad(rng.uniform(-10, 10))
    c, s = np.cos(tilt), np.sin(tilt)
    dst = []
    for x, y in src - (W / 2, H / 2):
        x *= scale * (1 + turn * (1 if x > 0 else -1) * (y / H + 0.5) * 0.3)
        y *= scale
        dst.append((c * x - s * y + W / 2 + shift[0], s * x + c * y + H / 2 + shift[1]))
    m = cv2.getPerspectiveTransform(src, np.float32(dst))
    total = float(visible.sum())
    kept = float(cv2.warpPerspective(visible, m, (W, H), borderMode=cv2.BORDER_CONSTANT).sum()) / max(abs(np.linalg.det(m[:2, :2])), 1e-6)
    return cv2.warpPerspective(img, m, (W, H), borderMode=cv2.BORDER_REFLECT), kept / total if total > 0 else 0.0


def _degrade(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Auf Videogröße verkleinern, Unschärfe, Rauschen, Kompression; dann wie ein echter Ausschnitt vergrößern."""
    h = int(rng.integers(*SMALL_HEIGHT))
    w = max(int(round(h * CROP_W / CROP_H)), 4)
    small = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_AREA)
    if rng.random() < 0.25:   # Bewegungsunschärfe
        n = int(rng.integers(2, 5))
        kernel = np.zeros((n, n), np.float32)
        kernel[n // 2] = 1.0 / n
        kernel = cv2.warpAffine(kernel, cv2.getRotationMatrix2D((n / 2 - 0.5, n / 2 - 0.5), rng.uniform(0, 180), 1), (n, n))
        small = cv2.filter2D(small, -1, kernel / max(kernel.sum(), 1e-6))
    small = cv2.resize(small, (w, h), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), rng.uniform(0.3, 0.9))
    small = np.clip(small + rng.normal(0, rng.uniform(2, 10), small.shape), 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", small[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(25, 80))])
    small = cv2.imdecode(enc, cv2.IMREAD_COLOR)[..., ::-1] if ok else small
    gray = cv2.cvtColor(np.ascontiguousarray(small), cv2.COLOR_RGB2GRAY)
    return cv2.resize(gray, (CROP_W, CROP_H), interpolation=cv2.INTER_LINEAR)


def make_labelled(number: int, rng: np.random.Generator) -> tuple[np.ndarray, int]:
    """Ein künstlicher Ausschnitt uint8[CROP_H, CROP_W] mit Nummer number (1–99) oder ohne (NO_NUMBER) und seine
    Klasse: Ist weniger als MIN_VISIBLE der Nummer zu sehen (verdeckt, abgeschnitten), ist sie NO_NUMBER."""
    if not 0 <= number < CLASSES:
        raise ValueError(f"Nummer {number} außerhalb 0–{CLASSES - 1}")
    img, digits, cover = _render(number, rng)
    out, share = _jitter(img, rng, digits * (1 - cover))
    if number != NO_NUMBER:
        share *= float((digits * (1 - cover)).sum()) / max(float(digits.sum()), 1e-6)
    label = number if number != NO_NUMBER and share >= MIN_VISIBLE else NO_NUMBER
    return normalise(_degrade(out, rng)), label


def make_sample(number: int, rng: np.random.Generator) -> np.ndarray:
    """Nur das Bild aus make_labelled."""
    return make_labelled(number, rng)[0]


def batch(n: int, rng: np.random.Generator, none_share: float = NONE_SHARE) -> tuple[np.ndarray, np.ndarray]:
    """n Ausschnitte mit Klassen; mindestens einer ohne Nummer."""
    y = rng.integers(1, CLASSES, n)
    y[rng.random(n) < none_share] = NO_NUMBER
    y[0] = NO_NUMBER
    pairs = [make_labelled(int(k), rng) for k in y]
    return np.stack([p[0] for p in pairs]), np.array([p[1] for p in pairs], np.int64)
