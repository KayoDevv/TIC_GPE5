import { afterEach, describe, expect, it, vi } from 'vitest';
import { readExtensionVersion } from '../../src/ui/extensionVersion';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('readExtensionVersion', () => {
  it('reads the version declared in the manifest', () => {
    vi.stubGlobal('chrome', { runtime: { getManifest: () => ({ version: '1.2.3' }) } });

    expect(readExtensionVersion()).toBe('1.2.3');
  });

  it('falls back outside of an extension context', () => {
    vi.stubGlobal('chrome', undefined);

    expect(readExtensionVersion()).toBe('0.0.0');
  });

  it('falls back when the runtime API is unavailable', () => {
    vi.stubGlobal('chrome', {});

    expect(readExtensionVersion()).toBe('0.0.0');
  });
});
