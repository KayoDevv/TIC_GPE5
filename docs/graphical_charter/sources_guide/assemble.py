# -*- coding: utf-8 -*-
import io
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

W, H = 595.275591, 841.889764
def rgb(hx): return tuple(int(hx[i:i+2],16)/255 for i in (1,3,5))
PARCH = rgb("#F4F1E8"); P0 = rgb("#FBF9F3"); NOIR = rgb("#1C1B16")
INK = rgb("#6B6552"); RULE = rgb("#DED7C5"); OR_ = rgb("#B08D57")
VERT = rgb("#3F6F5E"); AMBRE = rgb("#B07D24"); ROUGE = rgb("#A8322A")

FD = "/home/claude/charon/fonts/"
pdfmetrics.registerFont(TTFont("SpaceMono", FD+"SpaceMono-Regular.ttf"))
pdfmetrics.registerFont(TTFont("CinzelSB", FD+"Cinzel-SemiBold.ttf"))
pdfmetrics.registerFont(TTFont("SpectralM", FD+"Spectral-Medium.ttf"))

TITLES = {2:"Les symboles",3:"Le logotype",4:"La palette",5:"Couleurs fonctionnelles",
          6:"La typographie",7:"La grille des supports",8:"Exemples d\u2019application"}

def ruled(c, x0, x1, ys):
    c.setStrokeColorRGB(*RULE); c.setLineWidth(0.17)
    for y in ys: c.line(x0, y, x1, y)

def txt_spaced(c, x, y, s, font, size, color, target_w=None, center_x=None):
    w0 = pdfmetrics.stringWidth(s, font, size)
    cs = 0.0
    if target_w and len(s) > 1:
        cs = (target_w - w0) / (len(s) - 1)
    total = w0 + cs * (len(s) - 1)
    if center_x is not None:
        x = center_x - total / 2
    c.setFillColorRGB(*color)
    t = c.beginText(x, y); t.setFont(font, size); t.setCharSpace(cs); t.textOut(s)
    c.drawText(t)

def patch_p4(c):
    """re-composer le texte 'X correspond...' dans la justification"""
    # couvrir l'ancien bloc (déborde du cadre)
    c.setFillColorRGB(*PARCH)
    c.rect(465, 175, 113, 78, stroke=0, fill=1)
    ruled(c, 465, 578, (178.6, 192.8, 206.9, 221.1, 235.3, 249.4))
    # redessiner le segment du cadre or traversé
    c.setStrokeColorRGB(*OR_); c.setLineWidth(0.99)
    c.line(561.3, 175, 561.3, 253)
    # re-composer, calé pour finir à x <= 538.6
    text = ("X correspond à la hauteur du C de CHARON. Rien — texte, image, bordure — "
            "ne doit entrer dans cet espace. Règle commune aux deux symboles.")
    x0, maxw, size, lh = 466, 72.6, 7.4, 12.45
    words = text.split(" ")
    lines, cur = [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if pdfmetrics.stringWidth(trial, "SpectralM", size) <= maxw:
            cur = trial
        else:
            lines.append(cur); cur = wd
    lines.append(cur)
    y = 262
    c.setFillColorRGB(*INK)
    for ln in lines:
        t = c.beginText(x0, y); t.setFont("SpectralM", size); t.setCharSpace(0); t.textOut(ln)
        c.drawText(t)
        y -= lh

def patch_p6(c):
    """recentrer verticalement les mots dans les pilules de verdict"""
    pills = [
        (73.7, 185.2, VERT,  "AUTORISÉ", 42.9),
        (241.9, 353.4, AMBRE, "SUSPECT", 37.2),
        (410.1, 521.6, ROUGE, "BLOQUÉ", 34.9),
    ]
    for x0, x1, col, word, w in pills:
        c.setFillColorRGB(*col)
        c.rect(x0 + 5, 571.5, (x1 - x0) - 10, 18.5, stroke=0, fill=1)
        # pilule y 568.6..594.1 -> centre 581.35 ; hauteur de capitale Cinzel 6.8 ~ 4.8
        txt_spaced(c, 0, 578.9, word, "CinzelSB", 6.8, (1, 1, 1),
                   target_w=w, center_x=(x0 + x1) / 2)

def patch_p9(c):
    """textes de démonstration en Cinzel SemiBold"""
    # badge extension : CHARON (parchemin sur noir)
    c.setFillColorRGB(*NOIR); c.rect(115, 616.5, 74, 18.5, stroke=0, fill=1)
    txt_spaced(c, 119.1, 620.7, "CHARON", "CinzelSB", 12.5, PARCH, target_w=66.1)
    # panneau de verdict : Détonation achevée. (noir sur P0)
    c.setFillColorRGB(*P0); c.rect(339, 600.5, 159, 19.5, stroke=0, fill=1)
    txt_spaced(c, 343.0, 604.6, "Détonation achevée.", "CinzelSB", 13.0, NOIR, target_w=150.9)
    # couverture de document : CHARON centré (noir sur parchemin)
    c.setFillColorRGB(*PARCH); c.rect(113, 330, 63, 14.5, stroke=0, fill=1)
    txt_spaced(c, 0, 333.7, "CHARON", "CinzelSB", 9.6, NOIR, target_w=53.8, center_x=144.5)
    # état sombre : Analyse en cours… (parchemin sur noir)
    c.setFillColorRGB(*NOIR); c.rect(291, 239.5, 108, 15, stroke=0, fill=1)
    txt_spaced(c, 294.8, 243.0, "Analyse en cours…", "CinzelSB", 9.6, PARCH, target_w=98.9)

EXTRAS = {3: patch_p4, 5: patch_p6, 8: patch_p9}

def overlay(page_num, title, extra=None, total=14):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    # pagination
    c.setFillColorRGB(*PARCH); c.rect(506, 43.5, 37, 14.5, stroke=0, fill=1)
    ruled(c, 506, 543, (51.0,))
    c.setFillColorRGB(*INK); c.setFont("SpaceMono", 6.1)
    c.drawRightString(538.9, 48.8, f"{page_num:02d} / {total}")
    # titre Cinzel SemiBold
    c.setFillColorRGB(*PARCH); c.rect(50, 710.3, 430, 29.2, stroke=0, fill=1)
    ruled(c, 50, 480, (717.2, 731.3))
    c.setFillColorRGB(*NOIR)
    t = c.beginText(56.7, 713.8); t.setFont("CinzelSB", 24.4); t.setCharSpace(0.4); t.textOut(title)
    c.drawText(t)
    if extra: extra(c)
    c.save(); buf.seek(0)
    return PdfReader(buf).pages[0]

orig = PdfReader("/mnt/user-data/uploads/CHARON_brand_guide-5.pdf")
w = PdfWriter()
w.add_page(orig.pages[0])
w.add_page(PdfReader("out/02_sommaire.pdf").pages[0])
for i in range(2, 9):
    pg = orig.pages[i]
    pg.merge_page(overlay(i + 1, TITLES[i], EXTRAS.get(i)))
    w.add_page(pg)
for name in ["10_motif", "11_iconographie", "12_icones", "13_site", "14_interdits"]:
    w.add_page(PdfReader(f"out/{name}.pdf").pages[0])
w.add_metadata({"/Title": "CHARON — Guide de marque · Version 2.0",
                "/Author": "CHARON", "/Subject": "Identité visuelle — édition 02, 2026"})
with open("/home/claude/charon/CHARON_brand_guide_v2.pdf", "wb") as f:
    w.write(f)
print("ok — 14 pages")
