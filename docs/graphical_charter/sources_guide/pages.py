# -*- coding: utf-8 -*-
"""Génération des nouvelles pages du guide CHARON — v2, métriques originales."""
import base64, io
from PIL import Image
from template import *
import icons

TOTAL = 14

# ---------------------------------------------------------------- meander --
def meander_path(x, y, unit, n):
    u = unit
    d = [f"M{x + 0.5 * u:.2f} {y + 4.5 * u:.2f} L{x + (n * 5 + 0.5) * u:.2f} {y + 4.5 * u:.2f}"]
    for k in range(n):
        X = x + k * 5 * u
        pts = [(0.5, 4.5), (0.5, 0.5), (4.5, 0.5), (4.5, 3.0), (2.5, 3.0), (2.5, 1.9), (3.5, 1.9)]
        d.append("M" + " L".join(f"{X + px * u:.2f} {y + py * u:.2f}" for px, py in pts))
    return " ".join(d)

def meander(x, y, unit, n, color, sw=None):
    sw = sw or unit * 0.85
    return (f'<path d="{meander_path(x, y, unit, n)}" fill="none" stroke="{color}" '
            f'stroke-width="{sw}" stroke-linecap="butt" stroke-linejoin="miter"/>')

# ---------------------------------------------------------------- images ---
def embed_img(path, x, y, w, h, quality=82, max_px=620):
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'<image x="{x}" y="{y}" width="{w}" height="{h}" href="data:image/jpeg;base64,{b64}" preserveAspectRatio="xMidYMid slice"/>'

IMG = "/home/claude/charon/landing/public/images/"

# ---------------------------------------------------------------- pages ----

def page_sommaire():
    b = [header("", "P R É A M B U L E", "SOMMAIRE")]
    b.append(T(M, 128.1, "Une marque qui trie", 24.4, F_CIN_S, NOIR, ls=0.4))
    b.append(T(M, 160.1, "ce qui a le droit de passer.", 24.4, F_CIN_S, NOIR, ls=0.4))
    b.append(f'<line x1="{M}" y1="166" x2="{CR}" y2="166" stroke="{OR_}" stroke-width="1.13"/>')

    p1 = ("CHARON examine chaque fichier qu'un employé reçoit avant qu'il n'atteigne sa machine — une analyse "
          "statique, une détonation en sandbox isolée, une lecture sémantique du contexte. Trois passeurs "
          "indépendants, un seul verdict.")
    p2_ = ("L'identité visuelle emprunte au vocabulaire du musée et de la gravure : la gravité tranquille d'une "
           "salle de plâtres antiques, la précision d'un instrument de mesure. Trois couleurs, deux typographies, "
           "aucun ornement superflu — parce qu'un système de confiance n'a pas besoin de décor pour être pris "
           "au sérieux.")
    p3_ = ("Cette seconde édition étend le système au-delà du papier : un motif identitaire, une iconographie "
           "gravée, une grammaire du mouvement pour l'écran et la déclinaison web de la marque.")
    t, yy = wrap_text(M, 192, p1, 100, 8.8, lh=14.3)
    b.append(t)
    t, yy = wrap_text(M, yy + 24, p2_, 100, 8.8, lh=14.3)
    b.append(t)
    t, yy = wrap_text(M, yy + 24, p3_, 100, 8.8, lh=14.3, fam=F_SPE, style="italic")
    b.append(t)

    b.append(gold_overline(M, yy + 46, "SOMMAIRE"))
    chapters = [
        ("01", "Les symboles", "03"), ("02", "Le logotype", "04"),
        ("03", "La palette", "05"), ("04", "Couleurs fonctionnelles", "06"),
        ("05", "La typographie", "07"), ("06", "La grille des supports", "08"),
        ("07", "Exemples d'application", "09"), ("08", "Le motif identitaire", "10"),
        ("09", "L'iconographie", "11"), ("10", "Les icônes d'état", "12"),
        ("11", "Le site web", "13"), ("12", "Les interdits", "14"),
    ]
    y0 = yy + 70
    col_w = (CW - 26) / 2
    for i, (num, title, pg) in enumerate(chapters):
        col = i // 6
        row = i % 6
        x = M + col * (col_w + 26)
        xr = x + col_w
        y = y0 + row * 27
        b.append(T(x, y, num, 8.2, F_MONO, OR_HEAD))
        b.append(T(x + 24, y, title, 10.2, F_CIN_S, NOIR))
        b.append(T(xr, y, pg, 8.2, F_MONO, N3, anchor="end"))
        b.append(f'<line x1="{x}" y1="{y + 7.5}" x2="{xr}" y2="{y + 7.5}" stroke="{P3}" stroke-width="0.5"/>')
    b.append(footer(2, TOTAL))
    return svg_page("\n".join(b))


