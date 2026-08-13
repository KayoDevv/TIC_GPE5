<script setup lang="ts">
import { Menu, Moon, Sun, X } from "lucide-vue-next";

const { mode, toggle } = useTheme();
const navOpen = ref(false);
const { url: downloadUrl, available: downloadAvailable } = useExtensionDownload();

function closeNav(): void {
  navOpen.value = false;
}
</script>

<template>
  <nav
    class="fixed top-3 z-50 w-full border-b border-(--border) backdrop-blur-xl"
    style="background: var(--nav-bg)"
  >
    <div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
      <div class="flex items-center gap-2.5 text-(--btn-bg)">
        <IconsBoatMark />
        <span class="text-sm font-semibold tracking-wide text-(--text)">Charon</span>
        <span
          class="ml-1 rounded-full border border-(--border) px-2 py-0.5 font-mono2 text-[10px] text-(--faint)"
        >
          v2.6
        </span>
      </div>
      <div class="hidden items-center gap-6 text-[13px] text-(--muted) md:flex">
        <a
          v-for="link in NAV_LINKS"
          :key="link.href"
          :href="link.href"
          class="transition-colors hover:text-(--text)"
        >
          {{ link.label }}
        </a>    
      </div>

      <div class="flex items-center gap-2.5">
        <button
          aria-label="Basculer le thème"
          class="grid h-8 w-8 place-items-center rounded-lg border border-(--border) text-(--muted) transition-colors hover:border-(--border-strong) hover:text-(--text)"
          @click="toggle"
        >
          <Moon v-if="mode === 'light'" :size="15" />
          <Sun v-else :size="15" />
        </button>
        <a
          v-if="downloadAvailable"
          :href="downloadUrl"
          download
          class="btn-lift rounded-lg px-4 py-1.5 text-[13px] font-semibold"
          style="background: var(--btn-bg); color: var(--btn-text)"
        >
          Installer
        </a>
        <button
          v-else
          disabled
          title="Bientôt disponible"
          class="cursor-not-allowed rounded-lg px-4 py-1.5 text-[13px] font-semibold opacity-50"
          style="background: var(--btn-bg); color: var(--btn-text)"
        >
          Installer
        </button>
      </div>
    </div>

    <Transition name="mobile-menu">
      <div
        v-if="navOpen"
        class="border-t border-(--border) md:hidden"
        style="background: var(--nav-bg)"
      >
        <a
          v-for="link in NAV_LINKS"
          :key="link.href"
          :href="link.href"
          class="block border-b border-(--border) px-6 py-3.5 text-sm text-(--text-2) transition-colors last:border-b-0 hover:text-(--text)"
          @click="closeNav"
        >
          {{ link.label }}
        </a>
      </div>
    </Transition>
  </nav>
</template>

<style scoped>
.mobile-menu-enter-active {
  transition:
    opacity 180ms ease-out,
    transform 180ms ease-out;
}
.mobile-menu-enter-from {
  opacity: 0;
  transform: translateY(-6px);
}
</style>