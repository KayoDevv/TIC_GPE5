import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ANALYSE_MESSAGE,
  decodeFile,
  encodeFile,
  RESET_MESSAGE,
  sendToBackground
} from '../../src/p0/fileMessage';
import { stubChrome } from './fakeChromeStorage';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('file message', () => {
  it('carries every byte, the name and the type through a JSON message', async () => {
    // Every byte value, repeated past the encoder's chunk size.
    const bytes = Uint8Array.from({ length: 70_000 }, (_, index) => index % 256);
    const file = new File([bytes], 'sample.bin', { type: 'application/octet-stream' });

    const message = JSON.parse(JSON.stringify(await encodeFile(file)));
    const restored = decodeFile(message);

    expect(message.type).toBe(ANALYSE_MESSAGE);
    expect(restored.name).toBe('sample.bin');
    expect(restored.type).toBe('application/octet-stream');
    expect(new Uint8Array(await restored.arrayBuffer())).toEqual(bytes);
  });

  it('reaches the background worker', async () => {
    const fake = stubChrome();

    await sendToBackground({ type: RESET_MESSAGE });

    expect(fake.sent).toEqual([{ type: RESET_MESSAGE }]);
  });

  it('is a no-op outside of an extension context', async () => {
    vi.stubGlobal('chrome', undefined);

    await expect(sendToBackground({ type: RESET_MESSAGE })).resolves.toBeUndefined();
  });
});
