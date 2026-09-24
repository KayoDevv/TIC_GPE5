import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../../entrypoints/popup/App.vue';
import { ApiError, runAnalysis, type AnalysisOutcome } from '../../src/p0/network';
import { loadSettings } from '../../src/p0/settings';
import { resolveJwtTokenAutomatically } from '../../src/p0/tokenResolver';

vi.mock('../../src/p0/network', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/p0/network')>();
  return { ...actual, runAnalysis: vi.fn() };
});

vi.mock('../../src/p0/settings', () => ({ loadSettings: vi.fn() }));

vi.mock('../../src/p0/tokenResolver', () => ({ resolveJwtTokenAutomatically: vi.fn() }));

const BLOCKED_OUTCOME: AnalysisOutcome = {
  kind: 'verdict',
  jobId: 'job-9',
  verdict: {
    job_id: 'job-9',
    final_decision: 'blocked',
    user_explanation: 'The document drops an executable payload.',
    technical_summary: { ml_layer_score: 94, llm_layer_malicious: true },
    timestamp: '2026-08-13T10:00:00Z'
  }
};

function buildFile(): File {
  return new File(['payload'], 'invoice.pdf', { type: 'application/pdf' });
}

async function mountWithDroppedFile(): Promise<ReturnType<typeof mount>> {
  const wrapper = mount(App);
  await wrapper.find('.drop-zone').trigger('drop', { dataTransfer: { files: [buildFile()] } });
  return wrapper;
}

describe('popup application', () => {
  beforeEach(() => {
    vi.mocked(loadSettings).mockResolvedValue({
      apiBaseUrl: 'http://localhost:8000',
      cachedJwtToken: 'cached-token'
    });
    vi.mocked(resolveJwtTokenAutomatically).mockResolvedValue('cached-token');
    vi.mocked(runAnalysis).mockResolvedValue(BLOCKED_OUTCOME);
  });

  it('opens on the drop zone with an unresolved session', () => {
    const wrapper = mount(App);

    expect(wrapper.text()).toContain('drop an attachment here');
    expect(wrapper.find('[role="img"]').attributes('aria-label')).toBe('Standby');
    expect(wrapper.text()).toContain('Session token: not resolved');
  });

  it('starts the analysis as soon as a file is dropped', async () => {
    const wrapper = await mountWithDroppedFile();

    expect(runAnalysis).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain('invoice.pdf');
  });

  it('renders the verdict returned by the analysis layers', async () => {
    const wrapper = await mountWithDroppedFile();
    await flushPromises();

    expect(wrapper.text()).toContain('Malicious');
    expect(wrapper.text()).toContain('The document drops an executable payload.');
    expect(wrapper.text()).toContain('Session token: cached');
    expect(wrapper.find('.popup-shell').classes()).toContain('blocked');

    await wrapper.find('.details-toggle').trigger('click');

    expect(wrapper.text()).toContain('94 / 100');
    expect(wrapper.text()).toContain('Threat model: malicious');
  });

  it('returns to the drop zone after the verdict is acknowledged', async () => {
    const wrapper = await mountWithDroppedFile();
    await flushPromises();

    await wrapper.find('.verdict .popup-button').trigger('click');

    expect(wrapper.text()).toContain('drop an attachment here');
    expect(wrapper.find('.popup-shell').classes()).toContain('idle');
  });

  it('treats an analysis timeout as a suspicious verdict', async () => {
    vi.mocked(runAnalysis).mockResolvedValue({ kind: 'timeout', jobId: 'job-10' });
    const wrapper = await mountWithDroppedFile();
    await flushPromises();

    expect(wrapper.text()).toContain('Timed out');
    expect(wrapper.find('.verdict').classes()).toContain('warning');
  });

  it('renders a failed analysis with a retry action', async () => {
    vi.mocked(runAnalysis).mockRejectedValueOnce(new ApiError('Analyze request failed (413).'));
    const wrapper = await mountWithDroppedFile();
    await flushPromises();

    expect(wrapper.text()).toContain('Analysis failed');
    expect(wrapper.text()).toContain('Analyze request failed (413).');

    await wrapper.findAll('.popup-button')[1].trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('Malicious');
  });

  it('lists the verdict in the history tab', async () => {
    const wrapper = await mountWithDroppedFile();
    await flushPromises();

    await wrapper.findAll('.tab')[1].trigger('click');

    expect(wrapper.find('.history').text()).toContain('invoice.pdf');
    expect(wrapper.find('.history').text()).toContain('94/100');
    expect(wrapper.text()).not.toContain('drop an attachment here');
  });

  it('switches to the dark theme from the header', async () => {
    const wrapper = mount(App);

    await wrapper.find('.header button').trigger('click');

    expect(document.documentElement.classList.contains('theme-dark')).toBe(true);
  });
});
