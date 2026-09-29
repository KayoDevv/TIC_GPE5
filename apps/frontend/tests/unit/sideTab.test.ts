import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import SideTab from '../../src/ui/components/SideTab.vue';
import { IDLE_SNAPSHOT, type AnalysisSnapshot } from '../../src/p0/session';
import { stubChrome } from './fakeChromeStorage';

const FILE = { name: 'invoice.pdf', size: 7 };

async function mountTab(snapshot: AnalysisSnapshot, extra: Record<string, unknown> = {}) {
  const fake = stubChrome({ charonSession: snapshot, ...extra });
  const wrapper = mount(SideTab, { attachTo: document.body });
  await flushPromises();
  return { wrapper, fake };
}

function fileDrag(type: string): DragEvent {
  const event = new Event(type, { bubbles: true }) as DragEvent;
  Object.defineProperty(event, 'dataTransfer', { value: { types: ['Files'] } });
  return event;
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

describe('SideTab', () => {
  it('sits closed on the page edge until clicked', async () => {
    const { wrapper } = await mountTab(IDLE_SNAPSHOT);

    expect(wrapper.find('.popover').exists()).toBe(false);
    expect(wrapper.find('.pin').attributes('aria-label')).toBe('Charon: Standby');

    await wrapper.find('.pin').trigger('click');

    expect(wrapper.find('.popover').text()).toContain('Drop a file on this tab');
  });

  it('follows the verdict the background worker publishes', async () => {
    const { wrapper } = await mountTab(IDLE_SNAPSHOT);
    await wrapper.find('.pin').trigger('click');

    await chrome.storage.local.set({
      charonSession: {
        ...IDLE_SNAPSHOT,
        phase: 'completed',
        file: FILE,
        verdict: {
          job_id: 'j',
          final_decision: 'blocked',
          user_explanation: 'Dropper detected.',
          technical_summary: { ml_layer_score: 96, sandbox_layer_iocs: [{}, {}, {}] },
          timestamp: 't'
        }
      }
    });

    expect(wrapper.classes()).toContain('blocked');
    expect(wrapper.find('.label').text()).toBe('Malicious');
    expect(wrapper.text()).toContain('Dropper detected.');
    expect(wrapper.text()).toContain('96 / 100');
    expect(wrapper.text()).toContain('3');
  });

  it('shows the running analysis and the failure reason', async () => {
    const { wrapper } = await mountTab({ ...IDLE_SNAPSHOT, phase: 'analyzing', file: FILE });
    await wrapper.find('.pin').trigger('click');

    expect(wrapper.find('.label').text()).toBe('Analysing');
    expect(wrapper.text()).toContain('analysing “invoice.pdf”…');

    await chrome.storage.local.set({
      charonSession: { ...IDLE_SNAPSHOT, phase: 'failed', file: FILE, error: 'Too big.' }
    });

    expect(wrapper.find('.label').text()).toBe('Analysis failed');
    expect(wrapper.text()).toContain('Too big.');
  });

  it('grows into a drop pad while a file is dragged over the page', async () => {
    const { wrapper } = await mountTab(IDLE_SNAPSHOT);

    window.dispatchEvent(fileDrag('dragenter'));
    await flushPromises();
    expect(wrapper.classes()).toContain('dragging');

    window.dispatchEvent(Object.assign(fileDrag('dragleave'), { clientX: 400, clientY: 300 }));
    await flushPromises();
    expect(wrapper.classes()).toContain('dragging');

    window.dispatchEvent(new Event('dragend'));
    await flushPromises();
    expect(wrapper.classes()).not.toContain('dragging');
  });

  it('ignores a drag that carries no file', async () => {
    const { wrapper } = await mountTab(IDLE_SNAPSHOT);
    const textDrag = new Event('dragover', { bubbles: true }) as DragEvent;
    Object.defineProperty(textDrag, 'dataTransfer', { value: { types: ['text/plain'] } });

    window.dispatchEvent(textDrag);
    await flushPromises();

    expect(wrapper.classes()).not.toContain('dragging');
  });

  it('sends a dropped file to the background worker and opens the popover', async () => {
    const { wrapper, fake } = await mountTab(IDLE_SNAPSHOT);

    await wrapper.find('.pin').trigger('drop', {
      dataTransfer: { files: [new File(['payload'], FILE.name, { type: 'application/pdf' })] }
    });

    await vi.waitFor(() => expect(fake.sent).toMatchObject([{ type: 'charon:analyse', name: FILE.name }]));
    expect(wrapper.find('.popover').exists()).toBe(true);
  });

  it('refuses a second file while an analysis runs', async () => {
    const { wrapper, fake } = await mountTab({ ...IDLE_SNAPSHOT, phase: 'analyzing', file: FILE });

    await wrapper.find('.pin').trigger('drop', { dataTransfer: { files: [new File(['x'], 'b.pdf')] } });
    await flushPromises();

    expect(fake.sent).toEqual([]);
  });

  it('uses the popup theme and closes from its own button', async () => {
    const { wrapper } = await mountTab(IDLE_SNAPSHOT, { theme: 'dark' });
    await wrapper.find('.pin').trigger('click');

    expect(wrapper.classes()).toContain('theme-dark');

    await wrapper.find('.close').trigger('click');
    expect(wrapper.find('.popover').exists()).toBe(false);
    wrapper.unmount();
  });
});
