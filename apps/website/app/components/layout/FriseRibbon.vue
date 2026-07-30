<template>
  <div class="frise-ribbon" aria-hidden="true" />
</template>

<style scoped>
.frise-ribbon {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 12px;
  z-index: 60;
  background-color: var(--gold);
  -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M0 11 H12 M1.8 11 V1.8 H10.3 V7.3 H5.3 V5 H7.7' fill='none' stroke='%23000' stroke-width='1.6'/%3E%3C/svg%3E")
    repeat-x left bottom / 12px 12px;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M0 11 H12 M1.8 11 V1.8 H10.3 V7.3 H5.3 V5 H7.7' fill='none' stroke='%23000' stroke-width='1.6'/%3E%3C/svg%3E")
    repeat-x left bottom / 12px 12px;
  animation: frise-drift 60s linear infinite;
}

@keyframes frise-drift {
  from {
    -webkit-mask-position: 0 bottom;
    mask-position: 0 bottom;
  }
  to {
    -webkit-mask-position: 120px bottom;
    mask-position: 120px bottom;
  }
}

@media (prefers-reduced-motion: reduce) {
  .frise-ribbon {
    animation: none;
  }
}
</style>