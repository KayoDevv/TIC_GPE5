<template>
  <section class="brand-moment relative overflow-x-clip">
    <MotionScrollReveal>
      <div data-river-end class="w-full pt-16">
        <img
          src="/river-watercolor.jpg"
          alt="Aquarelle du Styx — le passeur mène sa barque entre les deux rives"
          class="watercolor w-full object-cover"
          width="1920"
          height="600"
          loading="lazy"
          decoding="async"
        />
      </div>
    </MotionScrollReveal>

    <div class="mx-auto flex max-w-4xl flex-col items-center px-6 pb-20 pt-10 text-center">
      <MotionScrollReveal>
        <span class="text-(--btn-bg)">
          <IconsBoatMark :size="40" />
        </span>
      </MotionScrollReveal>
      <MotionScrollReveal :delay="0.1">
        <blockquote class="font-display mt-6 max-w-2xl text-2xl leading-snug text-(--text) sm:text-3xl">
          « Dans le mythe, Charon ne laisse traverser que les âmes en règle.
          <span class="text-(--muted)">
            Dans votre navigateur, il fait pareil avec vos fichiers.
          </span>
          »
        </blockquote>
      </MotionScrollReveal>
      <MotionScrollReveal :delay="0.2">
        <p class="mt-5 font-mono2 text-[11px] uppercase tracking-[0.25em] text-(--faint)">
          Le Styx — un passage entre les mondes
        </p>
      </MotionScrollReveal>
    </div>
  </section>
</template>

<style scoped>
.brand-moment {
  background: linear-gradient(
    180deg,
    transparent 0%,
    color-mix(in srgb, var(--bg-alt) 55%, transparent) 14%,
    color-mix(in srgb, var(--bg-alt) 55%, transparent) 86%,
    transparent 100%
  );
}

.watercolor {
  height: clamp(260px, 40vw, 600px);
  -webkit-mask-image: linear-gradient(
    180deg,
    transparent 0%,
    #000 16%,
    #000 84%,
    transparent 100%
  );
  mask-image: linear-gradient(
    180deg,
    transparent 0%,
    #000 16%,
    #000 84%,
    transparent 100%
  );
}
</style>