import json, math, random, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SRC = sys.argv[1]
TRACK = sys.argv[2]
FONT = sys.argv[3]
OUT = sys.argv[4]
ONLY = [float(x) for x in sys.argv[5].split(",")] if len(sys.argv) > 5 else None

W, H, FPS = 1080, 1920, 30
CUT = 35.2          # when the contact card starts revealing
TOTAL = 42.0
NFR = int(TOTAL * FPS)

BG = (250, 247, 242)
INK = (29, 56, 43)
ACC = (68, 99, 75)
LOGO = [(126, 158, 79), (221, 166, 74), (62, 142, 156), (125, 85, 166), (218, 90, 94)]
CONF = LOGO + [ACC, (245, 198, 170), (136, 201, 191)]

def font(size, weight):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_axes([weight])
    return f

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def ease_out(x):
    x = clamp(x); return 1 - (1 - x) ** 3

def ease_io(x):
    x = clamp(x); return 3 * x * x - 2 * x * x * x

def back_out(x, s=1.9):
    x = clamp(x); x -= 1; return x * x * ((s + 1) * x + s) + 1

def rgba(c, a):
    return (c[0], c[1], c[2], int(255 * clamp(a)))

# ---------- tracking of the checkbox on each "vitória" slide ----------
track = {int(k): v for k, v in json.load(open(TRACK)).items()}
SEG = {1: 4.8, 2: 8.4, 3: 12.0, 4: 15.6, 5: 19.2, 6: 22.8}  # slide fully in
SLIDE = 3.2                                                  # until next transition starts

def box_at(k, fi):
    rows = track[k]
    good = [(i, l) for i, m, l in rows if m > 0.9]
    best = min(good, key=lambda r: abs(r[0] - fi))
    if fi > good[-1][0]:
        best = good[-1]
    x, y = best[1]
    return x + 6, y + 5   # top-left of the 43px checkbox

# ---------- supersampled drawing helpers ----------
SS = 3

class Layer:
    """Full-frame RGBA overlay drawn at SS x and downsampled locally."""
    def __init__(self):
        self.img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def sprite(self, x0, y0, w, h, fn):
        w, h = int(round(w)), int(round(h))
        s = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(s)
        fn(d, SS)
        s = s.resize((w, h), Image.LANCZOS)
        self.img.alpha_composite(s, (int(x0), int(y0)))

def draw_check(d, s, x, y, size, prog, color, width):
    """Check mark inside a box at (x,y) of given size, drawn progressively."""
    p1 = (x + size * 0.24, y + size * 0.53)
    p2 = (x + size * 0.43, y + size * 0.72)
    p3 = (x + size * 0.78, y + size * 0.30)
    l1 = math.dist(p1, p2); l2 = math.dist(p2, p3)
    L = (l1 + l2) * prog
    pts = [p1]
    if L <= l1:
        t = L / l1; pts.append((p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t))
    else:
        t = (L - l1) / l2; pts += [p2, (p2[0] + (p3[0] - p2[0]) * t, p2[1] + (p3[1] - p2[1]) * t)]
    if prog <= 0: return
    pts = [(a * s, b * s) for a, b in pts]
    d.line(pts, fill=color, width=int(width * s), joint="curve")
    r = width * s / 2
    for px, py in (pts[0], pts[-1]):
        d.ellipse([px - r, py - r, px + r, py + r], fill=color)

def burst(layer, cx, cy, t, seed, n=24, spread=1.0, life=1.1):
    """Confetti burst; t = seconds since burst."""
    if t < 0 or t > life: return
    rnd = random.Random(seed)
    for _ in range(n):
        ang = rnd.uniform(0, 2 * math.pi)
        sp = rnd.uniform(260, 620) * spread
        col = rnd.choice(CONF)
        sz = rnd.uniform(9, 16)
        rot0 = rnd.uniform(0, 180); rv = rnd.uniform(-500, 500)
        kind = rnd.random()
        # drag + gravity
        k = 3.2
        dist = sp / k * (1 - math.exp(-k * t))
        x = cx + math.cos(ang) * dist
        y = cy + math.sin(ang) * dist + 260 * t * t
        a = 1.0 if t < life - 0.45 else (life - t) / 0.45
        rot = math.radians(rot0 + rv * t)
        def fn(d, s, col=col, sz=sz, rot=rot, kind=kind, a=a):
            c = 22 * s
            if kind < 0.45:
                hw, hh = sz * 0.5 * s, sz * 0.22 * s
                pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
                pts = [(c + px * math.cos(rot) - py * math.sin(rot), c + px * math.sin(rot) + py * math.cos(rot)) for px, py in pts]
                d.polygon(pts, fill=rgba(col, a))
            else:
                r = sz * 0.36 * s
                d.ellipse([c - r, c - r, c + r, c + r], fill=rgba(col, a))
        layer.sprite(x - 22, y - 22, 44, 44, fn)

