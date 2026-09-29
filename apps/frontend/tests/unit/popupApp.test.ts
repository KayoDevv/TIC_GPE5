import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../../entrypoints/popup/App.vue';
import { IDLE_SNAPSHOT, type AnalysisSnapshot } from '../../src/p0/session';
import { stubChrome, type FakeChrome } from './fakeChromeStorage';

const FILE = { name: 'invoice.pdf', size: 7 };

const BLOCKED: AnalysisSnapshot = {
  ...IDLE_SNAPSHOT,
  phase: 'completed',
  file: FILE,
  jobId: 'job-9',
  verdict: {
    job_id: 'job-9',
    final_decision: 'blocked',
    user_explanation: 'The document drops an executable payload.',
    technical_summary: { ml_layer_score: 94, llm_layer_malicious: true },
    timestamp: '2026-08-13T10:00:00Z'
  }
};

async function mountWith(snapshot: AnalysisSnapshot, extra: Record<string, unknown> = {}) {
  const fake = stubChrome({ charonSession: snapshot, ...extra });
  const wrapper = mount(App);
  await flushPromises();
  return { wrapper, fake };
}

async function publish(fake: FakeChrome, snapshot: AnalysisSnapshot): Promise<void> {
  await chrome.storage.local.set({ charonSession: snapshot });
  fake.data.charonSession = snapshot;
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.classList.remove('theme-dark');
});

describe('popup application', () => {
  it('opens on the drop zone without any session label', async () => {
    const { wrapper } = await mountWith(IDLE_SNAPSHOT);

    expect(wrapper.text()).toContain('drop an attachment here');
    expect(wrapper.find('[role="img"]').attributes('aria-label')).toBe('Standby');
    expect(wrapper.text()).not.toContain('Session token');
  });

  it('hands a dropped file to the background worker', async () => {
    const { wrapper, fake } = await mountWith(IDLE_SNAPSHOT);

    await wrapper.find('.drop-zone').trigger('drop', {
      dataTransfer: { files: [new File(['payload'], FILE.name, { type: 'application/pdf' })] }
    });

    await vi.waitFor(() =>
      expect(fake.sent).toMatchObject([{ type: 'charon:analyse', name: FILE.name }])
    );
  });

  it('shows the analysis the worker is running, even one started elsewhere', async () => {
    const { wrapper, fake } = await mountWith(IDLE_SNAPSHOT);

    await publish(fake, { ...IDLE_SNAPSHOT, phase: 'analyzing', file: FILE, startedAt: Date.now() });

    expect(wrapper.text()).toContain('invoice.pdf');
    expect(wrapper.find('.popup-shell').classes()).toContain('analyzing');
  });

  it('renders the verdict and its details', async () => {
    const { wrapper } = await mountWith(BLOCKED);

    expect(wrapper.text()).toContain('Malicious');
    expect(wrapper.text()).toContain('The document drops an executable payload.');
    expect(wrapper.find('.popup-shell').classes()).toContain('blocked');

    await wrapper.find('.details-toggle').trigger('click');

    expect(wrapper.text()).toContain('94 / 100');
    expect(wrapper.text()).toContain('Threat model: malicious');
  });

  it('asks the worker to start over after a verdict', async () => {
    const { wrapper, fake } = await mountWith(BLOCKED);

    await wrapper.find('.verdict .popup-button').trigger('click');
    await flushPromises();

    expect(fake.sent).toEqual([{ type: 'charon:reset' }]);
  });

  it('treats an analysis timeout as a suspicious verdict', async () => {
    const { wrapper } = await mountWith({ ...BLOCKED, verdict: null, timedOut: true });

    expect(wrapper.text()).toContain('Timed out');
    expect(wrapper.find('.verdict').classes()).toContain('warning');
  });

  it('renders a failed analysis and asks the worker to retry', async () => {
    const { wrapper, fake } = await mountWith({
      ...IDLE_SNAPSHOT,
      phase: 'failed',
      file: FILE,
      error: 'Analyze request failed (413).'
    });

    expect(wrapper.text()).toContain('Analysis failed');
    expect(wrapper.text()).toContain('Analyze request failed (413).');

    await wrapper.findAll('.popup-button')[1].trigger('click');
    await flushPromises();

    expect(fake.sent).toEqual([{ type: 'charon:retry' }]);
  });

  it('lists past verdicts in the history tab', async () => {
    const { wrapper } = await mountWith(BLOCKED, {
      charonHistory: [{ name: 'invoice.pdf', decision: 'blocked', score: 94, time: 1 }]
    });

    await wrapper.findAll('.tab')[1].trigger('click');

    expect(wrapper.find('.history').text()).toContain('invoice.pdf');
    expect(wrapper.find('.history').text()).toContain('94/100');
  });

  it('switches to the dark theme from the header', async () => {
    const { wrapper } = await mountWith(IDLE_SNAPSHOT);

    await wrapper.find('.header button').trigger('click');

    expect(document.documentElement.classList.contains('theme-dark')).toBe(true);
  });
});
