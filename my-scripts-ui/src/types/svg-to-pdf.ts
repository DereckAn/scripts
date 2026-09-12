export type PageSizeMode = 'auto' | 'a4' | 'letter';

export interface SvgFile {
  id: string;
  file: File;
  name: string;
  size: number;
  /** Blob URL used for the thumbnail preview. */
  preview: string;
  /** Raw SVG markup, read once on upload. */
  content: string;
  /** Intrinsic size in pixels, taken from width/height or viewBox. */
  width: number;
  height: number;
  error?: string;
}

export interface PdfSettings {
  pageSize: PageSizeMode;
  /** Outer margin in millimeters, applied when pageSize is not 'auto'. */
  margin: number;
  fileName: string;
}

export interface PdfProgress {
  current: number;
  total: number;
  percentage: number;
  currentFile: string;
}

/** Page dimensions in millimeters. */
export const PAGE_SIZES_MM: Record<Exclude<PageSizeMode, 'auto'>, { width: number; height: number }> = {
  a4: { width: 210, height: 297 },
  letter: { width: 215.9, height: 279.4 },
};

export const PAGE_SIZE_OPTIONS: Array<{ value: PageSizeMode; label: string; description: string }> = [
  { value: 'auto', label: 'Automático', description: 'Cada página conserva el tamaño original del SVG' },
  { value: 'a4', label: 'A4', description: '210 × 297 mm, el estándar para partituras' },
  { value: 'letter', label: 'Carta', description: '216 × 279 mm, estándar en Norteamérica' },
];

export const MAX_SVG_SIZE = 25 * 1024 * 1024; // 25MB por archivo
