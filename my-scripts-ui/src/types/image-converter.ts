export type ImageFormat = 'jpg' | 'jpeg' | 'png' | 'webp' | 'avif' | 'bmp' | 'tiff' | 'gif' | 'svg' | 'ico';

export interface ImageFile {
  id: string;
  file: File;
  name: string;
  customName?: string; // For renaming functionality
  size: number;
  type: string;
  preview: string;
  originalFormat: string;
  status: 'pending' | 'converting' | 'completed' | 'error';
  convertedBlob?: Blob;
  convertedUrl?: string;
  error?: string;
}

export interface ConversionSettings {
  format: ImageFormat;
  quality: number; // 1-100
  width?: number;
  height?: number;
  maintainAspectRatio: boolean;
  removeMetadata: boolean;
  backgroundColor?: string; // For formats that don't support transparency
}

export interface ConversionProgress {
  current: number;
  total: number;
  percentage: number;
  currentFile: string;
}

export const SUPPORTED_INPUT_FORMATS = [
  'image/jpeg',
  'image/jpg', 
  'image/png',
  'image/webp',
  'image/avif',
  'image/bmp',
  'image/tiff',
  'image/gif',
  'image/svg+xml'
];

export const OUTPUT_FORMATS: Array<{ value: ImageFormat; label: string; description: string; supportsTransparency: boolean }> = [
  { value: 'jpg', label: 'JPEG', description: 'Ideal para fotografías', supportsTransparency: false },
  { value: 'png', label: 'PNG', description: 'Ideal para gráficos con transparencia', supportsTransparency: true },
  { value: 'webp', label: 'WebP', description: 'Formato moderno, menor tamaño', supportsTransparency: true },
  { value: 'avif', label: 'AVIF', description: 'Último formato, excelente compresión', supportsTransparency: true },
  { value: 'bmp', label: 'BMP', description: 'Formato sin compresión', supportsTransparency: false },
  { value: 'tiff', label: 'TIFF', description: 'Formato profesional', supportsTransparency: true },
  { value: 'gif', label: 'GIF', description: 'Para animaciones simples', supportsTransparency: true },
  { value: 'ico', label: 'ICO', description: 'Para iconos de aplicaciones', supportsTransparency: true }
];