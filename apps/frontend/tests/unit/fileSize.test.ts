import { describe, expect, it } from 'vitest';
import { formatFileSize } from '../../src/ui/fileSize';

describe('formatFileSize', () => {
  it('renders sizes below one kilobyte in bytes', () => {
    expect(formatFileSize(0)).toBe('0 B');
    expect(formatFileSize(512)).toBe('512 B');
  });

  it('renders sizes below one megabyte in kilobytes with one decimal', () => {
    expect(formatFileSize(1024)).toBe('1.0 KB');
    expect(formatFileSize(2048)).toBe('2.0 KB');
  });

  it('renders larger sizes in megabytes with two decimals', () => {
    expect(formatFileSize(2_400_000)).toBe('2.29 MB');
  });

  it('renders a placeholder for unusable sizes', () => {
    expect(formatFileSize(-1)).toBe('—');
    expect(formatFileSize(Number.NaN)).toBe('—');
  });
});
