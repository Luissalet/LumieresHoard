"""Build Lumiere's icon from the family dragon.

    python scripts/make_icon.py [--family <Icons folder>] [--src path/to/dragon-src.png] [--preview out.png]

Lumiere's Hoard is a local video editor; its icon is the family dragon in orchid with a gold clapperboard.

Method (the family recipe):
1. the family's finished icons are the source (the default when the shared Icons folder is next to this repository,
   or with --family <Icons folder>): the dragon is the same in all of them and only the glyph in the middle changes,
   so each icon's gold glyph (and its dark outline) is masked and every pixel takes the dragon from the siblings whose
   glyph does not cover it (brightness matched between icons, each weighted by its distance to its own glyph so the
   seams fade). No pixel of the dragon is guessed, so there are no inpainting smudges where the body passes behind the
   glyph. A single sibling still works with --src <sibling>/app-icon.png (glyph area inpainted, may smudge);
2. the dragon is recoloured by luminance with a dark-to-light orchid ramp (#4A0A52 to #F57AF8, a colour no sibling
   uses); the eye keeps a light colour; the background becomes the family's flat dark navy (the black rounded-square
   corners disappear);
3. a gold vector clapperboard (film slate, about 380 px wide) is composed at (627, 768): a slate body with a play
   triangle cut out of it and a striped bar on top, plus the hinged clapper arm opened about 20 degrees with diagonal
   stripes, with the family's vertical gold gradient and dark outline. It is drawn at 4x and downsampled.

Outputs: app-icon.png (1254^2), client/public/icon-512.png, icon-192.png, favicon.ico (16-256; also copied to
lumiere_hoard/static when that folder exists) and dist-icons/Lumieres hoard.png (for the shared Icons folder).
Needs: pillow, numpy, opencv-python-headless (requirements-icon.txt).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SIZE = 1254
BACKGROUND = (1, 11, 27)  # the family's flat dark navy
RAMP_DARK = np.array([0x4A, 0x0A, 0x52], dtype=np.float32)
RAMP_LIGHT = np.array([0xF5, 0x7A, 0xF8], dtype=np.float32)
EYE_COLOR = np.array([0xFF, 0xEE, 0xFD], dtype=np.float32)
GOLD_TOP = (0xF8, 0xD8, 0x8C)
GOLD_BOTTOM = (0xE0, 0xA2, 0x42)
OUTLINE = (6, 10, 24)
GLYPH_CENTER = (627, 768)
GLYPH_SIZE = 400


FAMILY_MIN_ICONS = 5


def family_icons(folder: Path) -> list[Path]:
    """The shared Icons folder's finished family icons other than this app's own: same size, the family's flat
    navy in the corner (not a black rounded square) and a dragon that is not gold, so its glyph can be told apart."""
    found = []
    for path in sorted(folder.glob("*.png")):
        if path.name.lower().startswith("lumi"):
            continue
        with Image.open(path) as img:
            if img.size != (SIZE, SIZE):
                continue
            rgb = np.array(img.convert("RGB"))
        corner = rgb[:60, :60].reshape(-1, 3).mean(axis=0)
        if not (corner[2] > 15 and corner.max() < 45):
            continue
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        ring = hsv[150:350, 250:1000]  # the head and the upper body, well away from any glyph
        body = ring[ring[..., 2] > 100]
        if body.size == 0 or 10 <= float(np.median(body[:, 0])) <= 40:
            continue
        found.append(path)
    return found


def default_family() -> Path | None:
    for folder in (ROOT.parent / "Icons", ROOT.parent / "icons"):
        if folder.is_dir() and len(family_icons(folder)) >= FAMILY_MIN_ICONS:
            return folder
    return None


def default_source() -> Path | None:
    for candidate in (ROOT.parent / "Icons" / "dragon-src.png", ROOT.parent / "icons" / "dragon-src.png", Path.home() / "icons" / "dragon-src.png",
                      ):
        if candidate.is_file():
            return candidate
    for sibling in sorted(ROOT.parent.glob("*/app-icon.png")):
        if sibling.parent != ROOT:
            return sibling
    return None


# ---------------------------------------------------------------------------
# dragon
# ---------------------------------------------------------------------------

def button_mask(rgb: np.ndarray) -> np.ndarray:
    """The yellow button, its triangle and the dark halo around it (uint8 0/255)."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    yellow = cv2.inRange(hsv, (12, 90, 110), (40, 255, 255))
    yellow = cv2.morphologyEx(yellow, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(yellow, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(yellow)
    if contours:
        biggest = max(contours, key=cv2.contourArea)
        cv2.drawContours(filled, [biggest], -1, 255, thickness=cv2.FILLED)  # includes the triangle
    halo = cv2.dilate(filled, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (29, 29)))
    return halo


def eye_mask(rgb: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    cyan = cv2.inRange(hsv, (80, 120, 120), (105, 255, 255))
    cyan = cv2.morphologyEx(cyan, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return cv2.dilate(cyan, np.ones((5, 5), np.uint8))


def glyph_mask(rgb: np.ndarray) -> np.ndarray:
    """A finished family icon's gold glyph plus its dark outline (bool)."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    gold = cv2.inRange(hsv, (12, 70, 120), (38, 255, 255))
    gold = cv2.morphologyEx(gold, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(gold)
    keep = np.zeros_like(gold)
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if 330 < x + w / 2 < 930 and 470 < y + h / 2 < 1060 and area > 30:  # the glyph sits in the middle
            keep[labels == i] = 255
    return cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (61, 61))) > 0


def family_dragon_map(folder: Path) -> tuple[np.ndarray, np.ndarray]:
    """The dragon's normalised brightness (0 = background, 1 = the dragon's light end, above 1.1 = the eye)
    rebuilt from the family's icons, and the eye mask."""
    maps, covers = [], []
    for path in family_icons(folder):
        rgb = np.array(Image.open(path).convert("RGB").resize((SIZE, SIZE), Image.LANCZOS))
        value = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[..., 2].astype(np.float32)
        bg = float(np.median(value[:60, :60]))
        maps.append(np.clip(value - bg, 0.0, None))
        covers.append(glyph_mask(rgb))
    if len(maps) < FAMILY_MIN_ICONS:
        raise SystemExit(f"need at least {FAMILY_MIN_ICONS} family icons in {folder}, found {len(maps)}")
    stack, covered = np.stack(maps), np.stack(covers)
    # Drop an icon whose dragon outline disagrees with the others (smudged or shifted when it was made).
    shape = stack > 60
    agreed = np.median(shape, axis=0) > 0.5
    edge_band = cv2.dilate(agreed.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
    disagreement = np.array([(shape[i] != agreed)[edge_band & ~covered[i]].mean() for i in range(len(maps))])
    keep = disagreement <= max(0.015, 2.5 * float(np.median(disagreement)))
    stack, covered = stack[keep], covered[keep]
    if len(stack) < FAMILY_MIN_ICONS - 2:
        raise SystemExit(f"too few family icons agree on the dragon in {folder}")
    # One gain per icon, measured where no glyph covers any of them, so all icons agree on the brightness.
    clear = ~covered.any(axis=0)
    reference = np.median(stack, axis=0)
    body = clear & (reference > 60)
    gains = np.array([np.median(reference[body] / np.maximum(m[body], 1.0)) for m in stack], np.float32)
    stack = stack * gains[:, None, None]
    top = float(np.percentile(reference[body & (reference < np.percentile(reference[body], 99.5))], 98))
    stack = np.clip(stack / max(1.0, top), 0.0, 1.3)
    # Each icon counts less the closer a pixel is to its glyph, so the seams between icons fade out;
    # a remnant of a glyph just outside its mask cannot show.
    weights = np.stack([np.clip(cv2.distanceTransform((~c).astype(np.uint8), cv2.DIST_L2, 5) / 60.0, 0.0, 1.0) ** 2
                        for c in covered])

    total = weights.sum(axis=0)
    t = np.where(total > 1e-3, (stack * weights).sum(axis=0) / np.maximum(total, 1e-3), 0.0).astype(np.float32)
    # Where every icon's glyph covers a pixel the weights vanish and only a leftover of some glyph's rim could speak:
    # a faint value there is not dragon, so it becomes background (real body is far brighter and is kept).
    t = np.where((total < 0.05) & (t < 0.4), 0.0, t).astype(np.float32)
    # Near the glyph only a few icons show the body, and where their edges disagree the outline gets a bite:
    # close the shape there (never elsewhere, so the horns keep their sharp corners).
    sparse = (~covered).sum(axis=0) <= 3
    closed = cv2.morphologyEx(t, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    bite = sparse & (t < closed - 0.2)
    t = np.where(bite, np.minimum(closed, 1.0), t).astype(np.float32)
    # Drop faint specks that touch no real body (a leftover rim of some glyph where almost every icon was masked).
    count, labels, stats, _ = cv2.connectedComponentsWithStats((t > 0.02).astype(np.uint8))
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] < 2000 and float(t[labels == i].max()) < 0.4:
            t[labels == i] = 0.0
    eye = cv2.dilate(((t > 1.1) * 255).astype(np.uint8), np.ones((3, 3), np.uint8))
    return t, eye


def recolour_map(t_map: np.ndarray, eye: np.ndarray) -> Image.Image:
    """Recolour a normalised dragon map with the ramp on the family's flat navy."""
    alpha = np.clip((t_map - 0.15) / 0.3, 0.0, 1.0)
    body = t_map[(alpha > 0.9) & (eye == 0)]
    lo, hi = (np.percentile(body, 2), np.percentile(body, 98)) if body.size else (0.5, 1.0)
    t = np.clip((t_map - lo) / max(1e-3, hi - lo), 0.0, 1.0)[..., None]
    colour = RAMP_DARK * (1 - t) + RAMP_LIGHT * t
    eye_f = (cv2.GaussianBlur(eye, (5, 5), 0).astype(np.float32) / 255.0)[..., None]
    colour = colour * (1 - eye_f) + EYE_COLOR * eye_f
    background = np.array(BACKGROUND, dtype=np.float32)
    a = alpha[..., None]
    out = background * (1 - a) + colour * a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def recolour_dragon(src: Image.Image) -> Image.Image:
    rgb = np.array(src.convert("RGB").resize((SIZE, SIZE), Image.LANCZOS))
    button = button_mask(rgb)
    # A sibling's finished icon carries its own glyph (outlined, recoloured): clear the whole glyph area too.
    cx, cy = GLYPH_CENTER
    half = int(GLYPH_SIZE * 0.52)
    cv2.rectangle(button, (cx - half, cy - half), (cx + half, cy + half), 255, thickness=cv2.FILLED)
    eye = eye_mask(rgb)
    lum = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    lum[eye > 0] = 200.0  # the eye counts as dragon (light) for the flat map
    # Flatten: dragon luminance on a flat background level, so inpainting cannot pick up
    # the button's yellow or the rounded square's black corners.
    bg_level = float(np.median(lum[(lum < 40) & (button == 0)])) if np.any((lum < 40) & (button == 0)) else 12.0
    flat = np.where(lum > 45, lum, bg_level).astype(np.float32)
    flat8 = np.clip(flat, 0, 255).astype(np.uint8)
    inpainted = cv2.inpaint(flat8, button, 21, cv2.INPAINT_TELEA).astype(np.float32)
    # Alpha of the dragon: smooth ramp on luminance (antialiased edges).
    alpha = np.clip((inpainted - 50.0) / 40.0, 0.0, 1.0)
    dragon = inpainted[alpha > 0.9]
    lo, hi = (np.percentile(dragon, 2), np.percentile(dragon, 98)) if dragon.size else (90.0, 220.0)
    t = np.clip((inpainted - lo) / max(1.0, hi - lo), 0.0, 1.0)[..., None]
    colour = RAMP_DARK * (1 - t) + RAMP_LIGHT * t
    eye_f = (cv2.GaussianBlur(eye, (5, 5), 0).astype(np.float32) / 255.0)[..., None]
    colour = colour * (1 - eye_f) + EYE_COLOR * eye_f
    background = np.array(BACKGROUND, dtype=np.float32)
    a = alpha[..., None]
    out = background * (1 - a) + colour * a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


# ---------------------------------------------------------------------------
# glyph: a clapperboard (film slate) with a play triangle
# ---------------------------------------------------------------------------

def glyph_layer(scale: int = 4) -> Image.Image:
    """RGBA of the glyph, drawn at `scale`x on a square of 1.4 x GLYPH_SIZE and downsampled."""
    box = int(GLYPH_SIZE * 1.4)
    big = box * scale
    c = big / 2
    u = GLYPH_SIZE * scale / 400.0  # 1 unit = 1 px of a 400 px glyph
    dy = -8  # keeps the glyph's bounding box centred on GLYPH_CENTER
    hinge = (-160.0, -4.0)  # the arm's lower-left corner; the arm opens upwards around it
    angle = np.radians(-20.0)  # screen coordinates: negative = counter-clockwise, the free end goes up
    arm_len, arm_h, period, bar = 342.0, 50.0, 70.0, 30.0

    def P(x, y):
        return (c + x * u, c + (y + dy) * u)

    def arm_pt(lx, ly):  # a point of the arm's own frame (x along the arm, y up = negative) on the glyph
        ca, sa = np.cos(angle), np.sin(angle)
        return P(hinge[0] + lx * ca - ly * sa, hinge[1] + lx * sa + ly * ca)

    def mask_of(draw_fn):
        m = Image.new("L", (big, big), 0)
        draw_fn(ImageDraw.Draw(m))
        return np.array(m)

    def rect_poly(d, x0, y0, x1, y1, r):
        d.rounded_rectangle([P(x0, y0), P(x1, y1)], radius=int(r * u), fill=255)

    def stripes(lo, hi, slant, height, frame):  # parallelogram bars across a strip of the given height
        def draw(d):
            x = lo
            while x < hi:
                quad = [(x, 0), (x + bar, 0), (x + bar + slant, -height), (x + slant, -height)]
                d.polygon([frame(px, py) for px, py in quad], fill=255)
                x += period
        return mask_of(draw)

    # the slate: a striped top bar and the body below it, with a small gap that shows the dark outline
    def body_shape(d):
        rect_poly(d, -175, 74, 175, 182, 14)
        rect_poly(d, -175, 10, 175, 58, 10)

    def arm_shape(d):
        d.polygon([arm_pt(0, 0), arm_pt(arm_len, 0), arm_pt(arm_len, -arm_h), arm_pt(0, -arm_h)], fill=255)
        for lx, ly in ((0, -arm_h), (arm_len, -arm_h)):  # round the free corners a little
            x, y = arm_pt(lx + (-9 if lx else 9), ly + 9)
            d.ellipse([x - 9 * u, y - 9 * u, x + 9 * u, y + 9 * u], fill=255)

    def play(d):  # the play triangle, cut out of the body (optically centred)
        d.polygon([P(-30, 100), P(-30, 156), P(26, 128)], fill=255)

    body, arm = mask_of(body_shape), mask_of(arm_shape)
    ca, sa = np.cos(angle), np.sin(angle)
    arm_stripes = stripes(30, arm_len, -34, arm_h,
                          lambda px, py: P(hinge[0] + px * ca - py * sa, hinge[1] + px * sa + py * ca))
    body_stripes = stripes(-175 + 20, 175 + 40, 34, 48, lambda px, py: P(px, 58 + py))
    cut = np.maximum(np.maximum(arm_stripes & arm, body_stripes & body), mask_of(play))
    mask = np.where(cut > 0, 0, np.maximum(body, arm)).astype(np.uint8)
    solid = np.maximum(body, arm)  # silhouette: the outline is dilated from it, so the cuts show the dark colour
    outline = cv2.dilate(solid, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(26 * u), int(26 * u))))
    top, bottom = np.array(GOLD_TOP, np.float32), np.array(GOLD_BOTTOM, np.float32)
    ramp = np.linspace(0, 1, big, dtype=np.float32)[:, None, None]
    gold = np.broadcast_to(top * (1 - ramp) + bottom * ramp, (big, big, 3)).astype(np.uint8)
    layer = np.zeros((big, big, 4), np.uint8)
    layer[..., :3] = OUTLINE  # transparent pixels carry the outline colour, so resizing leaves no halo
    layer[outline > 0, 3] = 255
    layer[mask > 0, :3] = gold[mask > 0]
    layer[mask > 0, 3] = 255
    return Image.fromarray(layer, "RGBA").resize((box, box), Image.LANCZOS)


def compose(src: Image.Image | Path) -> Image.Image:
    base = (recolour_map(*family_dragon_map(src)) if isinstance(src, Path) else recolour_dragon(src)).convert("RGBA")
    glyph = glyph_layer()
    x = GLYPH_CENTER[0] - glyph.width // 2
    y = GLYPH_CENTER[1] - glyph.height // 2
    base.alpha_composite(glyph, (x, y))
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--src", type=Path, default=None, help="The family dragon (dragon-src.png) or a sibling app icon")
    parser.add_argument("--family", type=Path, default=None, help="The shared Icons folder (rebuild the dragon from the family)")
    parser.add_argument("--preview", type=Path, default=None, help="Also write a 400 px preview here")
    args = parser.parse_args()
    family = args.family or (None if args.src else default_family())
    if family is not None:
        src_path = family
        icon = compose(family)
    else:
        src_path = args.src or default_source()
        if src_path is None or not src_path.is_file():
            print("no source: pass --family <Icons folder> or --src dragon-src.png")
            return 2
        icon = compose(Image.open(src_path))
    icon.save(ROOT / "app-icon.png", optimize=True)
    public = ROOT / "client" / "public"
    public.mkdir(parents=True, exist_ok=True)
    icon.resize((512, 512), Image.LANCZOS).save(public / "icon-512.png", optimize=True)
    icon.resize((192, 192), Image.LANCZOS).save(public / "icon-192.png", optimize=True)
    icon.convert("RGBA").save(public / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    static = ROOT / "lumiere_hoard" / "static"  # the built client served by the app, kept in step with public/
    if static.is_dir():
        for name in ("icon-512.png", "icon-192.png", "favicon.ico"):
            (static / name).write_bytes((public / name).read_bytes())
    dist = ROOT / "dist-icons"
    dist.mkdir(exist_ok=True)
    icon.save(dist / "Lumieres hoard.png", optimize=True)
    if args.preview:
        icon.resize((400, 400), Image.LANCZOS).convert("RGB").save(args.preview)
    print(f"icon written from {src_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