def ring(layer, cx, cy, t, r0=26, r1=90, dur=0.55, col=ACC):
    if t < 0 or t > dur: return
    p = ease_out(t / dur)
    r = r0 + (r1 - r0) * p
    a = 0.7 * (1 - p)
    R = int(r1 + 6)
    def fn(d, s):
        c = R * s
        d.ellipse([c - r * s, c - r * s, c + r * s, c + r * s], outline=rgba(col, a), width=int(4 * s))
    layer.sprite(cx - R, cy - R, 2 * R, 2 * R, fn)

def filled_box(layer, x, y, size, t, alpha, radius, check_w):
    """Green filled checkbox that pops in at t=0 and draws its check."""
    if t < 0: return
    sc = back_out(t / 0.28)
    p_check = ease_out((t - 0.12) / 0.32)
    pad = 14
    S = size + 2 * pad
    def fn(d, s):
        c = S / 2 * s
        hs = size / 2 * sc * s
        d.rounded_rectangle([c - hs, c - hs, c + hs, c + hs], radius=radius * sc * s, fill=rgba(ACC, alpha))
        draw_check(d, s, pad, pad, size, p_check, (255, 255, 255, int(255 * alpha)), check_w)
    layer.sprite(x - pad, y - pad, S, S, fn)

def progress(layer, x, y, k, t, alpha):
    """Six dots: done, current (fills at t>=0), upcoming."""
    gap, r = 30, 8
    def fn(d, s):
        for i in range(6):
            cx, cy = (r + 4 + i * gap) * s, (r + 4) * s
            rr = r * s
            if i < k - 1:
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=rgba(ACC, alpha))
            elif i == k - 1:
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=rgba(ACC, alpha), width=int(2.5 * s))
                f = back_out(t / 0.35)
                if t > 0:
                    fr = rr * f
                    d.ellipse([cx - fr, cy - fr, cx + fr, cy + fr], fill=rgba(ACC, alpha))
            else:
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=rgba(ACC, alpha * 0.45), width=int(2.5 * s))
    layer.sprite(x, y, 6 * gap + 10, 2 * r + 10, fn)

# ---------- cover: light confetti drifting outside the card ----------
COVER_RNG = random.Random(7)
COVER_P = [(COVER_RNG.uniform(0, W), COVER_RNG.uniform(-300, H), COVER_RNG.uniform(60, 120),
            COVER_RNG.uniform(0, 6.28), COVER_RNG.choice(CONF), COVER_RNG.uniform(8, 13),
            COVER_RNG.random()) for _ in range(34)]
COVER_CARD = (40, 470, 840, 1270)

def cover_confetti(layer, t):
    a_all = clamp((t - 0.7) / 0.6) * clamp((4.5 - t) / 0.4)
    if a_all <= 0: return
    for x0, y0, v, ph, col, sz, kind in COVER_P:
        y = (y0 + v * t) % (H + 100) - 50
        x = x0 + 18 * math.sin(ph + t * 1.6)
        if COVER_CARD[0] - 15 < x < COVER_CARD[2] + 15 and COVER_CARD[1] - 15 < y < COVER_CARD[3] + 15:
            continue
        rot = ph + t * 2.2
        def fn(d, s, col=col, sz=sz, rot=rot, kind=kind):
            c = 16 * s
            if kind < 0.5:
                hw, hh = sz * 0.5 * s, sz * 0.22 * s
                pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
                pts = [(c + px * math.cos(rot) - py * math.sin(rot), c + px * math.sin(rot) + py * math.cos(rot)) for px, py in pts]
                d.polygon(pts, fill=rgba(col, 0.85 * a_all))
            else:
                r = sz * 0.34 * s
                d.ellipse([c - r, c - r, c + r, c + r], fill=rgba(col, 0.85 * a_all))
        layer.sprite(x - 16, y - 16, 32, 32, fn)

# ---------- resumo slide ----------
RES_T0 = 26.85
RES_STEP = 0.3
RES_BOX = (122, 693, 39)    # x, y of first checkbox, size
RES_PITCH = 84.3
RES_ROW = (98, 678, 982, 746)
RES_MSG = (98, 1209, 982, 1340)

