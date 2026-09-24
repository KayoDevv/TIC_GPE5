/** Popup navigation tabs: the analysis flow and the local verdict history. */

export type AnalysisTabKey = 'analysis' | 'history';

export interface AnalysisTab {
  key: AnalysisTabKey;
  label: string;
}

export const ANALYSIS_TABS: AnalysisTab[] = [
  { key: 'analysis', label: 'Analysis' },
  { key: 'history', label: 'History' }
];
