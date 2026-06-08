import { describe, expect, it } from 'vitest';
import { buildWebSocketUrl } from '../../src/p0/network';

describe('buildWebSocketUrl', () => {
  it('builds ws URL from http base URL', () => {
    const value = buildWebSocketUrl('http://localhost:8000', 'job-1', 'token-1');
    expect(value).toBe('ws://localhost:8000/api/v1/ws/job-1?token=token-1');
  });

  it('builds wss URL from https base URL', () => {
    const value = buildWebSocketUrl('https://api.example.com/', 'job-2', 'token-2');
    expect(value).toBe('wss://api.example.com/api/v1/ws/job-2?token=token-2');
  });
});
