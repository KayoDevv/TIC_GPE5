import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import AnalysisErrorPanel from '../../src/ui/components/AnalysisErrorPanel.vue';
import AnalysisProgress from '../../src/ui/components/AnalysisProgress.vue';
import AnalysisTabs from '../../src/ui/components/AnalysisTabs.vue';
import FileDropZone from '../../src/ui/components/FileDropZone.vue';
import HistoryPanel from '../../src/ui/components/HistoryPanel.vue';
import PopupHeader from '../../src/ui/components/PopupHeader.vue';
import VerdictPanel from '../../src/ui/components/VerdictPanel.vue';
import type { VerdictDetails } from '../../src/ui/verdictPresentation';

const NO_DETAILS: VerdictDetails = { tiles: [], badges: [], indicators: [] };

const BLOCKED_DETAILS: VerdictDetails = {
  tiles: [{ label: 'Risk score', value: '94 / 100' }],
  badges: [{ label: 'Threat model: malicious', tone: 'blocked' }],
  indicators: [{ code: 'T1055', text: 'Process Injection' }]
};

function buildFile(): File {
  return new File(['payload'], 'sample.pdf', { type: 'application/pdf' });
}

describe('FileDropZone', () => {
  it('emits the dropped file', async () => {
    const wrapper = mount(FileDropZone);

    await wrapper.trigger('drop', { dataTransfer: { files: [buildFile()] } });

    expect(wrapper.emitted('select')?.[0]?.[0]).toBeInstanceOf(File);
  });

  it('stays silent when the drop carries no file', async () => {
    const wrapper = mount(FileDropZone);

    await wrapper.trigger('drop', { dataTransfer: { files: [] } });

    expect(wrapper.emitted('select')).toBeUndefined();
  });

  it('exposes a labelled file input so the zone opens the browse dialog', () => {
    const wrapper = mount(FileDropZone);

    expect(wrapper.element.tagName).toBe('LABEL');
    expect(wrapper.find('input[type="file"]').attributes('aria-label')).toBe(
      'Choose a file to analyse'
    );
  });

  it('emits the file picked from the browse dialog', async () => {
    const wrapper = mount(FileDropZone);
    const input = wrapper.find('input').element;
    Object.defineProperty(input, 'files', { value: [buildFile()], configurable: true });

    await wrapper.find('input').trigger('change');

    expect(wrapper.emitted('select')?.[0]?.[0]).toBeInstanceOf(File);
  });

  it('announces the release hint while a file hovers the zone', async () => {
    const wrapper = mount(FileDropZone);

    await wrapper.trigger('dragover');
    expect(wrapper.text()).toContain('release to analyse');
    expect(wrapper.classes()).toContain('dragging');

    await wrapper.trigger('dragleave');
    expect(wrapper.text()).toContain('drop an attachment here');
  });
});

describe('PopupHeader', () => {
  it('exposes the analysis status on the glyph and colours the lockup by state', () => {
    const wrapper = mount(PopupHeader, {
      props: { state: 'blocked', statusLabel: 'Complete', theme: 'light' }
    });

    expect(wrapper.classes()).toContain('blocked');
    expect(wrapper.find('[role="img"]').attributes('aria-label')).toBe('Complete');
  });

  it('asks for a theme switch and for the popup to close', async () => {
    const wrapper = mount(PopupHeader, {
      props: { state: 'idle', statusLabel: 'Standby', theme: 'dark' }
    });

    const [themeButton, closeButton] = wrapper.findAll('button');
    expect(themeButton.attributes('aria-label')).toBe('Switch to light theme');
    await themeButton.trigger('click');
    await closeButton.trigger('click');

    expect(wrapper.emitted('toggleTheme')).toHaveLength(1);
    expect(wrapper.emitted('close')).toHaveLength(1);
  });
});

describe('AnalysisTabs', () => {
  it('emits the tab selected by the user', async () => {
    const wrapper = mount(AnalysisTabs, { props: { activeTab: 'analysis' } });

    await wrapper.findAll('button')[1].trigger('click');

    expect(wrapper.emitted('update:activeTab')?.[0]).toEqual(['history']);
    expect(wrapper.findAll('[role="tab"]')[0].attributes('aria-selected')).toBe('true');
  });
});

