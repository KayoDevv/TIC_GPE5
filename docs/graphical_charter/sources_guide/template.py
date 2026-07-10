# -*- coding: utf-8 -*-
"""Gabarit commun — métriques calquées sur le PDF original."""

W, H = 595.28, 841.89
M = 56.7                       # marge de contenu
CR = 538.6                     # bord droit du contenu
CW = CR - M                    # 481.9

OR_   = "#B08D57"; OR_HEAD = "#936F3C"
NOIR  = "#1C1B16"
PARCH = "#F4F1E8"
OR_D  = "#936F3C"; OR_DD = "#7A5E32"; OR_L = "#C7A66E"; OR_LL = "#E0C68C"
N2 = "#3E3A30"; N3 = "#6B6552"; N4 = "#8A8170"; N5 = "#ABA28C"
P2 = "#ECE7DA"; P3 = "#DED7C5"; P4 = "#C9C0A9"; P0 = "#FBF9F3"
VERT = "#3F6F5E"; AMBRE = "#B07D24"; ROUGE = "#A8322A"

F_CIN_R = "Cinzel Regular"
F_CIN_M = "Cinzel Medium"
F_CIN_S = "Cinzel SemiBold"
F_CIN_B = "Cinzel Bold"
F_SPE   = "Spectral"
F_SPE_L = "Spectral Light"
F_SPE_M = "Spectral Medium"
F_SPE_S = "Spectral SemiBold"
F_MONO  = "Space Mono"

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def T(x, y, s, size=8.8, fam=F_SPE_M, fill=N2, ls=0, anchor="start",
      weight=None, style=None, opacity=None):
    if ls:
        s = s.replace(" ", "\u00A0")
    a = f'x="{x}" y="{y}" font-family="{fam}" font-size="{size}" fill="{fill}"'
    if ls: a += f' letter-spacing="{ls}"'
    if anchor != "start": a += f' text-anchor="{anchor}"'
    if weight: a += f' font-weight="{weight}"'
    if style: a += f' font-style="{style}"'
    if opacity is not None: a += f' opacity="{opacity}"'
    return f'<text {a}>{esc(s)}</text>'

def wrap_text(x, y, s, width_chars, size=8.8, lh=None, fam=F_SPE_M, fill=N2,
              anchor="start", style=None):
    import textwrap
    lh = lh or size * 1.55
    lines = textwrap.wrap(s, width_chars)
    out = [T(x, y + i * lh, line, size, fam, fill, anchor=anchor, style=style)
           for i, line in enumerate(lines)]
    return "\n".join(out), y + (len(lines) - 1) * lh

def header(num, title, right_label):
    left = f"{num} — {title.upper()}" if num else title.upper()
    return f'''
{T(M, 64.9, left, 6.8, F_CIN_R, OR_HEAD, ls=1.7)}
{T(CR, 64.9, right_label.upper(), 6.8, F_MONO, N3, ls=0.35, anchor="end")}
<line x1="{M}" y1="69.5" x2="{CR}" y2="69.5" stroke="{P4}" stroke-width="0.57"/>
'''

def footer(page, total=14):
    return f'''
<line x1="{M}" y1="779.5" x2="{CR}" y2="779.5" stroke="{P4}" stroke-width="0.57"/>
{T(M, 793.1, "CHARON — GUIDE DE MARQUE", 6.1, F_CIN_R, N3, ls=1.9)}
{T(538.9, 793.1, f"{page:02d} / {total}", 6.1, F_MONO, N3, anchor="end")}
'''

def page_title(txt):
    return (T(M, 128.1, txt, 24.4, F_CIN_S, NOIR, ls=0.4) +
            f'<line x1="{M}" y1="133.2" x2="{CR}" y2="133.2" stroke="{OR_}" stroke-width="1.13"/>')

def lede(txt, y=162.9, width=100):
    return wrap_text(M, y, txt, width, 9.1, lh=14.3, fam=F_SPE, fill=N2, style="italic")

def gold_overline(x, y, txt, anchor="start", rule=False):
    s = T(x, y, txt.upper(), 7.4, F_CIN_R, OR_HEAD, ls=1.9, anchor=anchor)
    if rule:
        s += f'<line x1="{M}" y1="{y + 7}" x2="{CR}" y2="{y + 7}" stroke="{P4}" stroke-width="0.5"/>'
    return s

def svg_page(body):
    rules = []
    y = 11.4
    while y < H:
        rules.append(f'<line x1="17" y1="{y:.1f}" x2="578.3" y2="{y:.1f}" stroke="{P3}" stroke-width="0.17"/>')
        y += 14.17
    frame = f'<rect x="34" y="34" width="527.3" height="773.9" fill="none" stroke="{OR_}" stroke-width="0.99"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<rect width="{W}" height="{H}" fill="{PARCH}"/>
{"".join(rules)}
{frame}
{body}
</svg>'''
