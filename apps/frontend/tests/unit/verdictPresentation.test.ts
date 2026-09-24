import { describe, expect, it } from 'vitest';
import type { VerdictMessage } from '../../src/p0/network';
import {
  buildVerdictDetails,
  hasVerdictDetails,
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

describe('buildVerdictDetails', () => {
  it('returns nothing without a technical summary', () => {
    const empty = { tiles: [], badges: [], indicators: [] };
    expect(buildVerdictDetails(null)).toEqual(empty);
    expect(buildVerdictDetails(undefined)).toEqual(empty);
    expect(hasVerdictDetails(empty)).toBe(false);
  });

  it('skips fields the verdict layer did not report', () => {
    const details = buildVerdictDetails({ ml_layer_score: 42 });

    expect(details).toEqual({
      tiles: [{ label: 'Risk score', value: '42 / 100' }],
      badges: [],
      indicators: []
    });
    expect(hasVerdictDetails(details)).toBe(true);
  });

  it('renders every reported field', () => {
    const details = buildVerdictDetails({
      ml_layer_score: 94,
      sandbox_layer_iocs: [
        { type: 'ip', value: '185.220.101.4', mitre_tactic: 'T1071', description: 'C2 beacon' },
        { type: 'domain', value: 'cdn.example.net' }
      ],
      sandbox_layer_timeout: true,
      llm_layer_malicious: false
    });

    expect(details.tiles).toEqual([
      { label: 'Risk score', value: '94 / 100' },
      { label: 'Indicators', value: '2' }
    ]);
    expect(details.badges).toEqual([
      { label: 'Threat model: clean', tone: null },
      { label: 'Sandbox: timed out', tone: 'warning' }
    ]);
    expect(details.indicators).toEqual([
      { code: 'T1071', text: 'C2 beacon' },
      { code: 'domain', text: 'cdn.example.net' }
    ]);
  });

  it('flags a malicious threat model and a completed sandbox run', () => {
    expect(
      buildVerdictDetails({ sandbox_layer_timeout: false, llm_layer_malicious: true }).badges
    ).toEqual([
      { label: 'Threat model: malicious', tone: 'blocked' },
      { label: 'Sandbox: completed', tone: null }
    ]);
  });

  it('keeps an indicator row for an IOC without readable fields', () => {
    expect(buildVerdictDetails({ sandbox_layer_iocs: [{ value: 42 }] }).indicators).toEqual([
      { code: 'IOC', text: '' }
    ]);
  });
});
