/** Popup navigation tabs; only the file tab is implemented in the current scope. */

export type AnalysisTabKey = 'file' | 'hash' | 'url';

export interface AnalysisTab {
  key: AnalysisTabKey;
  label: string;
}

export const ANALYSIS_TABS: AnalysisTab[] = [
  { key: 'file', label: 'File' },
  { key: 'hash', label: 'Hash' },
  { key: 'url', label: 'URL' }
];
