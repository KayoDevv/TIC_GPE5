import { describe, expect, it } from 'vitest';
import type { VerdictMessage } from '../../src/p0/network';
import {
  buildSummaryMetrics,
  presentVerdict,
  TIMEOUT_PRESENTATION
} from '../../src/ui/verdictPresentation';

function buildVerdict(overrides: Partial<VerdictMessage> = {}): VerdictMessage {
  return {
    job_id: 'job-1',
    final_decision: 'allowed',
    timestamp: '2026-08-13T10:00:00Z',
    ...overrides
  };
}

describe('presentVerdict', () => {
  it('maps every decision to its own tone', () => {
    expect(presentVerdict(buildVerdict({ final_decision: 'allowed' })).tone).toBe('allowed');
    expect(presentVerdict(buildVerdict({ final_decision: 'warning' })).tone).toBe('warning');
    expect(presentVerdict(buildVerdict({ final_decision: 'blocked' })).tone).toBe('blocked');
  });

  it('prefers the explanation produced by the analysis layers', () => {
    const presentation = presentVerdict(buildVerdict({ user_explanation: 'Dropper detected.' }));
    expect(presentation.detail).toBe('Dropper detected.');
  });

  it('falls back to the decision default when no explanation is provided', () => {
    expect(presentVerdict(buildVerdict({ user_explanation: '   ' })).detail).toContain(
      'No threat detected'
    );
  });
});

describe('TIMEOUT_PRESENTATION', () => {
  it('treats a timed-out analysis as suspicious', () => {
    expect(TIMEOUT_PRESENTATION.tone).toBe('warning');
  });
});

describe('buildSummaryMetrics', () => {
  it('returns nothing without a technical summary', () => {
    expect(buildSummaryMetrics(null)).toEqual([]);
    expect(buildSummaryMetrics(undefined)).toEqual([]);
  });

  it('skips fields the verdict layer did not report', () => {
    expect(buildSummaryMetrics({ ml_layer_score: 42 })).toEqual([
      { label: 'Risk score', value: '42 / 100' }
    ]);
  });

  it('renders every reported field', () => {
    const metrics = buildSummaryMetrics({
      ml_layer_score: 94,
      sandbox_layer_iocs: [{ type: 'network' }, { type: 'file' }],
      sandbox_layer_timeout: true,
      llm_layer_malicious: false
    });

    expect(metrics).toEqual([
      { label: 'Risk score', value: '94 / 100' },
      { label: 'Indicators', value: '2' },
      { label: 'Sandbox', value: 'Timed out' },
      { label: 'Threat model', value: 'Clean' }
    ]);
  });

  it('reports a completed sandbox run and a malicious threat model', () => {
    const metrics = buildSummaryMetrics({
      sandbox_layer_timeout: false,
      llm_layer_malicious: true
    });

    expect(metrics).toEqual([
      { label: 'Sandbox', value: 'Completed' },
      { label: 'Threat model', value: 'Malicious' }
    ]);
  });
});