def page_motif():
    b = [header("08", "Le motif identitaire", "LA GRECQUE")]
    b.append(page_title("Le motif identitaire"))
    t, yy = lede("La grecque — le méandre du fleuve que le passeur remonte sans fin. Un seul motif "
                 "géométrique, hérité de la céramique attique : il borde, il scande, il n'envahit jamais.")
    b.append(t)

    y0 = yy + 32
    b.append(gold_overline(M, y0, "CONSTRUCTION"))
    gx, gy, u = M, y0 + 16, 12
    for i in range(11):
        b.append(f'<line x1="{gx + i * u}" y1="{gy}" x2="{gx + i * u}" y2="{gy + 5 * u}" stroke="{P4}" stroke-width="0.35"/>')
    for j in range(6):
        b.append(f'<line x1="{gx}" y1="{gy + j * u}" x2="{gx + 10 * u}" y2="{gy + j * u}" stroke="{P4}" stroke-width="0.35"/>')
    b.append(meander(gx, gy, u, 2, NOIR))
    b.append(T(gx + 5 * u, gy + 5 * u + 15, "1 motif = 5 × 5 modules", 7.1, F_MONO, N3, anchor="middle"))
    b.append(T(gx + 5 * u, gy + 5 * u + 27, "TRAIT = 0,85 MODULE — CONSTANT", 6.1, F_MONO, N4, anchor="middle", ls=0.4))

    tx = gx + 10 * u + 30
    rules_c = [
        ("Le module", "Le motif se construit sur une grille de 5 × 5 modules. Le trait garde une épaisseur constante de 0,85 module — ni pleins, ni déliés."),
        ("Le raccord", "Chaque motif s'enchaîne au suivant par la ligne de base. La grecque ne se découpe jamais en cours de motif : on arrondit toujours au motif entier."),
    ]
    ty = y0 + 24
    for title, body in rules_c:
        b.append(T(tx, ty, title, 10.2, F_CIN_S, NOIR))
        t, ty2 = wrap_text(tx, ty + 14, body, 58, 8.2, lh=12.6)
        b.append(t)
        ty = ty2 + 28

    y1 = gy + 5 * u + 50
    b.append(gold_overline(M, y1, "LA FRISE"))
    fy = y1 + 14
    fh = 38
    b.append(f'<rect x="{M}" y="{fy}" width="{CW}" height="{fh}" fill="{P0}" stroke="{P3}" stroke-width="0.6"/>')
    mu = 4.9
    n = int((CW - 36) / (5 * mu))
    b.append(meander(M + 18, fy + (fh - 5 * mu) / 2, mu, n, OR_))
    b.append(T(M, fy + fh + 13, "Sur parchemin — or antique, hauteur 26 px / 7 mm.", 7.7, F_SPE_M, N3))
    fy2 = fy + fh + 26
    b.append(f'<rect x="{M}" y="{fy2}" width="{CW}" height="{fh}" fill="{NOIR}"/>')
    b.append(meander(M + 18, fy2 + (fh - 5 * mu) / 2, mu, n, OR_))
    b.append(T(M, fy2 + fh + 13, "Sur fond sombre — l'or reste identique ; seul le fond s'inverse.", 7.7, F_SPE_M, N3))

    y2 = fy2 + fh + 40
    b.append(gold_overline(M, y2, "RÈGLES D'USAGE"))
    rules = [
        "La grecque est un filet : elle souligne une tête ou un pied de support, jamais un fond intégral.",
        "Hauteur comprise entre 12 et 32 px (3 à 9 mm) — au-delà, elle devient décor.",
        "Une seule frise par support. Elle court toujours d'un bord à l'autre, horizontale.",
        "Deux encres seulement : or sur parchemin, or sur noir profond. Jamais de version noire sur or.",
    ]
    ry = y2 + 18
    for r in rules:
        b.append(T(M, ry, "—", 8.8, F_SPE_M, OR_HEAD))
        t, ry2 = wrap_text(M + 16, ry, r, 100, 8.5, lh=13)
        b.append(t)
        ry = ry2 + 16
    b.append(footer(10, TOTAL))
    return svg_page("\n".join(b))


