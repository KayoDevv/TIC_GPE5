const JWT_PATTERN = /[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g;

function decodeBase64Url(value: string): string | null {
  try {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), '=');
    return atob(padded);
  } catch {
    return null;
  }
}

export interface JwtPayload {
  exp?: number;
  sub?: string;
  aud?: string | string[];
  [key: string]: unknown;
}

export function parseJwtPayload(token: string): JwtPayload | null {
  const parts = token.split('.');
  if (parts.length !== 3) {
    return null;
  }

  const decoded = decodeBase64Url(parts[1]);
  if (!decoded) {
    return null;
  }

  try {
    return JSON.parse(decoded) as JwtPayload;
  } catch {
    return null;
  }
}

export function isJwtExpired(token: string, graceSeconds = 30): boolean {
  const payload = parseJwtPayload(token);
  if (!payload?.exp || typeof payload.exp !== 'number') {
    return false;
  }

  const now = Math.floor(Date.now() / 1000);
  return payload.exp <= now + graceSeconds;
}

export function extractJwtCandidates(samples: string[]): string[] {
  const tokens = new Set<string>();

  for (const sample of samples) {
    if (!sample) {
      continue;
    }

    const matches = sample.match(JWT_PATTERN) ?? [];
    for (const token of matches) {
      tokens.add(token);
    }
  }

  return Array.from(tokens);
}

function tokenScore(token: string): number {
  const payload = parseJwtPayload(token);
  if (!payload) {
    return -1;
  }

  const expScore = typeof payload.exp === 'number' ? payload.exp : 0;
  const subjectBonus = payload.sub ? 10_000_000_000 : 0;
  return expScore + subjectBonus;
}

export function pickBestJwtToken(tokens: string[]): string | null {
  const valid = tokens.filter((token) => !isJwtExpired(token));
  if (valid.length === 0) {
    return null;
  }

  return valid.sort((left, right) => tokenScore(right) - tokenScore(left))[0] ?? null;
}
