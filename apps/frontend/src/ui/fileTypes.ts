/** File-type vocabulary shared by the drop zone chips and the file cards. */

export const ANALYSED_FILE_EXTENSIONS = [
  'exe',
  'dll',
  'pdf',
  'zip',
  'apk',
  'js',
  'py',
  'jar'
] as const;

const GLYPH_BY_EXTENSION: Record<string, string> = {
  exe: '⚙',
  msi: '⚙',
  bat: '⚙',
  dll: '🔧',
  pdf: '📄',
  zip: '📦',
  js: 'JS',
  py: '🐍',
  doc: '📝',
  docx: '📝',
  sh: '$_',
  apk: '📱',
  jar: '☕'
};

const FALLBACK_GLYPH = '📁';

export function resolveFileGlyph(fileName: string): string {
  const extension = fileName.slice(fileName.lastIndexOf('.') + 1).toLowerCase();
  return GLYPH_BY_EXTENSION[extension] ?? FALLBACK_GLYPH;
}
