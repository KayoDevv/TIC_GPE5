import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  buildWebSocketUrl,
  describeUploader,
  readErrorMessage,
  runAnalysis
} from '../../src/p0/network';

function makeJwt(payload: Record<string, unknown>): string {
  const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${encode({ alg: 'RS256' })}.${encode(payload)}.signature`;
}

class FakeSocket extends EventTarget {
  static last: FakeSocket | undefined;
  readonly close = vi.fn();

  constructor(readonly url: string) {
    super();
    FakeSocket.last = this;
  }

  emit(type: 'message' | 'close' | 'error', init: { data?: string; code?: number } = {}): void {
    this.dispatchEvent(Object.assign(new Event(type), init));
  }
}

function stubBackend(response: Response): ReturnType<typeof vi.fn> {
  FakeSocket.last = undefined;
  const fetchMock = vi.fn(async () => response);
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('WebSocket', FakeSocket);
  return fetchMock;
}

function jobAccepted(): Response {
  return new Response(JSON.stringify({ job_id: 'job-1' }), { status: 202 });
}

// Wrapped so awaiting the helper waits for the socket, not for the outcome itself.
async function startAnalysis(): Promise<{ outcome: Promise<unknown>; socket: FakeSocket }> {
  const outcome = runAnalysis({
    apiBaseUrl: 'http://localhost:8000',
    jwtToken: makeJwt({ sub: 'user-1', email: 'alice@corp.example' }),
    file: new File(['payload'], 'invoice.pdf')
  });
  const socket = await vi.waitFor(() => {
    expect(FakeSocket.last).toBeDefined();
    return FakeSocket.last as FakeSocket;
  });
  return { outcome, socket };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

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

describe('describeUploader', () => {
  it('prefers the email, then the username, then the subject of the JWT', () => {
    expect(describeUploader(makeJwt({ sub: 'u-1', email: 'alice@corp.example' }))).toBe(
      'alice@corp.example'
    );
    expect(describeUploader(makeJwt({ sub: 'u-1', preferred_username: 'alice' }))).toBe('alice');
    expect(describeUploader(makeJwt({ sub: 'u-1', email: '  ' }))).toBe('u-1');
  });

  it('falls back when the token names nobody', () => {
    expect(describeUploader(makeJwt({ exp: 1 }))).toBe('unknown-uploader');
    expect(describeUploader('not-a-jwt')).toBe('unknown-uploader');
  });
});

describe('readErrorMessage', () => {
  it('reads both backend error shapes', () => {
    expect(readErrorMessage({ message: 'Failed to upload file to storage.' })).toBe(
      'Failed to upload file to storage.'
    );
    expect(readErrorMessage({ detail: { message: 'File exceeds the 35 MB limit.' } })).toBe(
      'File exceeds the 35 MB limit.'
    );
    expect(readErrorMessage({})).toBeUndefined();
  });
});

describe('runAnalysis', () => {
  it('uploads as the signed-in user and resolves with the verdict', async () => {
    const fetchMock = stubBackend(jobAccepted());
    const { outcome, socket } = await startAnalysis();

    socket.emit('message', {
      data: JSON.stringify({ job_id: 'job-1', final_decision: 'allowed', timestamp: 't' })
    });
    socket.emit('close', { code: 1000 });

    await expect(outcome).resolves.toMatchObject({ kind: 'verdict', jobId: 'job-1' });
    const body = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as FormData;
    expect(body.get('sender')).toBe('alice@corp.example');
  });

  it('shows the reason the backend gave for refusing the upload', async () => {
    stubBackend(
      new Response(JSON.stringify({ detail: { error: 'FILE_TOO_LARGE', message: 'Too big.' } }), {
        status: 400
      })
    );

    await expect(
      runAnalysis({ apiBaseUrl: 'http://x', jwtToken: 'token', file: new File(['x'], 'a.bin') })
    ).rejects.toThrow('Too big.');
  });

  it('keeps the status-code message when the error body is not JSON', async () => {
    stubBackend(new Response('bad gateway', { status: 502 }));

    await expect(
      runAnalysis({ apiBaseUrl: 'http://x', jwtToken: 'token', file: new File(['x'], 'a.bin') })
    ).rejects.toThrow('Analyze request failed (502).');
  });

  it('treats a 4008 close as an analysis timeout', async () => {
    stubBackend(jobAccepted());
    const { outcome, socket } = await startAnalysis();

    socket.emit('close', { code: 4008 });

    await expect(outcome).resolves.toEqual({ kind: 'timeout', jobId: 'job-1' });
  });

  it('fails at once when the channel closes early instead of waiting for the deadline', async () => {
    stubBackend(jobAccepted());
    const { outcome, socket } = await startAnalysis();

    socket.emit('close', { code: 1011 });

    await expect(outcome).rejects.toThrow(ApiError);
    await expect(outcome).rejects.toThrow('code 1011');
  });

  it('reports a rejected token', async () => {
    stubBackend(jobAccepted());
    const { outcome, socket } = await startAnalysis();

    socket.emit('close', { code: 4001 });

    await expect(outcome).rejects.toThrow('WebSocket authentication failed');
  });
});