def page_iconographie():
    b = [header("09", "L'iconographie", "GRAVURES")]
    b.append(page_title("L'iconographie"))
    t, yy = lede("Trois gravures fondatrices accompagnent la marque : l'obole, la main du passeur, le fleuve. "
                 "Un traitement unique — le trait de burin et la lumière de lanterne, jamais la photographie couleur.")
    b.append(t)

    y0 = yy + 30
    pw = (CW - 2 * 16) / 3
    ph = pw
    plates = [
        (IMG + "coin.png", "PL. I — L'OBOLE", "Le prix de la traversée : chaque fichier paie son passage en preuves."),
        (IMG + "hand-coin.png", "PL. II — LA MAIN DU PASSEUR", "Le geste du verdict : recevoir, peser, rendre ou retenir."),
        (IMG + "styx-river.png", "PL. III — LE STYX", "Le flux : la frontière que rien ne franchit sans être vu."),
    ]
    for i, (img, cap, sub) in enumerate(plates):
        x = M + i * (pw + 16)
        b.append(f'<rect x="{x - 3}" y="{y0 - 3}" width="{pw + 6}" height="{ph + 6}" fill="none" stroke="{OR_}" stroke-width="0.8"/>')
        b.append(embed_img(img, x, y0, pw, ph))
        b.append(T(x, y0 + ph + 17, cap, 6.5, F_MONO, NOIR, ls=0.4))
        t, _ = wrap_text(x, y0 + ph + 30, sub, 38, 7.1, lh=10.8, fam=F_SPE, fill=N3, style="italic")
        b.append(t)

    y1 = y0 + ph + 74
    b.append(gold_overline(M, y1, "TRAITEMENT"))
    rules = [
        ("Le trait, pas le pixel", "Toute illustration relève de la gravure : hachures, tailles croisées, aplats sobres. La photographie couleur est proscrite sur les supports de marque."),
        ("La planche sombre", "Le fond sombre est réservé aux planches d'illustration — il les isole comme un cabinet d'estampes. Le reste du support demeure parchemin."),
        ("La légende obligatoire", "Chaque planche porte une légende en Space Mono, numérotée en chiffres romains — le vocabulaire du catalogue de musée."),
        ("Le sujet entier", "Une gravure ne se recadre pas dans le vif du sujet : l'obole reste entière, la main reste entière."),
    ]
    col_w = (CW - 26) / 2
    ry = y1 + 22
    max_y = ry
    for i, (title, body) in enumerate(rules):
        col = i % 2
        x = M + col * (col_w + 26)
        if col == 0 and i > 0:
            ry = max_y + 26
        b.append(T(x, ry, title, 10.2, F_CIN_S, NOIR))
        t, y_end = wrap_text(x, ry + 14, body, 55, 8.2, lh=12.6)
        b.append(t)
        max_y = y_end if col == 0 else max(max_y, y_end)
    b.append(footer(11, TOTAL))
    return svg_page("\n".join(b))