describe('AnalysisProgress', () => {
  it('renders elapsed progress as a percentage of the deadline', () => {
    const wrapper = mount(AnalysisProgress, {
      props: { fileName: 'sample.pdf', progressRatio: 0.42 }
    });

    expect(wrapper.text()).toContain('42%');
    expect(wrapper.text()).toContain('sample.pdf');
    expect(wrapper.findAll('.layer')).toHaveLength(3);
  });
});

describe('VerdictPanel', () => {
  it('renders the verdict tone, file and job reference', () => {
    const wrapper = mount(VerdictPanel, {
      props: {
        presentation: { tone: 'blocked', label: 'Malicious', detail: 'Dropper detected.' },
        file: buildFile(),
        details: BLOCKED_DETAILS,
        jobId: 'job-1'
      }
    });

    expect(wrapper.classes()).toContain('blocked');
    expect(wrapper.text()).toContain('Malicious');
    expect(wrapper.text()).toContain('Dropper detected.');
    expect(wrapper.text()).toContain('sample.pdf · 7 B');
    expect(wrapper.text()).toContain('job-1');
  });

  it('keeps the technical details folded until asked', async () => {
    const wrapper = mount(VerdictPanel, {
      props: {
        presentation: { tone: 'blocked', label: 'Malicious', detail: 'Dropper detected.' },
        file: null,
        details: BLOCKED_DETAILS,
        jobId: null
      }
    });

    expect(wrapper.text()).not.toContain('94 / 100');

    await wrapper.find('.details-toggle').trigger('click');

    expect(wrapper.text()).toContain('94 / 100');
    expect(wrapper.text()).toContain('T1055');
    expect(wrapper.text()).toContain('Process Injection');
    expect(wrapper.find('.badge').classes()).toContain('blocked');
    expect(wrapper.find('.details-toggle').text()).toBe('Hide details');
  });

  it('hides the details toggle when nothing was reported', () => {
    const wrapper = mount(VerdictPanel, {
      props: {
        presentation: { tone: 'warning', label: 'Timed out', detail: 'Deadline exceeded.' },
        file: null,
        details: NO_DETAILS,
        jobId: null
      }
    });

    expect(wrapper.find('.details-toggle').exists()).toBe(false);
  });

  it('asks for a new analysis when the action is used', async () => {
    const wrapper = mount(VerdictPanel, {
      props: {
        presentation: { tone: 'allowed', label: 'Clean', detail: 'No threat detected.' },
        file: null,
        details: NO_DETAILS,
        jobId: null
      }
    });

    await wrapper.find('.popup-button').trigger('click');

    expect(wrapper.emitted('restart')).toHaveLength(1);
  });
});

describe('AnalysisErrorPanel', () => {
  it('reports the failure and offers a retry', async () => {
    const wrapper = mount(AnalysisErrorPanel, {
      props: { message: 'Analyze request failed (413).' }
    });

    expect(wrapper.text()).toContain('Analyze request failed (413).');

    await wrapper.findAll('button')[1].trigger('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
  });

  it('offers to start over with another file', async () => {
    const wrapper = mount(AnalysisErrorPanel, {
      props: { message: 'No valid SSO JWT found automatically.' }
    });

    await wrapper.find('button').trigger('click');

    expect(wrapper.emitted('restart')).toHaveLength(1);
  });
});

describe('HistoryPanel', () => {
  it('says so when nothing was analysed yet', () => {
    const wrapper = mount(HistoryPanel, { props: { entries: [] } });

    expect(wrapper.text()).toContain('no analysis yet.');
  });

  it('lists past verdicts with their decision and risk score', () => {
    const wrapper = mount(HistoryPanel, {
      props: {
        entries: [
          { name: 'setup.exe', decision: 'blocked', score: 96, time: 2 },
          { name: 'image.iso', decision: 'warning', score: null, time: 1 }
        ]
      }
    });

    const rows = wrapper.findAll('.row');
    expect(rows).toHaveLength(2);
    expect(rows[0].text()).toContain('setup.exe');
    expect(rows[0].text()).toContain('96/100');
    expect(rows[0].find('.dot').classes()).toContain('blocked');
    expect(rows[1].find('.score').exists()).toBe(false);
  });
});
