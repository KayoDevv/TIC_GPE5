import { vi } from 'vitest';

type ChangeListener = (
  changes: Record<string, { oldValue?: unknown; newValue?: unknown }>,
  area: string
) => void;

export interface FakeChrome {
  data: Record<string, unknown>;
  sent: unknown[];
}

// chrome.storage.local with change notifications, plus a recorded runtime.sendMessage.
export function stubChromeStorage(initial: Record<string, unknown> = {}): Record<string, unknown> {
  return stubChrome(initial).data;
}

export function stubChrome(initial: Record<string, unknown> = {}): FakeChrome {
  const data: Record<string, unknown> = { ...initial };
  const sent: unknown[] = [];
  const listeners = new Set<ChangeListener>();

  vi.stubGlobal('chrome', {
    storage: {
      local: {
        get: async (keys: string[]) =>
          Object.fromEntries(keys.filter((key) => key in data).map((key) => [key, data[key]])),
        set: async (items: Record<string, unknown>) => {
          const changes = Object.fromEntries(
            Object.entries(items).map(([key, value]) => [key, { oldValue: data[key], newValue: value }])
          );
          Object.assign(data, items);
          listeners.forEach((listener) => listener(changes, 'local'));
        }
      },
      onChanged: {
        addListener: (listener: ChangeListener) => listeners.add(listener),
        removeListener: (listener: ChangeListener) => listeners.delete(listener)
      }
    },
    runtime: {
      sendMessage: async (message: unknown) => {
        sent.push(message);
      }
    }
  });

  return { data, sent };
}