def page_icones():
    b = [header("10", "Les icônes d'état", "GRAMMAIRE DU MOUVEMENT")]
    b.append(page_title("Les icônes d'état"))
    t, yy = lede("Cinq formes, cinq états. À l'écran, les icônes de CHARON ne changent pas seulement de "
                 "couleur — elles changent de comportement. La couleur seule ne suffit jamais.")
    b.append(t)

    states = [
        ("rest",    "VEILLE",    "IDLE", N4),
        ("scan",    "ANALYSE",   "SCAN", OR_),
        ("suspect", "SUSPICION", "WARN", AMBRE),
        ("clear",   "SÛR",       "PASS", VERT),
        ("threat",  "DANGER",    "KILL", ROUGE),
    ]
    shapes = [
        ("eye",     "L'œil"),
        ("boat",    "La barque"),
        ("virus",   "Le virus"),
        ("ring",    "L'anneau"),
        ("lantern", "La lanterne"),
    ]
    y0 = yy + 32
    label_w = 70
    cell = (CW - label_w) / 5
    row_h = 52
    for j, (st, name, code, col) in enumerate(states):
        cx = M + label_w + j * cell + 8
        b.append(f'<circle cx="{cx}" cy="{y0 - 3}" r="2.4" fill="{col}"/>')
        b.append(T(cx + 7, y0, name, 6.4, F_CIN_S, NOIR, ls=0.8))
        b.append(T(cx + 7, y0 + 9.5, code, 5.8, F_MONO, col, ls=0.4))
    gy = y0 + 18
    for i, (sh, name) in enumerate(shapes):
        ry = gy + i * row_h
        b.append(T(M, ry + row_h / 2 + 3, name, 8.5, F_SPE_M, NOIR))
        for j, (st, _n, _c, col) in enumerate(states):
            x = M + label_w + j * cell
            b.append(f'<rect x="{x}" y="{ry}" width="{cell}" height="{row_h}" fill="{P0}" stroke="{P3}" stroke-width="0.5"/>')
            isz = 31
            b.append(icons.icon(sh, st, col, x + (cell - isz) / 2, ry + (row_h - isz) / 2, isz))

    y1 = gy + 5 * row_h + 28
    b.append(gold_overline(M, y1, "LA GRAMMAIRE DU MOUVEMENT"))
    gram = [
        ("VEILLE",    N4,    "lent et régulier — respiration, clignement, tangage."),
        ("ANALYSE",   OR_,   "continu et dirigé — rotation, balayage, cap tenu."),
        ("SUSPICION", AMBRE, "hésitant, irrégulier — tremblement, vacillement, regard qui fuit."),
        ("SÛR",       VERT,  "immobile et plein — la forme se remplit, la stabilité rassure."),
        ("DANGER",    ROUGE, "rupture — croix, naufrage, extinction. Le mouvement s'arrête mal."),
    ]
    ry = y1 + 18
    for name, col, desc in gram:
        b.append(f'<circle cx="{M + 3}" cy="{ry - 2.6}" r="2.4" fill="{col}"/>')
        b.append(T(M + 12, ry, name, 6.8, F_CIN_S, NOIR, ls=1.1))
        b.append(T(M + 86, ry, desc, 8.2, F_SPE_M, N2))
        ry += 15.5

    ry += 6
    b.append(f'<line x1="{M}" y1="{ry - 9}" x2="{CR}" y2="{ry - 9}" stroke="{P3}" stroke-width="0.57"/>')
    rule = ("Chaque état doit rester lisible par le mouvement seul, sans la couleur — l'accessibilité l'exige. "
            "Ces cinq couleurs demeurent réservées à l'interface produit (cf. chapitre 04).")
    t, _ = wrap_text(M, ry + 4, rule, 104, 8.0, lh=12.2, fam=F_SPE, style="italic", fill=N3)
    b.append(t)
    b.append(footer(12, TOTAL))
    return svg_page("\n".join(b))


