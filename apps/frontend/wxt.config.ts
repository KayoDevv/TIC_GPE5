import { defineConfig } from 'wxt';

export default defineConfig({
  modules: ['@wxt-dev/module-vue'],
  manifest: {
    name: 'Charon',
    description: 'Drag-and-drop attachment analysis with a zero-trust verdict.',
    permissions: ['storage', 'activeTab', 'scripting', 'tabs'],
    host_permissions: ['http://*/*', 'https://*/*'],
    action: {
      default_title: 'Charon — file analysis',
      default_popup: 'popup/index.html'
    }
  }
});
