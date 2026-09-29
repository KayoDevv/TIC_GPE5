/** Persisted light/dark preference of the popup. */

import { canUseChromeStorage, watchStorageKey } from './storage';

export type Theme = 'light' | 'dark';

const THEME_KEY = 'theme';
const DEFAULT_THEME: Theme = 'light';

export async function loadTheme(): Promise<Theme> {
  if (!canUseChromeStorage()) {
    return DEFAULT_THEME;
  }

  const raw = (await chrome.storage.local.get([THEME_KEY])) as { [THEME_KEY]?: string };
  return raw[THEME_KEY] === 'dark' ? 'dark' : DEFAULT_THEME;
}

export async function saveTheme(theme: Theme): Promise<void> {
  if (canUseChromeStorage()) {
    await chrome.storage.local.set({ [THEME_KEY]: theme });
  }
}

export function watchTheme(listener: (theme: Theme) => void): () => void {
  return watchStorageKey<string>(THEME_KEY, (value) =>
    listener(value === 'dark' ? 'dark' : DEFAULT_THEME)
  );
}