def resumo(layer, t):
    if not (26.4 <= t < 31.75): return
    fade = clamp((31.75 - t) / 0.35)
    for i in range(6):
        ti = t - (RES_T0 + i * RES_STEP)
        if ti < 0: continue
        y = RES_BOX[1] + i * RES_PITCH
        # row highlight sweep
        sw = ease_out(ti / 0.45)
        ha = 0.09 * (1 - clamp((ti - 0.45) / 0.6)) * fade
        if ha > 0:
            x0, y0, x1, y1 = RES_ROW[0], RES_ROW[1] + i * RES_PITCH, RES_ROW[2], RES_ROW[3] + i * RES_PITCH
            ww = int((x1 - x0) * sw)
            if ww > 4:
                def fn(d, s, ww=ww, h=y1 - y0, ha=ha):
                    d.rounded_rectangle([0, 0, ww * s, h * s], radius=14 * s, fill=rgba(ACC, ha))
                layer.sprite(x0, y0, ww + 1, y1 - y0 + 1, fn)
        filled_box(layer, RES_BOX[0], y, RES_BOX[2], ti, fade, 7, 4.2)
        ring(layer, RES_BOX[0] + RES_BOX[2] // 2, y + RES_BOX[2] // 2, ti - 0.05, 22, 64, 0.5)
    # final message: pulse border + small burst
    tm = t - (RES_T0 + 6 * RES_STEP + 0.35)
    if tm >= 0:
        x0, y0, x1, y1 = RES_MSG
        for k in range(2):
            tk = tm - k * 0.9
            if 0 <= tk <= 0.9:
                p = ease_out(tk / 0.9)
                g = 4 + 18 * p
                a = 0.55 * (1 - p) * fade
                def fn(d, s, g=g, a=a):
                    d.rounded_rectangle([(30 - g) * s, (30 - g) * s, (30 + x1 - x0 + g) * s, (30 + y1 - y0 + g) * s],
                                        radius=(18 + g * 0.6) * s, outline=rgba(ACC, a), width=int(4 * s))
                layer.sprite(x0 - 30, y0 - 30, x1 - x0 + 60, y1 - y0 + 60, fn)
        burst(layer, x1 - 40, y0 + 10, tm, 99, n=16, spread=0.8)

# ---------- contact end card ----------
F_NAME = font(92, 700)
F_ROLE = font(40, 500)
F_ROW = font(44, 500)
F_CTA = font(34, 600)
F_TAG = font(28, 700)

def lemniscate(n=400):
    pts = []
    for i in range(n + 1):
        u = math.pi / 2 + 2 * math.pi * i / n   # start at the crossing
        den = 1 + math.sin(u) ** 2
        pts.append((math.cos(u) / den, math.sin(u) * math.cos(u) / den))
    return pts

LEM = lemniscate()

def logo(layer, cx, cy, wdt, prog, alpha=1.0, stroke=15):
    if prog <= 0: return
    hw = wdt / 2
    pts = [(cx + x * hw, cy + y * hw * 1.25) for x, y in LEM]
    m = max(2, int(len(pts) * prog))
    pad = stroke + 4
    bx0, by0 = cx - hw - pad, cy - hw * 0.45 - pad
    bw, bh = int(wdt + 2 * pad), int(hw * 0.9 + 2 * pad)
    def fn(d, s):
        r = stroke / 2 * s
        for i in range(m):
            # colour by position along the path (5 bands like the brand logo)
            band = LOGO[min(4, int(5 * ((i / len(pts) + 0.0) % 1)))]
            x, y = (pts[i][0] - bx0) * s, (pts[i][1] - by0) * s
            d.ellipse([x - r, y - r, x + r, y + r], fill=rgba(band, alpha))
    layer.sprite(bx0, by0, bw, bh, fn)

def icon_whatsapp(d, s, c, r, col):
    lw = 4.5 * s
    d.ellipse([c - r, c - r, c + r, c + r], outline=col, width=int(lw))
    d.polygon([(c - r * 0.75, c + r * 0.45), (c - r * 1.05, c + r * 1.08), (c - r * 0.3, c + r * 0.86)], fill=col)
    # handset
    hr = r * 0.52
    d.arc([c - hr, c - hr, c + hr, c + hr], 120, 330, fill=col, width=int(6 * s))
    for ang in (120, 330):
        a = math.radians(ang)
        px, py = c + hr * math.cos(a), c + hr * math.sin(a)
        d.ellipse([px - 6 * s, py - 6 * s, px + 6 * s, py + 6 * s], fill=col)

def icon_insta(d, s, c, r, col):
    lw = int(4.5 * s)
    d.rounded_rectangle([c - r, c - r, c + r, c + r], radius=r * 0.5, outline=col, width=lw)
    rr = r * 0.45
    d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=col, width=lw)
    dx, dy, dr = c + r * 0.55, c - r * 0.55, 3.2 * s
    d.ellipse([dx - dr, dy - dr, dx + dr, dy + dr], fill=col)

