<template>
  <div aria-hidden="true">
    <div
      class="hand-anchor pointer-events-none absolute right-[-5%] top-24 hidden lg:block"
    >
      <div class="hand-enter hand-enter--right">
        <div class="hand-float hand-float--slow">
          <img
            src="/engraving-hand.png"
            alt=""
            class="engraving flip-x w-[min(540px,38vw)]"
          />
        </div>
      </div>
    </div>
    <div
      class="hand-anchor pointer-events-none absolute left-[-5%] top-[360px] hidden lg:block"
    >
      <div class="hand-enter hand-enter--left">
        <div class="hand-float hand-float--fast">
          <img
            src="/engraving-hand.png"
            alt=""
            class="engraving w-[min(540px,38vw)]"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hand-enter {
  opacity: 0;
  animation: hand-enter 1.2s ease-out forwards;
}
.hand-enter--right {
  --from-x: 40px;
  --to-opacity: 0.9;
  animation-delay: 0.5s;
}
.hand-enter--left {
  --from-x: -40px;
  --to-opacity: 0.85;
  animation-delay: 0.7s;
}

@keyframes hand-enter {
  from {
    opacity: 0;
    transform: translateX(var(--from-x));
  }
  to {
    opacity: var(--to-opacity);
    transform: translateX(0);
  }
}

.hand-float--slow {
  animation: hand-float-slow 11s ease-in-out infinite;
}
.hand-float--fast {
  animation: hand-float-fast 9s ease-in-out infinite 1.6s;
}

@keyframes hand-float-slow {
  0%,
  100% {
    transform: translateY(0) rotate(0deg);
  }
  50% {
    transform: translateY(-12px) rotate(1.2deg);
  }
}
@keyframes hand-float-fast {
  0%,
  100% {
    transform: translateY(0) rotate(0deg);
  }
  50% {
    transform: translateY(-10px) rotate(-1.2deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .hand-enter {
    animation: none;
    opacity: 0.85;
  }
  .hand-float--slow,
  .hand-float--fast {
    animation: none;
  }
}
</style>