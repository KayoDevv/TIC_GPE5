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

interface DecisionPresentation {
  tone: VerdictTone;
  label: string;
  defaultDetail: string;
}

interface MetricExtractor {
  label: string;
  read: (summary: TechnicalSummary) => string | null;
}

const RISK_SCORE_SCALE = 100;

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

const METRIC_EXTRACTORS: MetricExtractor[] = [
  {
    label: 'Risk score',
    read: (summary) =>
      summary.ml_layer_score == null ? null : `${summary.ml_layer_score} / ${RISK_SCORE_SCALE}`
  },
  {
    label: 'Indicators',
    read: (summary) =>
      summary.sandbox_layer_iocs == null ? null : String(summary.sandbox_layer_iocs.length)
  },
  {
    label: 'Sandbox',
    read: (summary) =>
      summary.sandbox_layer_timeout == null
        ? null
        : summary.sandbox_layer_timeout
          ? 'Timed out'
          : 'Completed'
  },
  {
    label: 'Threat model',
    read: (summary) =>
      summary.llm_layer_malicious == null
        ? null
        : summary.llm_layer_malicious
          ? 'Malicious'
          : 'Clean'
  }
];

export function presentVerdict(verdict: VerdictMessage): VerdictPresentation {
  const presentation = DECISION_PRESENTATIONS[verdict.final_decision];

  return {
    tone: presentation.tone,
    label: presentation.label,
    detail: verdict.user_explanation?.trim() || presentation.defaultDetail
  };
}

export function buildSummaryMetrics(summary: TechnicalSummary | null | undefined): SummaryMetric[] {
  if (!summary) {
    return [];
  }

  return METRIC_EXTRACTORS.map((extractor) => ({
    label: extractor.label,
    value: extractor.read(summary)
  })).filter((metric): metric is SummaryMetric => metric.value !== null);
}
