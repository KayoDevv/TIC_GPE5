<script setup lang="ts">
const CHANNELS = [
  "M 10 20 h 79.5 q 5 0 5 5 v 30",
  "M 180 10 h -69.7 q -5 0 -5 5 v 30",
  "M 130 20 v 21.8 q 0 5 -5 5 h -10",
  "M 170 80 v -21.8 q 0 -5 -5 -5 h -50",
  "M 135 65 h 15 q 5 0 5 5 v 10 q 0 5 -5 5 h -39.8 q -5 0 -5 -5 v -20",
  "M 94.8 95 v -36",
  "M 88 88 v -15 q 0 -5 -5 -5 h -10 q -5 0 -5 -5 v -5 q 0 -5 5 -5 h 14",
  "M 30 30 h 25 q 5 0 5 5 v 6.5 q 0 5 5 5 h 20",
];

const MASK_PATHS = [
  "M 10 20 h 79.5 q 5 0 5 5 v 24",
  "M 180 10 h -69.7 q -5 0 -5 5 v 24",
  "M 130 20 v 21.8 q 0 5 -5 5 h -10",
  "M 170 80 v -21.8 q 0 -5 -5 -5 h -50",
  "M 135 65 h 15 q 5 0 5 5 v 10 q 0 5 -5 5 h -39.8 q -5 0 -5 -5 v -20",
  "M 94.8 95 v -36",
  "M 88 88 v -15 q 0 -5 -5 -5 h -10 q -5 0 -5 -5 v -5 q 0 -5 5 -5 h 14",
  "M 30 30 h 25 q 5 0 5 5 v 6.5 q 0 5 5 5 h 20",
];

const PULSES = [
  { line: 1, gradient: "arch-brass-grad" },
  { line: 2, gradient: "arch-brass-bright-grad" },
  { line: 6, gradient: "arch-brass-grad" },
  { line: 7, gradient: "arch-brass-bright-grad" },
  { line: 5, gradient: "arch-brass-grad" },
  { line: 3, gradient: "arch-clean-grad" },
  { line: 4, gradient: "arch-suspicious-grad" },
  { line: 8, gradient: "arch-malicious-grad" },
];

const CHIP_PINS = [
  { x: 93, y: 37, transform: undefined },
  { x: 104, y: 37, transform: undefined },
  { x: 116.3, y: 44, transform: "rotate(90 116.25 45.5)" },
  { x: 122.8, y: 44, transform: "rotate(90 116.25 45.5)" },
  { x: 104, y: 16, transform: "rotate(180 105.25 39.5)" },
  { x: 114.5, y: 16, transform: "rotate(180 105.25 39.5)" },
  { x: 80, y: -13.6, transform: "rotate(270 115.25 19.5)" },
  { x: 87, y: -13.6, transform: "rotate(270 115.25 19.5)" },
];
</script>

