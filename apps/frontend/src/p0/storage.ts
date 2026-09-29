/** chrome.storage.local helpers shared by the popup, the side tab and the background worker. */

export function canUseChromeStorage(): boolean {
  return typeof chrome !== 'undefined' && Boolean(chrome.storage?.local);
}

// Calls `listener` with the new value each time `key` changes in chrome.storage.local.
export function watchStorageKey<T>(
  key: string,
  listener: (value: T | undefined) => void
): () => void {
  if (!canUseChromeStorage() || !chrome.storage.onChanged) {
    return () => {};
  }

  const onChanged = (
    changes: Record<string, chrome.storage.StorageChange>,
    area: chrome.storage.AreaName
  ): void => {
    if (area === 'local' && key in changes) {
      listener(changes[key].newValue as T | undefined);
    }
  };

  chrome.storage.onChanged.addListener(onChanged);
  return () => chrome.storage.onChanged.removeListener(onChanged);
}
