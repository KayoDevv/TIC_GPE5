export type ThemeMode = "light" | "dark";

export function useTheme() {
  const mode = useState<ThemeMode>("theme-mode", () => "light");

  const themeClass = computed(() =>
    mode.value === "light" ? "theme-light" : "theme-dark",
  );

  function toggle(): void {
    mode.value = mode.value === "light" ? "dark" : "light";
  }

  return { mode, themeClass, toggle };
}