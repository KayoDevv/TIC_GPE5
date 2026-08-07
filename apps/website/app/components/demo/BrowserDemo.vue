<script setup lang="ts">
import type { IconShape, IconState } from "~/types/icon";
import { ICON_SHAPES } from "~/types/icon";

type Edge = "top" | "right" | "bottom" | "left";
type Verdict = "clear" | "suspect" | "threat";

const FILES: { name: string; meta: string; tag: string; verdict: Verdict }[] = [
  {
    name: "flash_player_setup.exe",
    meta: "Mise à jour critique · v9.3.4 · 4.8 mb",
    tag: "EXE",
    verdict: "threat",
  },
  {
    name: "facture_impayee.docm",
    meta: "Macro intégrée · expéditeur inconnu · 0.6 mb",
    tag: "DOC",
    verdict: "suspect",
  },
  {
    name: "rapport_annuel_2025.pdf",
    meta: "Document financier signé · 22 pages · 1.1 mb",
    tag: "PDF",
    verdict: "clear",
  },
  {
    name: "optimizer_tools.zip",
    meta: "Pack utilitaires gratuit · 7.3 mb",
    tag: "ZIP",
    verdict: "clear",
  },
];

const VERDICT_COPY: Record<Verdict, { label: string; sub: string }> = {
  clear: {
    label: "Autorisé",
    sub: "Aucun comportement malveillant — traversée accordée.",
  },
  suspect: {
    label: "Suspect",
    sub: "Comportement ambigu — fichier placé en quarantaine.",
  },
  threat: {
    label: "Bloqué",
    sub: "Charge malveillante interceptée. La barque a coulé.",
  },
};

const EDGES: { id: Edge; label: string }[] = [
  { id: "top", label: "Haut" },
  { id: "right", label: "Droite" },
  { id: "bottom", label: "Bas" },
  { id: "left", label: "Gauche" },
];

const SHAPE_LABELS: Record<IconShape, string> = {
  eye: "Œil",
  boat: "Barque",
  virus: "Virus",
  ring: "Anneau",
  lantern: "Lanterne",
};

const EDGE_POSITION: Record<Edge, string> = {
  right: "right-0 top-1/2 -translate-y-1/2 flex-col",
  left: "left-0 top-1/2 -translate-y-1/2 flex-col",
  top: "top-0 left-1/2 -translate-x-1/2 flex-row",
  bottom: "bottom-0 left-1/2 -translate-x-1/2 flex-row",
};

const TAB_SHAPE: Record<Edge, string> = {
  right: "rounded-l-md border-r-0",
  left: "rounded-r-md border-l-0",
  top: "rounded-b-md border-t-0",
  bottom: "rounded-t-md border-b-0",
};

const POPOVER_PLACEMENT: Record<Edge, string> = {
  right: "right-full top-1/2 -translate-y-1/2 mr-3",
  left: "left-full top-1/2 -translate-y-1/2 ml-3",
  top: "top-full left-1/2 -translate-x-1/2 mt-3",
  bottom: "bottom-full left-1/2 -translate-x-1/2 mb-3",
};

const PAGE_LANE: Record<Edge, string> = {
  right: "pr-16",
  left: "pl-16",
  top: "pt-16",
  bottom: "pb-16",
};

const CHROME_DOTS = ["10%", "7%", "4%"];

const edge = ref<Edge>("right");
const shape = ref<IconShape>("eye");
const state = ref<IconState>("rest");
const popover = ref<Verdict | null>(null);
const busy = ref(false);
const timers: number[] = [];

function runScan(verdict: Verdict): void {
  if (busy.value) return;
  busy.value = true;
  popover.value = null;
  state.value = "scan";
  timers.push(
    window.setTimeout(() => {
      state.value = verdict;
      popover.value = verdict;
      timers.push(
        window.setTimeout(() => {
          state.value = "rest";
          popover.value = null;
          busy.value = false;
        }, 2800),
      );
    }, 1900),
  );
}

onUnmounted(() => {
  timers.forEach((timer) => window.clearTimeout(timer));
});
</script>

