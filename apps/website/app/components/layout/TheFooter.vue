<template>
  <footer class="border-t border-[var(--border)]">
    <div
      class="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 py-8 md:flex-row"
    >
      <div class="flex items-center gap-2.5 text-[var(--btn-bg)]">
        <IconsBoatMark :size="18" />
        <span class="text-xs font-semibold tracking-wide text-[var(--text)]">Charon</span>
        <span class="font-mono2 text-[10px] text-[var(--faint)]">
          — le passeur qui garde votre boîte mail
        </span>
      </div>
      <div class="flex gap-5 text-xs text-[var(--muted)]">
        <a
          v-for="link in FOOTER_LINKS"
          :key="link.href"
          :href="link.href"
          class="transition-colors hover:text-[var(--text)]"
        >
          {{ link.label }}
        </a>
      </div>
    </div>
  </footer>
</template>