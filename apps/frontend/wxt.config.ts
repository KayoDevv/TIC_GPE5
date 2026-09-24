import { defineConfig } from 'wxt';

const IDLE_ICONS = {
  16: 'icons/eye/icon16-idle.png',
  32: 'icons/eye/icon32-idle.png',
  48: 'icons/eye/icon48-idle.png',
  128: 'icons/eye/icon128-idle.png'
};

export default defineConfig({
  modules: ['@wxt-dev/module-vue'],
  manifest: {
    name: 'Charon',
    description: 'Drag-and-drop attachment analysis with a zero-trust verdict.',
    permissions: ['storage', 'activeTab', 'scripting', 'tabs'],
    host_permissions: ['http://*/*', 'https://*/*'],
    icons: IDLE_ICONS,
    action: {
      default_title: 'Charon — file analysis',
      default_popup: 'popup/index.html',
      default_icon: IDLE_ICONS
    }
  }
});
