# -*- coding: utf-8 -*-
"""Icônes d'état statiques — portage SVG des composants de la landing (viewBox 48)."""

def _g(inner, transform=None, opacity=None):
    a = ""
    if transform: a += f' transform="{transform}"'
    if opacity is not None: a += f' opacity="{opacity}"'
    return f"<g{a}>{inner}</g>"

def _cross(c, sw=2.6):
    return (f'<line x1="16" y1="16" x2="32" y2="32" stroke="{c}" stroke-width="{sw}" stroke-linecap="round"/>'
            f'<line x1="32" y1="16" x2="16" y2="32" stroke="{c}" stroke-width="{sw}" stroke-linecap="round"/>')

def eye(state, c):
    lid = f'<path d="M3 24 C 14 11, 34 11, 45 24 C 34 37, 14 37, 3 24 Z" fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>'
    if state == "threat":
        return lid + _cross(c)
    cx = 32 if state == "scan" else 24
    filled = state == "clear"
    r = 6.5 if filled else 6
    iris = f'<circle cx="{cx}" cy="24" r="{r}" fill="{c if filled else "none"}" stroke="{c}" stroke-width="2"/>'
    pup = "" if filled else f'<circle cx="{cx}" cy="24" r="2.4" fill="{c}"/>'
    inner = lid + iris + pup
    if state == "suspect":
        return _g(inner, transform="translate(0 24) scale(1 0.62) translate(0 -24)")
    return inner

def boat(state, c):
    sinking = state == "threat"
    filled = state == "clear"
    sail = (f'<path d="M24 5 C20.5 11 18.6 17.5 18.1 25.5 L29.9 25.5 C29.4 17.5 27.5 11 24 5 Z '
            f'M24 12.5 L27 18.5 L24 24 L21 18.5 Z" fill-rule="evenodd" '
            f'fill="{c if filled else "none"}" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>')
    hull = (f'<path d="M6 20.5 C7 17.5 10.5 17.5 11.5 20.5 C13.5 26.5 18 30 24 30 C30 30 34.5 26.5 36.5 20.5 '
            f'C37.5 17.5 41 17.5 42 20.5 C40.5 29.5 33 35.5 24 35.5 C15 35.5 7.5 29.5 6 20.5 Z" '
            f'fill="{c if filled else "none"}" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>')
    body = sail + hull
    if sinking:
        ship = _g(body, transform="translate(0 12) rotate(-18 24 24)", opacity="0.45")
        bubbles = "".join(f'<circle cx="{x}" cy="{y}" r="1.6" fill="none" stroke="{c}" stroke-width="1.2" opacity="{o}"/>'
                          for x, y, o in [(18, 30, 0.75), (25, 25, 0.55), (31, 21, 0.4)])
        wave = f'<path d="M3 38 Q9 33 15 38 T27 38 T39 38 T51 38" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round" opacity="0.75"/>'
        return ship + bubbles + wave
    rot = {"rest": -3.5, "scan": 3, "suspect": -7, "clear": 0}[state]
    ship = _g(body, transform=f"rotate({rot} 24 24)") if rot else body
    wave = f'<path d="M4 41 Q10 38 16 41 T28 41 T40 41 T52 41" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" opacity="0.75"/>'
    return ship + wave

def virus(state, c):
    import math
    filled = state == "clear"
    spikes = ""
    for i in range(8):
        a = i / 8 * 2 * math.pi
        x1, y1 = 24 + math.cos(a) * 9, 24 + math.sin(a) * 9
        x2, y2 = 24 + math.cos(a) * 16, 24 + math.sin(a) * 16
        spikes += (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{c}" stroke-width="2" stroke-linecap="round"/>'
                   f'<circle cx="{x2:.1f}" cy="{y2:.1f}" r="2" fill="{c}"/>')
    core = f'<circle cx="24" cy="24" r="9" fill="{c if filled else "none"}" stroke="{c}" stroke-width="2"/>'
    dots = "" if filled else (f'<circle cx="21" cy="22" r="1.6" fill="{c}"/>'
                              f'<circle cx="27" cy="26" r="1.6" fill="{c}"/>'
                              f'<circle cx="25" cy="20" r="1.2" fill="{c}"/>')
    inner = spikes + core + dots
    if state == "suspect":
        return _g(inner, transform="rotate(6 24 24)")
    if state == "threat":
        return _g(inner, transform="scale(1.1) translate(-2.2 -2.2)")
    return inner

def ring(state, c):
    if state == "rest":
        return f'<circle cx="24" cy="24" r="12" fill="none" stroke="{c}" stroke-width="2.4"/>'
    if state == "scan":
        return (f'<circle cx="24" cy="24" r="12" fill="none" stroke="{c}" stroke-width="2.4" opacity="0.25"/>'
                f'<path d="M24 12 A 12 12 0 0 1 36 24" fill="none" stroke="{c}" stroke-width="2.6" stroke-linecap="round"/>')
    if state == "suspect":
        return (f'<circle cx="24" cy="24" r="12" fill="none" stroke="{c}" stroke-width="2.4" stroke-dasharray="4 5"/>'
                f'<line x1="24" y1="17" x2="24" y2="26" stroke="{c}" stroke-width="2.6" stroke-linecap="round"/>'
                f'<circle cx="24" cy="30.5" r="1.7" fill="{c}"/>')
    if state == "clear":
        return f'<circle cx="24" cy="24" r="12" fill="{c}"/>'
    return (f'<circle cx="24" cy="24" r="12" fill="none" stroke="{c}" stroke-width="2.4"/>' + _cross(c))

def lantern(state, c):
    handle = f'<path d="M18 11 Q24 3 30 11" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
    body = f'<path d="M17.5 11 L30.5 11 L33 33.5 Q24 37.5 15 33.5 Z" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
    flame_d = "M24 17.5 C27.5 22 28.5 25.5 24 29.5 C19.5 25.5 20.5 22 24 17.5 Z"
    base = handle + body
    if state == "threat":
        smoke = f'<path d="M24 29 C26.5 25.5 21.5 22.5 24 18.5" fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" opacity="0.6"/>'
        bar = f'<line x1="21" y1="31" x2="27" y2="31" stroke="{c}" stroke-width="2.2" stroke-linecap="round"/>'
        return base + smoke + bar
    if state == "scan":
        halo = f'<circle cx="24" cy="24" r="14" fill="none" stroke="{c}" stroke-width="1.4" opacity="0.35"/>'
        flame = f'<path d="{flame_d}" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round" transform="translate(1.2 0)"/>'
        return base + halo + flame
    if state == "suspect":
        flame = f'<path d="{flame_d}" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round" opacity="0.45" transform="translate(0 24) scale(0.88) translate(0 -24) translate(3.2 0)"/>'
        return base + flame
    fill = c if state == "clear" else "none"
    flame = f'<path d="{flame_d}" fill="{fill}" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>'
    return base + flame

SHAPES = {"eye": eye, "boat": boat, "virus": virus, "ring": ring, "lantern": lantern}

def icon(shape, state, color, x, y, size):
    s = size / 48.0
    inner = SHAPES[shape](state, color)
    return f'<g transform="translate({x} {y}) scale({s})">{inner}</g>'
