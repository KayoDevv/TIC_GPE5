/** Guard for code that also runs outside the extension (unit tests, plain pages). */

export function canUseChromeStorage(): boolean {
  return typeof chrome !== 'undefined' && Boolean(chrome.storage?.local);
}
