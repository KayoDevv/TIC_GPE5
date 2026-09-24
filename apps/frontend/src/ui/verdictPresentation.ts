/** Maps backend verdict payloads to the labels, tones and metrics rendered by the popup. */

import type { TechnicalSummary, VerdictDecision, VerdictMessage } from '../p0/network';

export type VerdictTone = 'allowed' | 'warning' | 'blocked';

export interface VerdictPresentation {
  tone: VerdictTone;
  label: string;
  detail: string;
}

export interface SummaryMetric {
  label: string;
  value: string;
}

export interface SummaryBadge {
  label: string;
  tone: VerdictTone | null;
}

export interface IndicatorRow {
  code: string;
  text: string;
}

export interface VerdictDetails {
  tiles: SummaryMetric[];
  badges: SummaryBadge[];
  indicators: IndicatorRow[];
}

interface DecisionPresentation {
  tone: VerdictTone;
  label: string;
  defaultDetail: string;
}

const RISK_SCORE_SCALE = 100;
const UNKNOWN_INDICATOR_CODE = 'IOC';

const DECISION_PRESENTATIONS: Record<VerdictDecision, DecisionPresentation> = {
  allowed: {
    tone: 'allowed',
    label: 'Clean',
    defaultDetail: 'No threat detected. The download is unlocked.'
  },
  warning: {
    tone: 'warning',
    label: 'Suspicious',
    defaultDetail: 'Weak signals detected. Review the file before opening it.'
  },
  blocked: {
    tone: 'blocked',
    label: 'Malicious',
    defaultDetail: 'Malicious behaviour confirmed. The download is blocked.'
  }
};

export const TIMEOUT_PRESENTATION: VerdictPresentation = {
  tone: 'warning',
  label: 'Timed out',
  detail: 'Analysis exceeded its deadline. The file is treated as suspicious.'
};

export function presentVerdict(verdict: VerdictMessage): VerdictPresentation {
  const presentation = DECISION_PRESENTATIONS[verdict.final_decision];

  return {
    tone: presentation.tone,
    label: presentation.label,
    detail: verdict.user_explanation?.trim() || presentation.defaultDetail
  };
}

function readTiles(summary: TechnicalSummary): SummaryMetric[] {
  const tiles: SummaryMetric[] = [];

  if (summary.ml_layer_score != null) {
    tiles.push({ label: 'Risk score', value: `${summary.ml_layer_score} / ${RISK_SCORE_SCALE}` });
  }

  if (summary.sandbox_layer_iocs != null) {
    tiles.push({ label: 'Indicators', value: String(summary.sandbox_layer_iocs.length) });
  }

  return tiles;
}

function readBadges(summary: TechnicalSummary): SummaryBadge[] {
  const badges: SummaryBadge[] = [];

  if (summary.llm_layer_malicious != null) {
    badges.push(
      summary.llm_layer_malicious
        ? { label: 'Threat model: malicious', tone: 'blocked' }
        : { label: 'Threat model: clean', tone: null }
    );
  }

  if (summary.sandbox_layer_timeout != null) {
    badges.push(
      summary.sandbox_layer_timeout
        ? { label: 'Sandbox: timed out', tone: 'warning' }
        : { label: 'Sandbox: completed', tone: null }
    );
  }

  return badges;
}

function readText(ioc: Record<string, unknown>, key: string): string | null {
  const value = ioc[key];
  return typeof value === 'string' && value.trim() ? value : null;
}

function readIndicators(summary: TechnicalSummary): IndicatorRow[] {
  return (summary.sandbox_layer_iocs ?? []).map((ioc) => ({
    code: readText(ioc, 'mitre_tactic') ?? readText(ioc, 'type') ?? UNKNOWN_INDICATOR_CODE,
    text: readText(ioc, 'description') ?? readText(ioc, 'value') ?? ''
  }));
}

export function buildVerdictDetails(summary: TechnicalSummary | null | undefined): VerdictDetails {
  if (!summary) {
    return { tiles: [], badges: [], indicators: [] };
  }

  return {
    tiles: readTiles(summary),
    badges: readBadges(summary),
    indicators: readIndicators(summary)
  };
}

export function hasVerdictDetails(details: VerdictDetails): boolean {
  return details.tiles.length + details.badges.length + details.indicators.length > 0;
}
