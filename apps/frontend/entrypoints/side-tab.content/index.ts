import { createApp } from 'vue';
import { createShadowRootUi } from 'wxt/utils/content-script-ui/shadow-root';
import { defineContentScript } from 'wxt/utils/define-content-script';
import SideTab from '../../src/ui/components/SideTab.vue';
import '../../src/ui/theme.css';

export default defineContentScript({
  matches: ['http://*/*', 'https://*/*'],
  // The tab's styles live in its shadow root: the page's CSS cannot reach in, ours cannot leak.
  cssInjectionMode: 'ui',

  async main(ctx) {
    const ui = await createShadowRootUi(ctx, {
      name: 'charon-side-tab',
      position: 'inline',
      anchor: 'body',
      onMount: (container) => {
        const app = createApp(SideTab);
        app.mount(container);
        return app;
      },
      onRemove: (app) => app?.unmount()
    });

    ui.mount();
  }
});