def icon_web(d, s, c, r, col):
    lw = int(4 * s)
    d.ellipse([c - r, c - r, c + r, c + r], outline=col, width=lw)
    d.ellipse([c - r * 0.45, c - r, c + r * 0.45, c + r], outline=col, width=lw)
    d.line([(c - r, c), (c + r, c)], fill=col, width=lw)
    for yy in (-0.5, 0.5):
        hw = r * math.sqrt(1 - yy * yy)
        d.line([(c - hw, c + yy * r), (c + hw, c + yy * r)], fill=col, width=int(3 * s))

ROWS = [("WhatsApp (21) 97748-6801", icon_whatsapp),
        ("@soniatorresfono", icon_insta),
        ("sonia.fonosuite.com", icon_web)]

BG_DOTS = [(random.Random(i).uniform(0, W), random.Random(i + 50).uniform(0, H), random.Random(i + 90).choice(CONF),
            random.Random(i + 120).uniform(5, 10), random.Random(i + 150).uniform(0, 6.28)) for i in range(26)]

def text_center(img, y, txt, f, col, alpha, dy=0):
    d = ImageDraw.Draw(img)
    bb = d.textbbox((0, 0), txt, font=f)
    tw = bb[2] - bb[0]
    tl = Image.new("RGBA", (tw + 20, bb[3] + 20), (0, 0, 0, 0))
    ImageDraw.Draw(tl).text((10 - bb[0], 0), txt, font=f, fill=rgba(col, 1))
    if alpha < 1:
        tl.putalpha(tl.getchannel("A").point(lambda v: int(v * alpha)))
    img.alpha_composite(tl, (int((W - tw) / 2 - 10), int(y + dy)))

def end_card(t):
    """t = seconds since CUT. Returns RGBA full frame of the card."""
    img = Image.new("RGBA", (W, H), rgba(BG, 1))
    lay = Layer()
    # floating background confetti (outside content column)
    for x0, y0, col, sz, ph in BG_DOTS:
        if 110 < x0 < 970 and 330 < y0 < 1560: continue
        a = 0.55 * clamp((t - 0.6) / 0.8)
        y = y0 - 22 * t; x = x0 + 10 * math.sin(ph + t)
        r = sz / 2
        def fn(d, s, col=col, r=r, a=a):
            d.ellipse([(12 - r) * s, (12 - r) * s, (12 + r) * s, (12 + r) * s], fill=rgba(col, a))
        lay.sprite(x - 12, y - 12, 24, 24, fn)
    # logo draw
    logo(lay, W / 2, 500, 230, ease_io((t - 0.45) / 0.9))
    img.alpha_composite(lay.img)
    # name + role
    a = ease_out((t - 0.9) / 0.5)
    if a > 0:
        text_center(img, 620, "Sônia Torres", F_NAME, INK, a, dy=30 * (1 - a))
    a = ease_out((t - 1.1) / 0.5)
    if a > 0:
        text_center(img, 745, "Fonoaudióloga · CRFa 1-17701", F_ROLE, INK, a, dy=24 * (1 - a))
    # divider
    p = ease_out((t - 1.3) / 0.5)
    if p > 0:
        d = ImageDraw.Draw(img)
        hw = 70 * p
        d.rounded_rectangle([W / 2 - hw, 838, W / 2 + hw, 843], radius=3, fill=rgba(ACC, 1))
    # contact rows
    for i, (txt, ic) in enumerate(ROWS):
        ti = t - (1.5 + 0.22 * i)
        a = ease_out(ti / 0.55)
        if a <= 0: continue
        x0, y0, rw, rh = 150, 910 + i * 132, 780, 108
        dx = 70 * (1 - a)
        pulse = 0.0
        if i == 0:
            for pt in (3.4, 5.2):
                q = (t - pt) / 0.7
                if 0 <= q <= 1: pulse = math.sin(math.pi * q)
        sc = 1 + 0.035 * pulse
        row = Layer()
        def fn(d, s, a=a, ic=ic, pulse=pulse):
            d.rounded_rectangle([4 * s, 4 * s, (rw - 4) * s, (rh - 4) * s], radius=(rh / 2 - 4) * s,
                                fill=(255, 255, 255, int(255 * a)),
                                outline=rgba(ACC if pulse > 0 else (226, 219, 207), a), width=int((2 + 2 * pulse) * s))
            c = rh / 2 * s
            cr = 38 * s
            d.ellipse([c - cr + 8 * s, c - cr, c + cr + 8 * s, c + cr], fill=rgba(ACC, a))
            ic(d, s, c + 8 * s, 19 * s, (255, 255, 255, int(255 * a)))
        row.sprite(0, 0, rw, rh, fn)
        tile = row.img.crop((0, 0, rw, rh))
        dd = ImageDraw.Draw(tile)
        bb = dd.textbbox((0, 0), txt, font=F_ROW)
        tl = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
        ImageDraw.Draw(tl).text((126 - bb[0], (rh - (bb[3] - bb[1])) / 2 - bb[1]), txt, font=F_ROW, fill=rgba(INK, 1))
        tl.putalpha(tl.getchannel("A").point(lambda v, a=a: int(v * a)))
        tile.alpha_composite(tl)
        if sc != 1:
            tile = tile.resize((int(rw * sc), int(rh * sc)), Image.LANCZOS)
        img.alpha_composite(tile, (int(x0 + dx - (tile.width - rw) / 2), int(y0 - (tile.height - rh) / 2)))
    # CTA
    a = ease_out((t - 2.4) / 0.5)
    if a > 0:
        text_center(img, 1330, "Converse comigo pelo WhatsApp", F_CTA, ACC, a, dy=20 * (1 - a))
    return img

