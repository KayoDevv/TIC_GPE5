<script setup lang="ts">
const steps = [
  'Download the archive and unzip it.',
  'Open chrome://extensions (or edge://extensions).',
  'Enable Developer mode, top right.',
  'Click Load unpacked and select the unzipped folder.'
];
</script>

<template>
  <div class="page">
    <NuxtRouteAnnouncer />

    <main class="shell">
      <header class="head">
        <p class="eyebrow">Zero-trust file analysis</p>
        <h1>Charon</h1>
        <p class="lede">
          Drop an attachment in the popup, get a verdict: static analysis, behavioural
          detonation in an isolated sandbox, and a plain-language explanation.
        </p>
      </header>

      <a class="download" href="/charon-extension.zip" download>
        Download the extension
        <span class="hint">Chrome &amp; Edge · Manifest V3</span>
      </a>

      <section class="install">
        <h2>Install it</h2>
        <ol>
          <li v-for="(step, index) in steps" :key="index">{{ step }}</li>
        </ol>
        <p class="note">
          Chrome only installs unpacked extensions from the Web Store, so Developer
          mode is required for this build.
        </p>
      </section>
    </main>
  </div>
</template>

<style>
:root {
  color-scheme: dark;
  --ink: #e9edf5;
  --muted: #9aa4b8;
  --bg: #0b0e14;
  --glass: rgba(255, 255, 255, 0.04);
  --edge: rgba(255, 255, 255, 0.09);
  --accent: #5aa9ff;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: radial-gradient(120% 90% at 50% 0%, #16203a 0%, var(--bg) 60%);
  color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.55;
}

.page {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  padding: 4rem 1.5rem;
}

.shell {
  width: 100%;
  max-width: 40rem;
  display: flex;
  flex-direction: column;
  gap: 2.5rem;
}

.eyebrow {
  margin: 0 0 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 0.72rem;
  color: var(--accent);
}

h1 {
  margin: 0 0 0.75rem;
  font-size: clamp(2.5rem, 8vw, 3.5rem);
  letter-spacing: -0.02em;
}

.lede { margin: 0; color: var(--muted); }

.download {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 1.15rem 1.5rem;
  border: 1px solid var(--edge);
  border-radius: 14px;
  background: var(--glass);
  backdrop-filter: blur(12px);
  color: var(--ink);
  font-size: 1.05rem;
  font-weight: 600;
  text-decoration: none;
  transition: border-color 160ms ease, transform 160ms ease;
}

.download:hover {
  border-color: var(--accent);
  transform: translateY(-1px);
}

.hint {
  font-size: 0.78rem;
  font-weight: 400;
  color: var(--muted);
}

.install h2 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--muted);
}

.install ol {
  margin: 0;
  padding-left: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.note {
  margin: 1rem 0 0;
  font-size: 0.85rem;
  color: var(--muted);
}
</style>
