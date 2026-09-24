import { vi } from 'vitest';

export function stubChromeStorage(initial: Record<string, unknown> = {}): Record<string, unknown> {
  const data: Record<string, unknown> = { ...initial };

  vi.stubGlobal('chrome', {
    storage: {
      local: {
        get: async (keys: string[]) =>
          Object.fromEntries(keys.filter((key) => key in data).map((key) => [key, data[key]])),
        set: async (items: Record<string, unknown>) => {
          Object.assign(data, items);
        }
      }
    }
  });

  return data;
}
