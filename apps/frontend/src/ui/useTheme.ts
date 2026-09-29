/** Light/dark theme: the popup applies it to its document, the side tab only reads it. */

import { onScopeDispose, ref, type Ref } from 'vue';
import { loadTheme, saveTheme, watchTheme, type Theme } from '../p0/theme';

export type { Theme };

const DARK_THEME_CLASS = 'theme-dark';

export interface ThemeControl {
  theme: Ref<Theme>;
  toggleTheme: () => void;
}

function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle(DARK_THEME_CLASS, theme === 'dark');
}

export function useTheme(): ThemeControl {
  const theme = ref<Theme>('light');
  let toggled = false;

  void loadTheme().then((stored) => {
    // A toggle made before storage answered is the newer choice.
    if (!toggled) {
      theme.value = stored;
      applyTheme(stored);
    }
  });

  function toggleTheme(): void {
    toggled = true;
    theme.value = theme.value === 'dark' ? 'light' : 'dark';
    applyTheme(theme.value);
    void saveTheme(theme.value);
  }

  return { theme, toggleTheme };
}

// Follows the stored theme without touching the document: the side tab lives in someone
// else's page, so it applies the theme to its own shadow-root wrapper.
export function useStoredTheme(): Ref<Theme> {
  const theme = ref<Theme>('light');
  let changed = false;

  const stop = watchTheme((value) => {
    changed = true;
    theme.value = value;
  });
  void loadTheme().then((value) => {
    if (!changed) {
      theme.value = value;
    }
  });
  onScopeDispose(stop);

  return theme;
}
