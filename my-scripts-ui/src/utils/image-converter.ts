import { ImageFile, ImageFormat, ConversionSettings } from '@/types/image-converter';

export function createImageFile(file: File): ImageFile {
  const id = Math.random().toString(36).substr(2, 9);
  const originalFormat = file.type.split('/')[1] || 'unknown';
  
  return {
    id,
    file,
    name: file.name,
    size: file.size,
    type: file.type,
    preview: URL.createObjectURL(file),
    originalFormat,
    status: 'pending'
  };
}

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export function getMimeType(format: ImageFormat): string {
  const mimeTypes: Record<ImageFormat, string> = {
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    webp: 'image/webp',
    avif: 'image/avif',
    bmp: 'image/bmp',
    tiff: 'image/tiff',
    gif: 'image/gif',
    svg: 'image/svg+xml',
    ico: 'image/x-icon'
  };
  
  return mimeTypes[format] || 'image/jpeg';
}

export async function convertImage(
  imageFile: ImageFile, 
  settings: ConversionSettings
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const img = new Image();
    
    img.onload = () => {
      try {
        // Calculate dimensions
        let { width, height } = calculateDimensions(
          img.width, 
          img.height, 
          settings.width, 
          settings.height, 
          settings.maintainAspectRatio
        );
        
        canvas.width = width;
        canvas.height = height;
        
        // Set background color for formats that don't support transparency
        if (!supportsTransparency(settings.format) && settings.backgroundColor) {
          ctx!.fillStyle = settings.backgroundColor;
          ctx!.fillRect(0, 0, width, height);
        }
        
        // Draw image
        ctx!.drawImage(img, 0, 0, width, height);
        
        // Convert to blob
        canvas.toBlob(
          (blob) => {
            if (blob) {
              resolve(blob);
            } else {
              reject(new Error('Failed to convert image'));
            }
          },
          getMimeType(settings.format),
          settings.quality / 100
        );
      } catch (error) {
        reject(error);
      }
    };
    
    img.onerror = () => {
      reject(new Error('Failed to load image'));
    };
    
    img.src = imageFile.preview;
  });
}

function calculateDimensions(
  originalWidth: number,
  originalHeight: number,
  targetWidth?: number,
  targetHeight?: number,
  maintainAspectRatio: boolean = true
): { width: number; height: number } {
  if (!targetWidth && !targetHeight) {
    return { width: originalWidth, height: originalHeight };
  }
  
  if (!maintainAspectRatio) {
    return {
      width: targetWidth || originalWidth,
      height: targetHeight || originalHeight
    };
  }
  
  const aspectRatio = originalWidth / originalHeight;
  
  if (targetWidth && targetHeight) {
    // Both dimensions specified - fit within bounds
    const targetAspectRatio = targetWidth / targetHeight;
    
    if (aspectRatio > targetAspectRatio) {
      // Image is wider than target ratio
      return {
        width: targetWidth,
        height: Math.round(targetWidth / aspectRatio)
      };
    } else {
      // Image is taller than target ratio
      return {
        width: Math.round(targetHeight * aspectRatio),
        height: targetHeight
      };
    }
  } else if (targetWidth) {
    // Only width specified
    return {
      width: targetWidth,
      height: Math.round(targetWidth / aspectRatio)
    };
  } else if (targetHeight) {
    // Only height specified
    return {
      width: Math.round(targetHeight * aspectRatio),
      height: targetHeight
    };
  }
  
  return { width: originalWidth, height: originalHeight };
}

function supportsTransparency(format: ImageFormat): boolean {
  const transparentFormats: ImageFormat[] = ['png', 'webp', 'avif', 'tiff', 'gif', 'ico'];
  return transparentFormats.includes(format);
}

export function generateFileName(originalName: string, format: ImageFormat): string {
  const nameWithoutExtension = originalName.replace(/\.[^/.]+$/, '');
  const extension = format === 'jpg' ? 'jpg' : format;
  return `${nameWithoutExtension}.${extension}`;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function downloadMultipleImages(images: ImageFile[], format: ImageFormat): void {
  images.forEach(image => {
    if (image.convertedBlob) {
      const filename = generateFileName(image.name, format);
      downloadBlob(image.convertedBlob, filename);
    }
  });
}

export async function createZipArchive(images: ImageFile[], format: ImageFormat): Promise<Blob> {
  // For now, we'll return a simple implementation
  // In a real app, you'd use a library like JSZip
  const files: Array<{ name: string; blob: Blob }> = [];
  
  images.forEach(image => {
    if (image.convertedBlob) {
      const filename = generateFileName(image.name, format);
      files.push({ name: filename, blob: image.convertedBlob });
    }
  });
  
  // Simple concatenation for demo - replace with proper ZIP implementation
  const combinedBlob = new Blob(files.map(f => f.blob));
  return combinedBlob;
}

export function validateImageFile(file: File): { valid: boolean; error?: string } {
  // Check file type
  if (!file.type.startsWith('image/')) {
    return { valid: false, error: 'El archivo debe ser una imagen' };
  }
  
  // Check file size (50MB limit)
  const maxSize = 50 * 1024 * 1024;
  if (file.size > maxSize) {
    return { valid: false, error: 'El archivo es demasiado grande (máximo 50MB)' };
  }
  
  // Check supported formats
  const supportedTypes = [
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
  
  if (!supportedTypes.includes(file.type)) {
    return { valid: false, error: 'Formato de imagen no soportado' };
  }
  
  return { valid: true };
}