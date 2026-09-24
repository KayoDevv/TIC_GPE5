<script setup lang="ts">
const RIVER_PATH =
  "M50 0 C 66 96 80 210 78 330 C 76 452 34 542 24 660 C 16 786 42 918 50 1000";
const PATH_LENGTH = 1000;
const WAKE_OVERSHOOT = -40;
const BOAT_MAX_T = 0.997;

const progress = useScrollProgress();
const rootEl = ref<HTMLDivElement | null>(null);
const pathEl = ref<SVGPathElement | null>(null);
const boatEl = ref<HTMLDivElement | null>(null);
const fogEl = ref<HTMLDivElement | null>(null);
const riverHeight = ref<number | null>(null);
const endFraction = ref(1);

function clamp01(value: number): number {
  return Math.min(Math.max(value, 0), 1);
}

function measure(): void {
  const target = document.querySelector<HTMLElement>("[data-river-end]");
  if (!target) return;
  const end = target.getBoundingClientRect().bottom + window.scrollY;
  const scrollable =
    document.documentElement.scrollHeight - window.innerHeight;
  riverHeight.value = Math.round(end);
  endFraction.value =
    scrollable > 0
      ? clamp01((end - window.innerHeight) / scrollable) || 0.05
      : 1;
}

function renderFrame(): void {
  const root = rootEl.value;
  const path = pathEl.value;
  if (!root || !path) return;
  const t = clamp01(progress.value / endFraction.value);
  const dash = PATH_LENGTH - (PATH_LENGTH - WAKE_OVERSHOOT) * t;
  root.style.setProperty("--dash", String(dash));
  const boatT = Math.min(t, BOAT_MAX_T);
  const point = path.getPointAtLength(boatT * path.getTotalLength());
  positionAtPoint(boatEl.value, point);
  positionAtPoint(fogEl.value, point);
}

function positionAtPoint(
  el: HTMLElement | null,
  point: { x: number; y: number },
): void {
  if (!el) return;
  el.style.left = `${point.x}%`;
  el.style.top = `${point.y / 10}%`;
}

onMounted(() => {
  measure();
  renderFrame();
  window.setTimeout(() => {
    measure();
    renderFrame();
  }, 700);
  window.addEventListener("resize", measure, { passive: true });
});

onUnmounted(() => {
  window.removeEventListener("resize", measure);
});

watch(progress, renderFrame);
</script>

<template>
  <div
    ref="rootEl"
    class="river pointer-events-none absolute inset-x-0 top-0 -z-10 overflow-hidden"
    aria-hidden="true"
    :style="{ height: riverHeight ? `${riverHeight}px` : '100%' }"
  >
    <svg class="h-full w-full" viewBox="0 0 100 1000" preserveAspectRatio="none">
      <defs>
        <linearGradient id="styx-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="var(--gold-2)" stop-opacity="0" />
          <stop offset="0.06" stop-color="var(--gold)" stop-opacity="1" />
          <stop offset="0.94" stop-color="var(--gold-deep)" stop-opacity="1" />
          <stop offset="1" stop-color="var(--gold-deep)" stop-opacity="0" />
        </linearGradient>
        <filter id="styx-wc" x="-40%" y="-2%" width="180%" height="104%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.8 0.009"
            numOctaves="3"
            seed="9"
            result="n"
          />
          <feDisplacementMap
            in="SourceGraphic"
            in2="n"
            scale="3.5"
            xChannelSelector="R"
            yChannelSelector="G"
          />
          <feGaussianBlur stdDeviation="0.5" />
        </filter>
        <filter id="styx-mist" x="-60%" y="-3%" width="220%" height="106%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.5 0.012"
            numOctaves="2"
            seed="4"
            result="m"
          />
          <feDisplacementMap in="SourceGraphic" in2="m" scale="6" />
          <feGaussianBlur stdDeviation="3.4" />
        </filter>
        <filter id="styx-soft"><feGaussianBlur stdDeviation="1.1" /></filter>
      </defs>

      <path
        :d="RIVER_PATH"
        :pathLength="PATH_LENGTH"
        fill="none"
        stroke="url(#styx-grad)"
        stroke-width="46"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
        filter="url(#styx-mist)"
        opacity="0.07"
      />
      <path
        :d="RIVER_PATH"
        :pathLength="PATH_LENGTH"
        fill="none"
        stroke="url(#styx-grad)"
        stroke-width="22"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
        filter="url(#styx-wc)"
        opacity="0.11"
      />
      <path
        :d="RIVER_PATH"
        :pathLength="PATH_LENGTH"
        fill="none"
        stroke="var(--bg)"
        stroke-width="13"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
        filter="url(#styx-soft)"
        opacity="0.85"
      />
      <path
        :d="RIVER_PATH"
        :pathLength="PATH_LENGTH"
        fill="none"
        stroke="url(#styx-grad)"
        stroke-width="2"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
        opacity="0.13"
      />

      <!-- The wake repaints on every scroll frame: an SVG filter here drops frames. -->
      <path
        ref="pathEl"
        class="wake wake--wide"
        :d="RIVER_PATH"
        :pathLength="PATH_LENGTH"
        fill="none"
        stroke="url(#styx-grad)"
        stroke-width="20"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
        opacity="0.07"
      />
      <path
        class="wake wake--mid"
        :d="RIVER_PATH"
        :pathLength="PATH_LENGTH"
        fill="none"
        stroke="url(#styx-grad)"
        stroke-width="8"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
        opacity="0.15"
      />
      <path
        class="wake wake--core"
        :d="RIVER_PATH"
        :pathLength="PATH_LENGTH"
        fill="none"
        stroke="url(#styx-grad)"
        stroke-width="2.5"
        stroke-linecap="round"
        vector-effect="non-scaling-stroke"
        opacity="0.26"
      />
    </svg>

    <div ref="fogEl" class="fog absolute -translate-x-1/2 -translate-y-1/2" />
    <div
      ref="boatEl"
      class="absolute -translate-x-1/2 -translate-y-1/2"
      style="left: 56%; top: 0"
    >
      <svg width="26" height="26" viewBox="0 0 13 13" fill="none" style="opacity: 0.55">
        <path
          d="M2 8C4.3 9.6 5.4 10.4 6.5 10.4S8.7 9.6 11 8"
          stroke="var(--gold-deep)"
          stroke-width="0.9"
          fill="none"
        />
        <path
          d="M6.5 2L5.2 6.2H7.8Z"
          stroke="var(--gold-deep)"
          stroke-width="0.9"
          fill="none"
        />
      </svg>
    </div>
  </div>
</template>

<style scoped>
.river {
  --dash: 1000;
  -webkit-mask-image: linear-gradient(180deg, #000 84%, transparent 100%);
  mask-image: linear-gradient(180deg, #000 84%, transparent 100%);
}

.wake {
  stroke-dasharray: 1000;
}
.wake--wide {
  stroke-dashoffset: calc(var(--dash) * 1px);
}
.wake--mid {
  stroke-dashoffset: calc((var(--dash) + 55) * 1px);
}
.wake--core {
  stroke-dashoffset: calc((var(--dash) + 115) * 1px);
}

.fog {
  left: 50%;
  top: 0;
  width: 300px;
  height: 220px;
  background: radial-gradient(
    ellipse at center,
    color-mix(in srgb, var(--bg) 88%, transparent) 0%,
    color-mix(in srgb, var(--bg) 55%, transparent) 38%,
    transparent 72%
  );
}
</style>