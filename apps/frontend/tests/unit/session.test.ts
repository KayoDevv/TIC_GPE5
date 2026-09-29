import { afterEach, describe, expect, it, vi } from 'vitest';
import { watchHistory } from '../../src/p0/history';
import { IDLE_SNAPSHOT, loadSnapshot, saveSnapshot, watchSnapshot } from '../../src/p0/session';
import { watchTheme } from '../../src/p0/theme';
import { stubChrome } from './fakeChromeStorage';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('shared analysis snapshot', () => {
  it('is idle until the background worker writes one', async () => {
    stubChrome();
    expect(await loadSnapshot()).toEqual(IDLE_SNAPSHOT);

    vi.stubGlobal('chrome', undefined);
    expect(await loadSnapshot()).toEqual(IDLE_SNAPSHOT);
    await expect(saveSnapshot(IDLE_SNAPSHOT)).resolves.toBeUndefined();
  });

  it('notifies every watcher of a new snapshot until it stops watching', async () => {
    stubChrome();
    const seen: string[] = [];
    const stop = watchSnapshot((snapshot) => seen.push(snapshot.phase));

    await saveSnapshot({ ...IDLE_SNAPSHOT, phase: 'analyzing' });
    stop();
    await saveSnapshot({ ...IDLE_SNAPSHOT, phase: 'completed' });

    expect(seen).toEqual(['analyzing']);
    expect((await loadSnapshot()).phase).toBe('completed');
  });

  it('ignores changes to other keys and treats a cleared snapshot as idle', async () => {
    const fake = stubChrome();
    const seen: string[] = [];
    watchSnapshot((snapshot) => seen.push(snapshot.phase));

    await chrome.storage.local.set({ unrelated: 1 });
    await chrome.storage.local.set({ charonSession: undefined });

    expect(seen).toEqual(['idle']);
    expect(fake.data.unrelated).toBe(1);
  });

  it('watches the history and the theme the same way', async () => {
    stubChrome();
    const history = vi.fn();
    const theme = vi.fn();
    watchHistory(history);
    watchTheme(theme);

    await chrome.storage.local.set({ charonHistory: 'corrupted', theme: 'dark' });
    await chrome.storage.local.set({ theme: 'sepia' });

    expect(history).toHaveBeenCalledWith([]);
    expect(theme.mock.calls).toEqual([['dark'], ['light']]);
  });

  it('cannot watch outside of an extension context', () => {
    vi.stubGlobal('chrome', undefined);

    expect(() => watchSnapshot(() => {})()).not.toThrow();
  });
});
