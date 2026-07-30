<script setup lang="ts">
import { Menu, Moon, Sun, X } from "lucide-vue-next";

const { mode, toggle } = useTheme();
const navOpen = ref(false);

function closeNav(): void {
  navOpen.value = false;
}
</script>

<template>
  <nav
    class="fixed top-[12px] z-50 w-full border-b border-[var(--border)] backdrop-blur-xl"
    style="background: var(--nav-bg)"
  >
    <div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
      <div class="flex items-center gap-2.5 text-[var(--btn-bg)]">
        <IconsBoatMark />
        <span class="text-sm font-semibold tracking-wide text-[var(--text)]">Charon</span>
        <span
          class="ml-1 rounded-full border border-[var(--border)] px-2 py-0.5 font-mono2 text-[10px] text-[var(--faint)]"
        >
          v2.6
        </span>
      </div>
      <div class="hidden items-center gap-6 text-[13px] text-[var(--muted)] md:flex">
        <a
          v-for="link in NAV_LINKS"
          :key="link.href"
          :href="link.href"
          class="transition-colors hover:text-[var(--text)]"
        >
          {{ link.label }}
        </a>    
      </div>

      <div class="flex items-center gap-2.5">
        <button
          aria-label="Basculer le thème"
          class="grid h-8 w-8 place-items-center rounded-lg border border-[var(--border)] text-[var(--muted)] transition-colors hover:border-[var(--border-strong)] hover:text-[var(--text)]"
          @click="toggle"
        >
          <Moon v-if="mode === 'light'" :size="15" />
          <Sun v-else :size="15" />
        </button>
        <a
          href="/charon-extension-v2.0.0.zip"
          download
          class="btn-lift rounded-lg px-4 py-1.5 text-[13px] font-semibold"
          style="background: var(--btn-bg); color: var(--btn-text)"
        >
          Installer
        </a>
        <button
          :aria-label="navOpen ? 'Fermer le menu' : 'Ouvrir le menu'"
          :aria-expanded="navOpen"
          class="grid h-11 w-11 place-items-center rounded-lg border border-[var(--border)] text-[var(--muted)] transition-colors hover:text-[var(--text)] md:hidden"
          @click="navOpen = !navOpen"
        >
          <X v-if="navOpen" :size="17" />
          <Menu v-else :size="17" />
        </button>
      </div>
    </div>

    <Transition name="mobile-menu">
      <div
        v-if="navOpen"
        class="border-t border-[var(--border)] md:hidden"
        style="background: var(--nav-bg)"
      >
        <a
          v-for="link in NAV_LINKS"
          :key="link.href"
          :href="link.href"
          class="block border-b border-[var(--border)] px-6 py-3.5 text-sm text-[var(--text-2)] transition-colors last:border-b-0 hover:text-[var(--text)]"
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