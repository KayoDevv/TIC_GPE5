import tailwindcss from "@tailwindcss/vite";

export default defineNuxtConfig({
  compatibilityDate: "2025-07-15",
  devtools: { enabled: true },
  modules: ["@nuxt/fonts"],
  css: ["~/assets/css/main.css"],
  fonts: {
    families: [
      { name: "Cinzel", provider: "google", weights: [500, 600, 700] },
      { name: "Spectral", provider: "google", weights: [300, 400, 500, 600] },
      { name: "Space Mono", provider: "google", weights: [400] },
    ],
  },
  typescript: {
    typeCheck: true,
  },
  vite: {
    plugins: [tailwindcss()],
    optimizeDeps: {
      include: ["@vue/devtools-core", "@vue/devtools-kit"],
    },
  },
});