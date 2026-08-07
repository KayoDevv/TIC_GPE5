# Website — Charon marketing site

Public marketing site for Charon, the browser extension that inspects every
attachment before it reaches the disk. Static-generated, no runtime backend.

Stack: **Nuxt 4** · **Vue 3** · **Tailwind 4** · **TypeScript (strict)**

---

## Commands

```bash
npm install          # install dependencies
npm run dev          # dev server on http://localhost:3000
npm run build        # production build (runs vue-tsc typecheck)
npm run generate     # static generation
npm run preview      # serve the production build
```

`vue-tsc` runs in strict mode on every build — a type error fails the build.

---

## Structure

```
app/
├── app.vue                  # shell: frise, river, navbar, page, footer
├── pages/
│   └── index.vue            # composes the sections, nothing else
├── components/
│   ├── layout/              # FriseRibbon, RiverStyx, TheNavbar, TheFooter
│   ├── sections/            # one component per page section
│   ├── demo/                # interactive browser demo
│   ├── icons/               # the shape × state icon system
│   ├── motion/              # reusable animation primitives
│   └── ui/                  # presentational building blocks
├── composables/             # useTheme, useInView, scroll progress, icon cycle
├── types/                   # shared domain types
├── utils/                   # pure helpers, auto-imported
└── assets/css/              # main → tokens → base
```

Nuxt auto-imports components with a directory prefix: `layout/TheNavbar.vue`
becomes `<LayoutTheNavbar>`, `icons/AnimatedIcon.vue` becomes
`<IconsAnimatedIcon>`.

---

## Design tokens

Two themes live in `assets/css/tokens.css` as CSS custom properties under
`.theme-light` and `.theme-dark`. Components never hardcode a colour — they
read `var(--text)`, `var(--gold)`, `var(--card)` and so on, which means a
single component covers both themes.

`useTheme()` holds the active mode and exposes the class applied on the root
element in `app.vue`.

Product verdict colours (`--safe`, `--warn`, `--danger`) belong to the
extension interface. On the site they appear only inside the product
demonstration.

---

## Animation

No animation library. Every effect is CSS keyframes or transitions driven by a
small composable, which keeps transform and opacity work on the compositor and
the bundle minimal.

- `useInView` — IntersectionObserver, fires once by default
- `useScrollProgress` — page scroll, rAF-throttled
- `useElementScrollProgress` — progress through one tall element (sticky sections)

Primitives in `components/motion/` wrap these: `ScrollReveal` (fade-up on
enter), `SplitText` (word-by-word reveal), `DecryptText` (scrambled glyphs
resolving left to right), `StaggerGrid` (radial dot pulse).

Every animated component honours `prefers-reduced-motion: reduce`.

---

## The icon system

Five shapes — eye, boat, virus, ring, lantern — each rendered across five
states: rest, scan, suspect, clear, threat. `AnimatedIcon` dispatches to a
shape component; the shape reads `data-state` and picks its choreography.

Each state has its own grammar of motion: slow and regular at rest, continuous
and directed while scanning, hesitant under suspicion, still and filled when
clear, broken on threat. States must stay legible without colour.

`stateColor()` maps a state to its token. Pass `color` to `AnimatedIcon` to
override it, which the demo chips use to stay readable on a filled background.

---

## Conventions

Repository-wide rules in [`docs/CONTRIBUTING.md`](../../docs/CONTRIBUTING.md)
apply here. In particular: English everywhere, one docstring per file, no
explanatory comments inside function bodies, small single-purpose components,
named constants over magic values, and full type annotations.

Section components own their markup and their styles. Data that drives a
section lives in a typed constant at the top of its `<script setup>` rather
than being inlined in the template.

---

## Known gaps

- The extension archive linked by the download buttons
  (`/charon-extension-v2.0.0.zip`) is not committed yet — those links 404.
- No test suite. Vitest would fit the composables and the pure helpers.