<template>
  <svg
    width="100%"
    height="100%"
    viewBox="0 0 200 100"
    role="img"
    aria-label="Schéma animé : les spécimens circulent le long de canaux gravés et convergent vers le moteur de verdict"
  >
    <g
      stroke="var(--arch-trace)"
      fill="none"
      stroke-width="0.3"
      stroke-dasharray="100 100"
      path-length="100"
      marker-start="url(#arch-circle-marker)"
    >
      <path
        v-for="(channel, index) in CHANNELS"
        :key="index"
        :d="channel"
        stroke-dasharray="100 100"
        path-length="100"
      />
      <animate
        attributeName="stroke-dashoffset"
        from="100"
        to="0"
        dur="1s"
        fill="freeze"
        calcMode="spline"
        keySplines="0.25,0.1,0.5,1"
        keyTimes="0; 1"
      />
    </g>

    <g
      font-family="'Space Mono', monospace"
      font-size="4"
      letter-spacing="0.12em"
      fill="var(--faint)"
    >
      <text x="10" y="15.5">STATIQUE</text>
      <text x="180" y="5.5" text-anchor="end">SANDBOX</text>
      <text x="30" y="25.5">SÉMANTIQUE</text>
    </g>

    <g v-for="pulse in PULSES" :key="pulse.line" :mask="`url(#arch-mask-${pulse.line})`">
      <circle
        class="arch-pulse"
        :class="`arch-line-${pulse.line}`"
        cx="0"
        cy="0"
        r="8"
        :fill="`url(#${pulse.gradient})`"
      />
    </g>

    <g>
      <g fill="var(--gold-deep)">
        <rect
          v-for="(pin, index) in CHIP_PINS"
          :key="index"
          :x="pin.x"
          :y="pin.y"
          width="2.5"
          height="5"
          rx="0.7"
          :transform="pin.transform"
        />
      </g>
      <rect
        x="85"
        y="40"
        width="30"
        height="20"
        rx="2"
        fill="var(--arch-chip)"
        stroke="var(--gold-deep)"
        stroke-width="0.4"
      />
      <text
        x="100"
        y="52.2"
        text-anchor="middle"
        font-family="'Space Mono', monospace"
        font-size="5"
        font-weight="700"
        letter-spacing="0.08em"
        fill="url(#arch-text-gradient)"
      >
        VERDICT
      </text>
    </g>

    <defs>
      <mask v-for="(path, index) in MASK_PATHS" :id="`arch-mask-${index + 1}`" :key="index">
        <path :d="path" stroke-width="0.5" stroke="white" />
      </mask>

      <radialGradient id="arch-brass-grad" fx="1">
        <stop offset="0%" stop-color="var(--arch-pulse-core)" />
        <stop offset="50%" stop-color="var(--arch-pulse-mid)" />
        <stop offset="100%" stop-color="transparent" />
      </radialGradient>
      <radialGradient id="arch-brass-bright-grad" fx="1">
        <stop offset="0%" stop-color="var(--arch-pulse-bright-core)" />
        <stop offset="50%" stop-color="var(--arch-pulse-bright-mid)" />
        <stop offset="100%" stop-color="transparent" />
      </radialGradient>
      <radialGradient id="arch-clean-grad" fx="1">
        <stop offset="0%" stop-color="var(--safe)" />
        <stop offset="60%" stop-color="var(--safe)" />
        <stop offset="100%" stop-color="transparent" />
      </radialGradient>
      <radialGradient id="arch-suspicious-grad" fx="1">
        <stop offset="0%" stop-color="var(--warn)" />
        <stop offset="60%" stop-color="var(--warn)" />
        <stop offset="100%" stop-color="transparent" />
      </radialGradient>
      <radialGradient id="arch-malicious-grad" fx="1">
        <stop offset="0%" stop-color="var(--danger)" />
        <stop offset="60%" stop-color="var(--danger)" />
        <stop offset="100%" stop-color="transparent" />
      </radialGradient>

      <marker
        id="arch-circle-marker"
        viewBox="0 0 10 10"
        refX="5"
        refY="5"
        :markerWidth="18"
        :markerHeight="18"
      >
        <circle cx="5" cy="5" r="2" fill="var(--card-inset)" stroke="var(--gold-deep)" stroke-width="0.5">
          <animate attributeName="r" values="0; 3; 2" dur="0.5s" />
        </circle>
      </marker>

      <linearGradient id="arch-text-gradient" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="var(--gold-deep)">
          <animate
            attributeName="offset"
            values="-2; -1; 0"
            dur="5s"
            repeatCount="indefinite"
            calcMode="spline"
            keyTimes="0; 0.5; 1"
            keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
          />
        </stop>
        <stop offset="25%" stop-color="var(--gold-2)">
          <animate
            attributeName="offset"
            values="-1; 0; 1"
            dur="5s"
            repeatCount="indefinite"
            calcMode="spline"
            keyTimes="0; 0.5; 1"
            keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
          />
        </stop>
        <stop offset="50%" stop-color="var(--gold-deep)">
          <animate
            attributeName="offset"
            values="0; 1; 2"
            dur="5s"
            repeatCount="indefinite"
            calcMode="spline"
            keyTimes="0; 0.5; 1"
            keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
          />
        </stop>
      </linearGradient>
    </defs>
  </svg>
</template>