def _browser(x, y, w, h, dark):
    bg = NOIR if dark else PARCH
    fg = PARCH if dark else NOIR
    acc = OR_L if dark else OR_
    chrome = "#2A2822" if dark else P2
    out = []
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}" stroke="{P4}" stroke-width="0.8"/>')
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="13" fill="{chrome}"/>')
    for i in range(3):
        out.append(f'<circle cx="{x + 9 + i * 7}" cy="{y + 6.5}" r="1.8" fill="{N4}"/>')
    ny = y + 28
    out.append(icons.icon("boat", "rest", acc, x + 11, ny - 9, 13))
    out.append(T(x + 28, ny + 1.5, "CHARON", 6.2, F_CIN_S, fg, ls=1.3))
    for i, l in enumerate(["PRODUIT", "VERDICTS", "TARIFS"]):
        out.append(T(x + w - 108 + i * 35, ny + 1.5, l, 4.3, F_MONO, fg, opacity=0.65))
    out.append(f'<line x1="{x + 11}" y1="{ny + 9}" x2="{x + w - 11}" y2="{ny + 9}" stroke="{acc}" stroke-width="0.5" opacity="0.5"/>')
    hy = ny + 31
    out.append(T(x + w / 2, hy, "La traversée", 14, F_CIN_S, fg, anchor="middle"))
    out.append(T(x + w / 2, hy + 16, "sous bonne garde", 14, F_CIN_S, fg, anchor="middle"))
    out.append(T(x + w / 2, hy + 29.5, "Chaque pièce jointe paie son passage en preuves.", 5.3, F_SPE, fg, anchor="middle", opacity=0.8))
    bw, bh = 86, 14
    bx, by = x + w / 2 - bw / 2, hy + 38
    out.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="{acc}"/>')
    out.append(T(x + w / 2, by + 9.5, "AJOUTER AU NAVIGATEUR", 4.3, F_CIN_S, NOIR, anchor="middle", ls=0.7))
    vy = by + 24
    out.append(f'<rect x="{x + w / 2 - 43}" y="{vy}" width="86" height="11.5" fill="none" stroke="{VERT}" stroke-width="0.6"/>')
    out.append(f'<circle cx="{x + w / 2 - 36}" cy="{vy + 5.7}" r="1.6" fill="{VERT}"/>')
    out.append(T(x + w / 2 - 30, vy + 7.6, "AUTORISÉ · facture_Q3.pdf", 4.3, F_MONO, VERT))
    mu = 2.2
    n = int((w - 22) / (5 * mu))
    out.append(meander(x + 11, y + h - 18, mu, n, acc))
    return "\n".join(out)


def page_site():
    b = [header("11", "Le site web", "DÉCLINAISON DIGITALE")]
    b.append(page_title("Le site web"))
    t, yy = lede("La vitrine publique parle la même langue que le papier : Cinzel pour les titres, Spectral "
                 "pour le corps, la grecque en filet. Deux thèmes, une seule voix.")
    b.append(t)

    y0 = yy + 28
    mw = (CW - 20) / 2
    mh = 186
    b.append(_browser(M, y0, mw, mh, dark=False))
    b.append(_browser(M + mw + 20, y0, mw, mh, dark=True))
    b.append(T(M, y0 + mh + 14, "Thème clair — le support par défaut.", 7.7, F_SPE_M, N3))
    b.append(T(M + mw + 20, y0 + mh + 14, "Thème sombre — sur préférence système uniquement.", 7.7, F_SPE_M, N3))

    y1 = y0 + mh + 40
    b.append(gold_overline(M, y1, "JETONS DE COULEUR"))
    rows = [
        ("THÈME", "FOND", "TEXTE", "ACCENT"),
        ("Clair", "#F4F1E8", "#1C1B16", "#B08D57"),
        ("Sombre", "#1C1B16", "#F4F1E8", "#C7A66E"),
    ]
    ty = y1 + 18
    cols = [M, M + 100, M + 226, M + 352]
    for r_i, (a, c1, c2, c3) in enumerate(rows):
        if r_i == 0:
            for x, v in zip(cols, (a, c1, c2, c3)):
                b.append(T(x, ty, v, 6.1, F_MONO, N4, ls=0.7))
            b.append(f'<line x1="{M}" y1="{ty + 6.5}" x2="{CR}" y2="{ty + 6.5}" stroke="{P3}" stroke-width="0.5"/>')
        else:
            b.append(T(cols[0], ty, a, 9.0, F_SPE_M, NOIR))
            for x, v in zip(cols[1:], (c1, c2, c3)):
                b.append(f'<rect x="{x}" y="{ty - 7.5}" width="9" height="9" fill="{v}" stroke="{P4}" stroke-width="0.5"/>')
                b.append(T(x + 14, ty, v, 7.4, F_MONO, N2))
        ty += 21

    note = ("L'or antique manque de contraste sur fond sombre : le thème sombre emploie la nuance claire "
            "#C7A66E du nuancier — jamais une teinte nouvelle. Le fond sombre est le noir profond de la "
            "charte, jamais un noir pur #000000.")
    t, ty2 = wrap_text(M, ty + 4, note, 104, 8.0, lh=12.2, fam=F_SPE, style="italic", fill=N3)
    b.append(t)

    y2 = ty2 + 28
    b.append(gold_overline(M, y2, "RÈGLES"))
    rules = [
        "Le contraste texte / fond respecte au minimum 4,5:1 — l'or n'écrit jamais un paragraphe.",
        "Les icônes d'état et leurs couleurs n'apparaissent que dans la démonstration produit.",
        "La grecque tient lieu de filet de section ; une frise au plus par écran.",
        "Le passage clair / sombre suit la préférence du système — jamais imposé, toujours réversible.",
    ]
    ry = y2 + 18
    for r in rules:
        b.append(T(M, ry, "—", 8.8, F_SPE_M, OR_HEAD))
        t, ry2 = wrap_text(M + 16, ry, r, 100, 8.5, lh=13)
        b.append(t)
        ry = ry2 + 16
    b.append(footer(13, TOTAL))
    return svg_page("\n".join(b))