# ---------- per-frame composition ----------
def overlay(t, fi):
    lay = Layer()
    if t < 4.6:
        cover_confetti(lay, t)
    for k, s0 in SEG.items():
        if not (s0 - 0.2 <= t < s0 + SLIDE + 0.4): continue
        bx, by = box_at(k, fi)
        fade = clamp((s0 + SLIDE + 0.3 - t) / 0.3) * clamp((t - (s0 - 0.2)) / 0.3)
        tc = t - (s0 + 0.55)
        progress(lay, bx - 4, by + 425, k, tc, fade * 0.95)
        filled_box(lay, bx, by, 43, tc, fade, 8, 5)
        ring(lay, bx + 21, by + 21, tc - 0.05)
        burst(lay, bx + 21, by + 21, tc - 0.1, k * 13)
    resumo(lay, t)
    return lay.img

def main():
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", SRC, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    if ONLY is None:
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                                "-pix_fmt", "yuv420p", OUT], stdin=subprocess.PIPE)
    last = None
    fsz = W * H * 3
    for fi in range(NFR):
        t = fi / FPS
        if ONLY is not None and not any(abs(t - o) < 0.5 / FPS for o in ONLY):
            if t < CUT + 0.8:
                dec.stdout.read(fsz)
            continue
        if t < CUT + 0.8:
            buf = dec.stdout.read(fsz)
            if len(buf) == fsz:
                last = buf
            base = Image.frombuffer("RGB", (W, H), last).convert("RGBA")
        frame = None
        if t < CUT + 0.8:
            base.alpha_composite(overlay(t, fi))
            frame = base
        if t >= CUT:
            tc = t - CUT
            card = end_card(tc)
            p = ease_io(tc / 0.7)
            if p < 1:
                # circular reveal from the logo of the previous slide
                mask = Image.new("L", (W // 2, H // 2), 0)
                R = p * 1150 / 2
                cx, cy = 540 / 2, 515 / 2
                ImageDraw.Draw(mask).ellipse([cx - R, cy - R, cx + R, cy + R], fill=255)
                mask = mask.resize((W, H), Image.BILINEAR)
                frame.paste(card, (0, 0), mask)
                rl = Layer()
                Rf = R * 2
                ImageDraw.Draw(rl.img).ellipse([540 - Rf, 515 - Rf, 540 + Rf, 515 + Rf],
                                                outline=rgba(ACC, 1 - p), width=6)
                frame.alpha_composite(rl.img)
            else:
                frame = card
        rgb = frame.convert("RGB")
        if ONLY is not None:
            rgb.save(f"{OUT}_{t:.2f}.png")
        else:
            enc.stdin.write(rgb.tobytes())
        if fi % 60 == 0:
            print("frame", fi, flush=True)
    dec.stdout.close()
    if ONLY is None:
        enc.stdin.close(); enc.wait()

main()
