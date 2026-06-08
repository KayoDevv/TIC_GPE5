import { describe, expect, it } from 'vitest';
import { extractJwtCandidates, isJwtExpired, parseJwtPayload, pickBestJwtToken } from '../../src/p0/jwt';

function toBase64Url(value: string): string {
  return Buffer.from(value, 'utf-8')
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

function makeJwt(payload: Record<string, unknown>): string {
  const header = { alg: 'RS256', typ: 'JWT' };
  return `${toBase64Url(JSON.stringify(header))}.${toBase64Url(JSON.stringify(payload))}.signature`;
}

describe('jwt helpers', () => {
  it('extracts JWT candidates from raw text samples', () => {
    const token = makeJwt({ sub: 'u-1', exp: Math.floor(Date.now() / 1000) + 600 });
    const values = extractJwtCandidates(['foo', `Bearer ${token}`, 'bar']);

    expect(values).toContain(token);
  });

  it('parses payload and expiration correctly', () => {
    const token = makeJwt({ sub: 'u-2', exp: Math.floor(Date.now() / 1000) + 120 });
    const payload = parseJwtPayload(token);

    expect(payload?.sub).toBe('u-2');
    expect(isJwtExpired(token)).toBe(false);
  });

  it('picks best valid token by preferring non-expired candidates', () => {
    const expired = makeJwt({ sub: 'u-3', exp: Math.floor(Date.now() / 1000) - 120 });
    const valid = makeJwt({ sub: 'u-4', exp: Math.floor(Date.now() / 1000) + 600 });

    expect(pickBestJwtToken([expired, valid])).toBe(valid);
  });
});
