import { afterEach, describe, expect, it, vi } from 'vitest';
import { IDLE_SNAPSHOT, type AnalysisSnapshot } from '../../src/p0/session';
import { snapshotState, toolbarIconPaths } from '../../src/ui/charonState';

afterEach(() => {
  vi.unstubAllGlobals();
});

function snapshot(overrides: Partial<AnalysisSnapshot>): AnalysisSnapshot {
  return { ...IDLE_SNAPSHOT, ...overrides };
}

describe('snapshotState', () => {
  it('follows the phase and the verdict of the shared snapshot', () => {
    const blocked = { job_id: 'j', final_decision: 'blocked' as const, timestamp: 't' };

    expect(snapshotState(IDLE_SNAPSHOT)).toBe('idle');
    expect(snapshotState(snapshot({ phase: 'analyzing' }))).toBe('analyzing');
    expect(snapshotState(snapshot({ phase: 'completed', verdict: blocked }))).toBe('blocked');
    expect(snapshotState(snapshot({ phase: 'completed', timedOut: true }))).toBe('warning');
    expect(snapshotState(snapshot({ phase: 'completed' }))).toBe('idle');
    expect(snapshotState(snapshot({ phase: 'failed', error: 'x' }))).toBe('idle');
  });
});

describe('toolbarIconPaths', () => {
  it('maps verdict states onto the shipped icon files', () => {
    expect(toolbarIconPaths('allowed')[16]).toBe('icons/eye/icon16-safe.png');
    expect(toolbarIconPaths('warning')[128]).toBe('icons/eye/icon128-warn.png');
    expect(toolbarIconPaths('blocked')[48]).toBe('icons/eye/icon48-danger.png');
    expect(Object.keys(toolbarIconPaths('idle'))).toEqual(['16', '32', '48', '128']);
  });
});
