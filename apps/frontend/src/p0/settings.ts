export interface P0Settings {
  apiBaseUrl: string;
  cachedJwtToken: string;
}

const ENV_API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const DEFAULT_SETTINGS: P0Settings = {
  apiBaseUrl: ENV_API_BASE_URL,
  cachedJwtToken: ''
};

function canUseChromeStorage(): boolean {
  return typeof chrome !== 'undefined' && Boolean(chrome.storage?.local);
}

export async function loadSettings(): Promise<P0Settings> {
  if (!canUseChromeStorage()) {
    return DEFAULT_SETTINGS;
  }

  const raw = (await chrome.storage.local.get(['cachedJwtToken'])) as Partial<P0Settings>;

  return {
    apiBaseUrl: ENV_API_BASE_URL,
    cachedJwtToken: (raw.cachedJwtToken ?? DEFAULT_SETTINGS.cachedJwtToken).trim()
  };
}

export async function saveSettings(settings: P0Settings): Promise<void> {
  if (!canUseChromeStorage()) {
    return;
  }

  await chrome.storage.local.set({
    cachedJwtToken: settings.cachedJwtToken.trim()
  });
}
