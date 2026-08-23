/** Human-readable rendering of a file size, used by the file cards. */

interface SizeUnit {
  maxBytes: number;
  divisor: number;
  fractionDigits: number;
  suffix: string;
}

const BYTES_PER_KILOBYTE = 1024;
const BYTES_PER_MEGABYTE = BYTES_PER_KILOBYTE * BYTES_PER_KILOBYTE;

const SMALL_SIZE_UNITS: SizeUnit[] = [
  { maxBytes: BYTES_PER_KILOBYTE, divisor: 1, fractionDigits: 0, suffix: 'B' },
  { maxBytes: BYTES_PER_MEGABYTE, divisor: BYTES_PER_KILOBYTE, fractionDigits: 1, suffix: 'KB' }
];

const LARGE_SIZE_UNIT: SizeUnit = {
  maxBytes: Number.POSITIVE_INFINITY,
  divisor: BYTES_PER_MEGABYTE,
  fractionDigits: 2,
  suffix: 'MB'
};

const UNKNOWN_SIZE = '—';

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return UNKNOWN_SIZE;
  }

  const unit = SMALL_SIZE_UNITS.find((candidate) => bytes < candidate.maxBytes) ?? LARGE_SIZE_UNIT;
  return `${(bytes / unit.divisor).toFixed(unit.fractionDigits)} ${unit.suffix}`;
}
