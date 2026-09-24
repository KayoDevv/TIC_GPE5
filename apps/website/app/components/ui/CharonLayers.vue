<script setup lang="ts">
const LAYERS = [
  { numeral: "I", label: "STATIQUE", sub: "entropie & structure PE", sla: "< 500 ms" },
  { numeral: "II", label: "SANDBOX", sub: "détonation isolée", sla: "< 120 s" },
  { numeral: "III", label: "SÉMANTIQUE", sub: "lecture du contexte", sla: "3–5 s" },
];

const FILLS = ["var(--card)", "var(--bg-alt)", "var(--card-inset)"];

const root = ref<HTMLElement | null>(null);
const inView = useInView(root, { once: true, margin: "-60px" });

const stack = computed(() =>
  [2, 1, 0].map((index) => ({
    ...LAYERS[index]!,
    index,
    y0: 30 + index * 62,
    fill: FILLS[index]!,
    enterDelay: (2 - index) * 0.16,
    floatDelay: index * 0.7,
    floatDuration: 5 + index * 0.9,
  })),
);
</script>

<template>
  <svg
    ref="root"
    class="w-full"
    viewBox="0 0 340 300"
    role="img"
    aria-label="Les trois couches d'analyse de Charon : statique, sandbox, sémantique — empilées au-dessus du verdict"
  >
    <g
      v-for="layer in stack"
      :key="layer.label"
      class="layer-enter"
      :class="{ 'layer-enter--visible': inView }"
      :style="{ transitionDelay: `${layer.enterDelay}s` }"
    >
      <g
        class="layer-float"
        :style="{
          animationDuration: `${layer.floatDuration}s`,
          animationDelay: `${layer.floatDelay}s`,
        }"
      >
        <path
          :d="`M50 ${layer.y0 + 36} L170 ${layer.y0 + 72} L170 ${layer.y0 + 85} L50 ${layer.y0 + 49} Z`"
          fill="var(--border)"
          stroke="var(--gold-deep)"
          stroke-opacity="0.45"
          stroke-width="0.8"
        />
        <path
          :d="`M170 ${layer.y0 + 72} L290 ${layer.y0 + 36} L290 ${layer.y0 + 49} L170 ${layer.y0 + 85} Z`"
          fill="var(--border)"
          stroke="var(--gold-deep)"
          stroke-opacity="0.45"
          stroke-width="0.8"
        />
        <path
          :d="`M170 ${layer.y0} L290 ${layer.y0 + 36} L170 ${layer.y0 + 72} L50 ${layer.y0 + 36} Z`"
          :fill="layer.fill"
          stroke="var(--gold-deep)"
          stroke-opacity="0.6"
          stroke-width="0.9"
        />
        <text
          x="170"
          :y="layer.y0 + 34"
          text-anchor="middle"
          font-family="'Space Mono', monospace"
          font-size="11"
          font-weight="700"
          letter-spacing="0.12em"
          fill="var(--text-2)"
        >
          <tspan fill="var(--gold-deep)">{{ layer.numeral }}</tspan>
          <tspan dx="8">{{ layer.label }}</tspan>
        </text>
        <text x="170" :y="layer.y0 + 49" text-anchor="middle" font-size="9">
          <tspan font-family="'Spectral', serif" font-style="italic" fill="var(--faint)">
            {{ layer.sub }}
          </tspan>
          <tspan
            dx="7"
            font-family="'Space Mono', monospace"
            font-size="7.5"
            fill="var(--gold-deep)"
          >
            {{ layer.sla }}
          </tspan>
        </text>
      </g>
    </g>

    <g class="verdict-enter" :class="{ 'verdict-enter--visible': inView }">
      <line
        x1="170"
        y1="242"
        x2="170"
        y2="262"
        stroke="var(--gold-deep)"
        stroke-opacity="0.5"
        stroke-width="0.9"
        stroke-dasharray="2 3"
      />
      <circle cx="170" cy="272" r="5" fill="var(--gold)" />
      <text
        x="170"
        y="292"
        text-anchor="middle"
        font-family="'Space Mono', monospace"
        font-size="9"
        letter-spacing="0.14em"
        fill="var(--faint)"
      >
        VERDICT
        <tspan fill="var(--gold-deep)" font-size="7.5">· saga · redis</tspan>
      </text>
    </g>
  </svg>
</template>

<style scoped>
.layer-enter {
  opacity: 0;
  transform: translateY(-26px);
  transition:
    opacity 0.55s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}
.layer-enter--visible {
  opacity: 1;
  transform: translateY(0);
}

.layer-float {
  animation-name: layer-bob;
  animation-iteration-count: infinite;
  animation-timing-function: ease-in-out;
}
@keyframes layer-bob {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-3px);
  }
}

.verdict-enter {
  opacity: 0;
  transition: opacity 0.5s ease 0.65s;
}
.verdict-enter--visible {
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .layer-enter,
  .verdict-enter {
    opacity: 1;
    transform: none;
    transition: none;
  }
  .layer-float {
    animation: none;
  }
}
</style>