def page_interdits():
    b = [header("12", "Les interdits", "CLÔTURE")]
    b.append(page_title("Les interdits"))
    t, yy = lede("Cette liste n'est pas exhaustive — elle protège l'esprit du système, pas la lettre.")
    b.append(t)

    items = [
        "Ajouter une quatrième teinte — même un gris neutre, même un bleu « technique ».",
        "Remplir l'iris ou les paupières du symbole — seule la pupille reste pleine.",
        "Appliquer une ombre portée, un dégradé ou un effet de profondeur sur le symbole.",
        "Mélanger plus de deux graisses de Cinzel sur un même support.",
        "Utiliser les couleurs de verdict (vert, ambre, rouge) hors de l'interface produit.",
        "Enfermer le logotype dans un cartouche, une forme fermée ou une bordure décorative.",
        "Étirer la grecque en hauteur ou l'employer en fond pleine page — c'est un filet, pas une tapisserie.",
        "Inventer un sixième état d'icône, ou animer hors de la grammaire du mouvement.",
        "Recadrer une gravure dans le vif du sujet, ou la remplacer par une photographie couleur.",
        "Employer l'or antique pour du texte courant sur fond sombre — la nuance #C7A66E s'y substitue.",
    ]
    y0 = yy + 40
    col_w = (CW - 34) / 2
    col_y = [y0, y0]
    for i, it in enumerate(items):
        col = i % 2
        x = M + col * (col_w + 34)
        y = col_y[col]
        b.append(T(x, y, "×", 11, F_SPE_S, OR_HEAD))
        t, y_end = wrap_text(x + 16, y, it, 52, 8.5, lh=13)
        b.append(t)
        b.append(f'<line x1="{x + 16}" y1="{y_end + 12}" x2="{x + col_w - 10}" y2="{y_end + 12}" stroke="{P3}" stroke-width="0.4"/>')
        col_y[col] = y_end + 34

    cy = 672
    mu = 3.2
    n = 8
    total_w = (n * 5 + 1) * mu
    b.append(meander(W / 2 - total_w / 2, cy - 32, mu, n, OR_))
    b.append(T(W / 2, cy + 10, "CHARON", 14, F_CIN_S, NOIR, ls=5.5, anchor="middle"))
    b.append(T(W / 2, cy + 27, "GUIDE DE MARQUE · VERSION 2.0", 6.1, F_MONO, N3, ls=1.1, anchor="middle"))
    b.append(T(W / 2, cy + 41, "Document interne · Usage confidentiel · 2026", 7.1, F_SPE, N4, anchor="middle", style="italic"))
    b.append(footer(14, TOTAL))
    return svg_page("\n".join(b))


PAGES = {
    "02_sommaire": page_sommaire,
    "10_motif": page_motif,
    "11_iconographie": page_iconographie,
    "12_icones": page_icones,
    "13_site": page_site,
    "14_interdits": page_interdits,
}

if __name__ == "__main__":
    import cairosvg, sys, os
    os.makedirs("out", exist_ok=True)
    only = sys.argv[1:] or PAGES.keys()
    for name in only:
        svg = PAGES[name]()
        with open(f"out/{name}.svg", "w") as f:
            f.write(svg)
        cairosvg.svg2pdf(bytestring=svg.encode(), write_to=f"out/{name}.pdf", dpi=72)
        cairosvg.svg2png(bytestring=svg.encode(), write_to=f"out/{name}.png", scale=1.2)
        print("ok", name)
