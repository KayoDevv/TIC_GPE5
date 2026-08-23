import { describe, expect, it } from 'vitest';
import { ANALYSED_FILE_EXTENSIONS, resolveFileGlyph } from '../../src/ui/fileTypes';

describe('resolveFileGlyph', () => {
  it('maps a known extension regardless of case', () => {
    expect(resolveFileGlyph('report.PDF')).toBe(resolveFileGlyph('report.pdf'));
  });

  it('falls back to a generic glyph for unknown extensions', () => {
    expect(resolveFileGlyph('archive.unknown')).toBe('📁');
    expect(resolveFileGlyph('no-extension')).toBe('📁');
  });
});

describe('ANALYSED_FILE_EXTENSIONS', () => {
  it('advertises lowercase extensions without a leading dot', () => {
    for (const extension of ANALYSED_FILE_EXTENSIONS) {
      expect(extension).toBe(extension.toLowerCase());
      expect(extension.startsWith('.')).toBe(false);
    }
  });
});
