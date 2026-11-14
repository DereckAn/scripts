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
  convertedFormat?: ImageFormat;
  convertedName?: string;
  error?: string;
}

export interface ConversionSettings {
  format: ImageFormat;
  quality: number; // 1-100
  width?: number;
  height?: number;
  maintainAspectRatio: boolean;
  backgroundColor?: string; // For formats that don't support transparency
  flattenTransparency?: boolean;
}

export interface ConversionProgress {
  current: number;
  total: number;
  percentage: number;
  currentFile: string;
}

export const OUTPUT_FORMATS: Array<{ value: ImageFormat; supportsTransparency: boolean }> = [
  { value: 'jpg', supportsTransparency: false },
  { value: 'png', supportsTransparency: true },
  { value: 'webp', supportsTransparency: true },
  { value: 'avif', supportsTransparency: true },
  { value: 'bmp', supportsTransparency: false },
  { value: 'tiff', supportsTransparency: true },
  { value: 'gif', supportsTransparency: true },
  { value: 'ico', supportsTransparency: true }
];
