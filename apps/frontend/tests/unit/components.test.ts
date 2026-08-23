import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import AnalysisErrorPanel from '../../src/ui/components/AnalysisErrorPanel.vue';
import AnalysisProgress from '../../src/ui/components/AnalysisProgress.vue';
import AnalysisTabs from '../../src/ui/components/AnalysisTabs.vue';
import FileDropZone from '../../src/ui/components/FileDropZone.vue';
import SelectedFileCard from '../../src/ui/components/SelectedFileCard.vue';
import VerdictPanel from '../../src/ui/components/VerdictPanel.vue';

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
    expect(wrapper.text()).toContain('Release to analyse');

    await wrapper.trigger('dragleave');
    expect(wrapper.text()).toContain('Drop a file here');
  });
});

describe('SelectedFileCard', () => {
  it('renders the file name and its human-readable size', () => {
    const wrapper = mount(SelectedFileCard, { props: { file: buildFile() } });

    expect(wrapper.text()).toContain('sample.pdf');
    expect(wrapper.text()).toContain('7 B');
    expect(wrapper.find('button').exists()).toBe(false);
  });

  it('emits a removal request when it is removable', async () => {
    const wrapper = mount(SelectedFileCard, { props: { file: buildFile(), removable: true } });

    await wrapper.find('button').trigger('click');

    expect(wrapper.emitted('remove')).toHaveLength(1);
  });
});

describe('AnalysisTabs', () => {
  it('emits the tab selected by the user', async () => {
    const wrapper = mount(AnalysisTabs, { props: { activeTab: 'file' } });

    await wrapper.findAll('button')[1].trigger('click');

    expect(wrapper.emitted('update:activeTab')?.[0]).toEqual(['hash']);
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
  it('renders the verdict tone, metrics and job reference', () => {
    const wrapper = mount(VerdictPanel, {
      props: {
        presentation: { tone: 'blocked', label: 'Malicious', detail: 'Dropper detected.' },
        file: buildFile(),
        metrics: [{ label: 'Risk score', value: '94 / 100' }],
        jobId: 'job-1'
      }
    });

    expect(wrapper.find('.verdict').classes()).toContain('blocked');
    expect(wrapper.text()).toContain('Malicious');
    expect(wrapper.text()).toContain('94 / 100');
    expect(wrapper.text()).toContain('job-1');
  });

  it('asks for a new analysis when the action is used', async () => {
    const wrapper = mount(VerdictPanel, {
      props: {
        presentation: { tone: 'allowed', label: 'Clean', detail: 'No threat detected.' },
        file: null,
        metrics: [],
        jobId: null
      }
    });

    await wrapper.find('button').trigger('click');

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
