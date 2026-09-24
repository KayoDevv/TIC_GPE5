import { flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadTheme, saveTheme } from '../../src/p0/theme';
import { useTheme } from '../../src/ui/useTheme';
import { stubChromeStorage } from './fakeChromeStorage';

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.classList.remove('theme-dark');
});

describe('theme preference', () => {
  it('defaults to light, including outside of an extension context', async () => {
    vi.stubGlobal('chrome', undefined);
    await saveTheme('dark');
    expect(await loadTheme()).toBe('light');

    stubChromeStorage({ theme: 'sepia' });
    expect(await loadTheme()).toBe('light');
  });

  it('restores the stored theme on the document root', async () => {
    stubChromeStorage({ theme: 'dark' });

    const { theme } = useTheme();
    await flushPromises();

    expect(theme.value).toBe('dark');
    expect(document.documentElement.classList.contains('theme-dark')).toBe(true);
  });

  it('toggles and persists the theme', async () => {
    const data = stubChromeStorage();
    const { theme, toggleTheme } = useTheme();
    await flushPromises();

    toggleTheme();
    await flushPromises();
    expect(theme.value).toBe('dark');
    expect(data.theme).toBe('dark');

    toggleTheme();
    await flushPromises();
    expect(document.documentElement.classList.contains('theme-dark')).toBe(false);
    expect(data.theme).toBe('light');
  });

  it('keeps a toggle made before the stored theme was read', async () => {
    stubChromeStorage({ theme: 'light' });
    const { theme, toggleTheme } = useTheme();

    toggleTheme();
    await flushPromises();

    expect(theme.value).toBe('dark');
  });
});
