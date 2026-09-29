export type VerdictDecision = 'allowed' | 'blocked' | 'warning';

export interface TechnicalSummary {
  ml_layer_score?: number | null;
  sandbox_layer_iocs?: Record<string, unknown>[] | null;
  sandbox_layer_timeout?: boolean | null;
  llm_layer_malicious?: boolean | null;
}

export interface VerdictMessage {
  job_id: string;
  final_decision: VerdictDecision;
  user_explanation?: string | null;
  technical_summary?: TechnicalSummary | null;
  timestamp: string;
}

export interface AnalysisInput {
  apiBaseUrl: string;
  jwtToken: string;
  file: File;
  timeoutMs?: number;
}

export type AnalysisOutcome =
  | {
      kind: 'verdict';
      jobId: string;
      verdict: VerdictMessage;
    }
  | {
      kind: 'timeout';
      jobId: string;
    };

import { parseJwtPayload } from './jwt';

export class ApiError extends Error {
  constructor(message: string, readonly statusCode?: number) {
    super(message);
    this.name = 'ApiError';
  }
}

// Longer than the backend's 150 s so the backend's own 4008 timeout is what the popup sees.
const DEFAULT_TIMEOUT_MS = 160_000;
const UNKNOWN_UPLOADER = 'unknown-uploader';
const WS_CLOSE_TIMEOUT = 4008;
const WS_CLOSE_AUTH_FAILED = 4001;

interface ErrorPayload {
  message?: string;
  detail?: { message?: string };
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
}

export function buildWebSocketUrl(baseUrl: string, jobId: string, jwtToken: string): string {
  const normalizedBase = normalizeBaseUrl(baseUrl);
  const url = new URL(`${normalizedBase}/api/v1/ws/${jobId}`);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.searchParams.set('token', jwtToken);
  return url.toString();
}

// A manual upload has no email, so the sender is the signed-in user the JWT names.
export function describeUploader(jwtToken: string): string {
  const payload = parseJwtPayload(jwtToken);
  const claims = [payload?.email, payload?.preferred_username, payload?.sub];
  const uploader = claims.find(
    (claim): claim is string => typeof claim === 'string' && claim.trim() !== ''
  );
  return uploader ?? UNKNOWN_UPLOADER;
}

// Handled failures come back as `{ error, message }`, rejected requests (400, 401) as
// `{ detail: { error, message } }`.
export function readErrorMessage(payload: ErrorPayload): string | undefined {
  return payload.message ?? payload.detail?.message;
}

async function requestJobId(input: AnalysisInput): Promise<string> {
  const analyzeUrl = `${normalizeBaseUrl(input.apiBaseUrl)}/api/v1/analyze`;

  const formData = new FormData();
  formData.append('file', input.file, input.file.name);
  formData.append('sender', describeUploader(input.jwtToken));
  formData.append('subject', `Manual upload: ${input.file.name}`);
  formData.append('body_text', 'Manual file upload from extension drag-and-drop UI.');

  const response = await fetch(analyzeUrl, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${input.jwtToken}`
    },
    body: formData
  });

  if (!response.ok) {
    let message = `Analyze request failed (${response.status}).`;

    try {
      message = readErrorMessage((await response.json()) as ErrorPayload) ?? message;
    } catch {
      // Keep fallback message when body is not JSON.
    }

    throw new ApiError(message, response.status);
  }

  const payload = (await response.json()) as { job_id?: string };

  if (!payload.job_id) {
    throw new ApiError('Backend response did not include a job_id.');
  }

  return payload.job_id;
}

async function waitForVerdict(
  apiBaseUrl: string,
  jwtToken: string,
  jobId: string,
  timeoutMs: number
): Promise<AnalysisOutcome> {
  return await new Promise<AnalysisOutcome>((resolve, reject) => {
    const socket = new WebSocket(buildWebSocketUrl(apiBaseUrl, jobId, jwtToken));

    const timeoutHandle = setTimeout(() => {
      socket.close();
      resolve({ kind: 'timeout', jobId });
    }, timeoutMs);

    socket.addEventListener('message', (event) => {
      try {
        const verdict = JSON.parse(String(event.data)) as VerdictMessage;
        clearTimeout(timeoutHandle);
        socket.close();
        resolve({ kind: 'verdict', jobId, verdict });
      } catch {
        clearTimeout(timeoutHandle);
        socket.close();
        reject(new ApiError('Received invalid verdict payload from WebSocket.'));
      }
    });

    // Fires after the verdict message too; the promise is settled by then, so it is a no-op.
    socket.addEventListener('close', (event) => {
      clearTimeout(timeoutHandle);

      if (event.code === WS_CLOSE_TIMEOUT) {
        resolve({ kind: 'timeout', jobId });
      } else if (event.code === WS_CLOSE_AUTH_FAILED) {
        reject(new ApiError('WebSocket authentication failed. Check JWT token.'));
      } else {
        reject(
          new ApiError(`Verdict channel closed before the verdict arrived (code ${event.code}).`)
        );
      }
    });

    socket.addEventListener('error', () => {
      clearTimeout(timeoutHandle);
      reject(new ApiError('WebSocket connection failed while waiting for verdict.'));
    });
  });
}

export async function runAnalysis(input: AnalysisInput): Promise<AnalysisOutcome> {
  const jobId = await requestJobId(input);
  const timeoutMs = input.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  return await waitForVerdict(input.apiBaseUrl, input.jwtToken, jobId, timeoutMs);
}
