import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadHistory, recordHistory, type HistoryEntry } from '../../src/p0/history';
import { stubChromeStorage } from './fakeChromeStorage';

function entry(time: number): HistoryEntry {
  return { name: `file-${time}.pdf`, decision: 'allowed', score: 5, time };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('verdict history', () => {
  it('is empty outside of an extension context', async () => {
    vi.stubGlobal('chrome', undefined);

    expect(await loadHistory()).toEqual([]);
    expect(await recordHistory(entry(1))).toEqual([entry(1)]);
  });

  it('ignores a corrupted stored value', async () => {
    stubChromeStorage({ charonHistory: 'not a list' });

    expect(await loadHistory()).toEqual([]);
  });

  it('persists entries newest first and keeps only the last twenty', async () => {
    const data = stubChromeStorage();

    for (let time = 1; time <= 25; time += 1) {
      await recordHistory(entry(time));
    }

    const history = await loadHistory();
    expect(history).toHaveLength(20);
    expect(history[0].time).toBe(25);
    expect(history[19].time).toBe(6);
    expect(data.charonHistory).toEqual(history);
  });
});
