import { afterEach, describe, expect, it, vi } from 'vitest';
import { resolveJwtTokenAutomatically } from '../../src/p0/tokenResolver';
import { stubChromeStorage } from './fakeChromeStorage';

function makeJwt(payload: Record<string, unknown>): string {
  const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${encode({ alg: 'RS256' })}.${encode(payload)}.signature`;
}

const IN_ONE_HOUR = Math.floor(Date.now() / 1000) + 3600;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('resolveJwtTokenAutomatically', () => {
  it('reuses a cached token that is still valid', async () => {
    const cached = makeJwt({ sub: 'u-1', exp: IN_ONE_HOUR });
    stubChromeStorage({ cachedJwtToken: cached });

    expect(await resolveJwtTokenAutomatically()).toBe(cached);
  });

  it('returns null instead of failing when no token can be found', async () => {
    stubChromeStorage();

    expect(await resolveJwtTokenAutomatically()).toBeNull();
  });

  it('discovers and caches a token from the active tab', async () => {
    const found = makeJwt({ sub: 'u-2', exp: IN_ONE_HOUR });
    const data = stubChromeStorage();
    const chromeStub = (globalThis as unknown as { chrome: Record<string, unknown> }).chrome;
    chromeStub.tabs = { query: async () => [{ id: 7 }] };
    chromeStub.scripting = { executeScript: async () => [{ result: [`token=${found}`] }] };

    expect(await resolveJwtTokenAutomatically()).toBe(found);
    expect(data.cachedJwtToken).toBe(found);
  });
});
