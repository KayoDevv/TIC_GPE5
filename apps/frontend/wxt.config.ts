import { defineConfig } from 'wxt';

export default defineConfig({
  modules: ['@wxt-dev/module-vue'],
  manifest: {
    name: 'Endpoint Guard P0',
    description: 'P0 drag-and-drop attachment analysis flow.',
    permissions: ['storage', 'activeTab', 'scripting', 'tabs'],
    host_permissions: ['http://*/*', 'https://*/*'],
    action: {
      default_title: 'Endpoint Guard P0',
      default_popup: 'popup/index.html'
    }
  }
});
