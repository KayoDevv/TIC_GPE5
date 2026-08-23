/** Reads the manifest version rendered in the popup footer. */

const UNKNOWN_VERSION = '0.0.0';

export function readExtensionVersion(): string {
  if (typeof chrome === 'undefined' || !chrome.runtime?.getManifest) {
    return UNKNOWN_VERSION;
  }

  return chrome.runtime.getManifest().version;
}