<template>
  <div class="w-full">
    <div class="mb-5 flex flex-wrap items-center justify-center gap-x-8 gap-y-4">
      <DemoControlGroup label="Position">
        <DemoChip
          v-for="item in EDGES"
          :key="item.id"
          :active="edge === item.id"
          @select="edge = item.id"
        >
          {{ item.label }}
        </DemoChip>
      </DemoControlGroup>
      <DemoControlGroup label="Forme">
        <DemoChip
          v-for="s in ICON_SHAPES"
          :key="s"
          :active="shape === s"
          @select="shape = s"
        >
          <span class="flex items-center gap-1.5">
            <IconsAnimatedIcon
              :shape="s"
              :state="shape === s ? state : 'rest'"
              :size="16"
              :color="shape === s ? 'var(--demo-chip-text)' : undefined"
            />
            {{ SHAPE_LABELS[s] }}
          </span>
        </DemoChip>
      </DemoControlGroup>
    </div>

    <div
      class="relative mx-auto max-w-3xl overflow-hidden rounded-2xl shadow-2xl"
      style="background: var(--demo-frame)"
    >
      <div class="flex items-center gap-2 px-4 py-3" style="background: var(--demo-chrome)">
        <span
          v-for="dot in CHROME_DOTS"
          :key="dot"
          class="h-3 w-3 rounded-full border border-(--border)"
          :style="{ background: `color-mix(in srgb, var(--demo-dot) ${dot}, transparent)` }"
        />
        <div class="ml-3 flex-1">
          <div
            class="flex items-center gap-2 rounded-md px-3 py-1.5 text-xs text-(--text-2)"
            style="background: var(--demo-inset)"
          >
            <svg width="11" height="11" viewBox="0 0 12 12" fill="none" class="opacity-60" aria-hidden="true">
              <rect x="2" y="5" width="8" height="5.5" rx="1" stroke="currentColor" stroke-width="1.1" />
              <path d="M4 5V3.8A2 2 0 0 1 8 3.8V5" stroke="currentColor" stroke-width="1.1" />
            </svg>
            fastdownloader.io / files
          </div>
        </div>
        <div
          class="grid h-7 w-7 place-items-center rounded-md border border-(--border)"
          style="background: var(--demo-tab-bg)"
          title="Charon"
        >
          <IconsAnimatedIcon :shape="shape" :state="state" :size="17" />
        </div>
      </div>

      <div
        class="relative min-h-90 p-6 text-(--text) sm:p-8"
        :class="PAGE_LANE[edge]"
        style="background: var(--demo-page)"
      >
        <div class="mb-6">
          <h4 class="text-xl font-semibold">Centre de téléchargement</h4>
          <p class="text-sm text-(--faint)">
            Cliquez sur « Télécharger » — Charon inspecte chaque fichier avant qu'il n'accoste.
          </p>
        </div>

        <div class="space-y-3">
          <div
            v-for="file in FILES"
            :key="file.name"
            class="flex items-center gap-4 rounded-xl border border-(--border) p-3 sm:p-4"
            style="background: var(--demo-card)"
          >
            <span
              class="hidden h-11 w-11 shrink-0 place-items-center rounded-lg text-[10px] font-bold tracking-wider text-(--faint) sm:grid"
              style="background: var(--demo-inset)"
            >
              {{ file.tag }}
            </span>
            <div class="min-w-0 flex-1">
              <div class="truncate text-sm font-medium">{{ file.name }}</div>
              <div class="hidden truncate text-xs text-(--faint) sm:block">
                {{ file.meta }}
              </div>
            </div>
            <button
              :disabled="busy"
              class="shrink-0 rounded-lg px-3 py-2 text-[11px] font-semibold transition-transform hover:scale-[1.03] active:scale-95 disabled:opacity-40 sm:px-4 sm:text-xs"
              style="background: var(--btn-bg); color: var(--btn-text)"
              @click="runScan(file.verdict)"
            >
              Télécharger
            </button>
          </div>
        </div>

        <Transition name="tab-pop" mode="out-in">
          <div
            :key="edge"
            class="pointer-events-none absolute z-20 flex"
            :class="EDGE_POSITION[edge]"
          >
            <div
              class="tab pointer-events-auto relative flex items-center justify-center border p-2.5 backdrop-blur"
              :class="TAB_SHAPE[edge]"
              :data-state="state"
              style="background: var(--demo-tab-bg)"
            >
              <IconsAnimatedIcon :shape="shape" :state="state" :size="34" />

              <Transition name="popover">
                <div
                  v-if="popover"
                  class="absolute w-44 rounded-md border border-(--border) p-3.5 text-left shadow-xl sm:w-56"
                  :class="POPOVER_PLACEMENT[edge]"
                  style="background: var(--demo-popover-bg); color: var(--text)"
                >
                  <div class="flex items-center gap-2">
                    <IconsAnimatedIcon :shape="shape" :state="popover" :size="15" />
                    <span
                      class="font-display flex-1 text-[11px] font-semibold uppercase tracking-[0.14em]"
                      style="color: var(--demo-accent)"
                    >
                      Charon
                    </span>
                  </div>
                  <div class="relative my-2 h-px bg-(--border)">
                    <span
                      class="absolute left-1/2 -top-0.5 h-1.25 w-1.25 -translate-x-1/2 rounded-full"
                      style="background: var(--demo-accent)"
                    />
                  </div>
                  <div
                    class="verdict-label font-display mb-1 text-[13px] font-semibold uppercase tracking-[0.08em]"
                    :data-verdict="popover"
                  >
                    {{ VERDICT_COPY[popover].label }}
                  </div>
                  <p class="text-xs leading-relaxed text-(--faint)">
                    {{ VERDICT_COPY[popover].sub }}
                  </p>
                </div>
              </Transition>
            </div>
          </div>
        </Transition>

        <Transition name="fade">
          <div
            v-if="state === 'scan'"
            class="pointer-events-none absolute inset-0 z-10 overflow-hidden"
          >
            <div class="sweep absolute inset-x-0 h-24" />
          </div>
        </Transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tab {
  border-color: var(--demo-tab-border);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25);
  transition:
    border-color 0.3s ease,
    box-shadow 0.3s ease;
}
.tab[data-state="scan"] {
  box-shadow: 0 0 22px color-mix(in srgb, var(--gold) 40%, transparent);
}
.tab[data-state="suspect"] {
  border-color: var(--warn);
  box-shadow: 0 0 24px color-mix(in srgb, var(--warn) 44%, transparent);
}
.tab[data-state="clear"] {
  border-color: var(--safe);
  box-shadow: 0 0 22px color-mix(in srgb, var(--safe) 40%, transparent);
}
.tab[data-state="threat"] {
  border-color: var(--danger);
  box-shadow: 0 0 26px color-mix(in srgb, var(--danger) 47%, transparent);
}

.verdict-label[data-verdict="clear"] {
  color: var(--safe);
}
.verdict-label[data-verdict="suspect"] {
  color: var(--warn);
}
.verdict-label[data-verdict="threat"] {
  color: var(--danger);
}

.sweep {
  background: linear-gradient(
    to bottom,
    transparent,
    color-mix(in srgb, var(--gold) 13%, transparent),
    transparent
  );
  animation: sweep-fall 1.6s linear infinite;
}
@keyframes sweep-fall {
  from {
    top: -20%;
  }
  to {
    top: 110%;
  }
}

.tab-pop-enter-active,
.tab-pop-leave-active {
  transition:
    opacity 0.16s ease,
    transform 0.16s ease;
}
.tab-pop-enter-from,
.tab-pop-leave-to {
  opacity: 0;
  transform: scale(0.85);
}

.popover-enter-active {
  transition:
    opacity 0.22s cubic-bezier(0.34, 1.56, 0.64, 1),
    transform 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.popover-leave-active {
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}
.popover-enter-from,
.popover-leave-to {
  opacity: 0;
  transform: scale(0.85);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .sweep {
    animation: none;
  }
}
</style>