import { extractJwtCandidates, isJwtExpired, pickBestJwtToken } from './jwt';
import { loadSettings, saveSettings } from './settings';

async function discoverTokenSamplesFromActiveTab(): Promise<string[]> {
  try {
    if (typeof chrome === 'undefined' || !chrome.tabs?.query || !chrome.scripting?.executeScript) {
      return [];
    }

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) {
      return [];
    }

    const injected = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const samples: string[] = [];

        const collectStorage = (storage: Storage) => {
          for (let index = 0; index < storage.length; index += 1) {
            const key = storage.key(index);
            if (!key) {
              continue;
            }

            samples.push(key);

            const value = storage.getItem(key);
            if (value) {
              samples.push(value);
            }
          }
        };

        try {
          collectStorage(window.localStorage);
        } catch {
          // Ignore storage access errors.
        }

        try {
          collectStorage(window.sessionStorage);
        } catch {
          // Ignore storage access errors.
        }

        if (document.cookie) {
          samples.push(document.cookie);
        }

        samples.push(window.location.href);

        return samples;
      }
    });

    const values = injected
      .map((item) => item.result)
      .flatMap((item) => (Array.isArray(item) ? item : []))
      .filter((item): item is string => typeof item === 'string');

    return values;
  } catch {
    return [];
  }
}

// Null when no usable token exists: the backend, not the popup, decides whether one is needed.
export async function resolveJwtTokenAutomatically(): Promise<string | null> {
  const settings = await loadSettings();

  if (settings.cachedJwtToken && !isJwtExpired(settings.cachedJwtToken)) {
    return settings.cachedJwtToken;
  }

  const samples = await discoverTokenSamplesFromActiveTab();
  const candidates = extractJwtCandidates(samples);
  const bestToken = pickBestJwtToken(candidates);

  if (!bestToken) {
    return null;
  }

  await saveSettings({
    apiBaseUrl: settings.apiBaseUrl,
    cachedJwtToken: bestToken
  });

  return bestToken;
}
