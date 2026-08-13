export function useExtensionDownload() {
  const url = computed(() => useRuntimeConfig().public.extensionDownloadUrl);
  const available = computed(() => url.value.length > 0);

  return { url, available };
}