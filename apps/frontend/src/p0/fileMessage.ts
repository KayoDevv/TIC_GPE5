/** Carries a picked or dropped file to the background worker, which owns the analysis. */

export const ANALYSE_MESSAGE = 'charon:analyse';
export const RETRY_MESSAGE = 'charon:retry';
export const RESET_MESSAGE = 'charon:reset';

export interface AnalyseMessage {
  type: typeof ANALYSE_MESSAGE;
  name: string;
  mimeType: string;
  // Extension messages are JSON: a File or an ArrayBuffer would arrive as `{}`.
  base64: string;
}

export type CharonMessage =
  | AnalyseMessage
  | { type: typeof RETRY_MESSAGE }
  | { type: typeof RESET_MESSAGE };

// String.fromCharCode takes its bytes as arguments, which overflow the call stack past ~100k.
const ENCODE_CHUNK_BYTES = 0x8000;

export async function encodeFile(file: File): Promise<AnalyseMessage> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += ENCODE_CHUNK_BYTES) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + ENCODE_CHUNK_BYTES));
  }

  return { type: ANALYSE_MESSAGE, name: file.name, mimeType: file.type, base64: btoa(binary) };
}

export function decodeFile(message: AnalyseMessage): File {
  const binary = atob(message.base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return new File([bytes], message.name, { type: message.mimeType });
}

export async function sendToBackground(message: CharonMessage): Promise<void> {
  if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
    await chrome.runtime.sendMessage(message);
  }
}
