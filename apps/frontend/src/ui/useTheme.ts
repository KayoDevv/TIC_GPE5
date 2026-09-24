/** Light/dark theme of the popup, applied as a class on the document root. */

import { ref, type Ref } from 'vue';
import { loadTheme, saveTheme, type Theme } from '../p0/theme';

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
