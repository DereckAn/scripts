'use client';

import { useCallback, useState } from 'react';
import { ImageFile } from '@/types/image-converter';
import { createImageFile, validateImageFile } from '@/utils/image-converter';

interface ImageUploaderProps {
  onImagesAdded: (images: ImageFile[]) => void;
  maxFiles?: number;
}

export default function ImageUploader({ onImagesAdded, maxFiles = 20 }: ImageUploaderProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const handleFiles = useCallback((files: FileList | File[]) => {
    const fileArray = Array.from(files);
    const newImages: ImageFile[] = [];
    const newErrors: string[] = [];

    fileArray.forEach(file => {
      const validation = validateImageFile(file);
      if (validation.valid) {
        newImages.push(createImageFile(file));
      } else {
        newErrors.push(`${file.name}: ${validation.error}`);
      }
    });

    if (newErrors.length > 0) {
      setErrors(newErrors);
      setTimeout(() => setErrors([]), 5000); // Clear errors after 5 seconds
    }

    if (newImages.length > 0) {
      onImagesAdded(newImages);
    }
  }, [onImagesAdded]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFiles(files);
    }
  }, [handleFiles]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFiles(files);
    }
    // Reset input value to allow selecting the same file again
    e.target.value = '';
  }, [handleFiles]);

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        className={`border-2 border-dashed rounded-xl p-12 text-center transition-all duration-300 ${
          isDragOver
            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
            : 'border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500'
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <div className="space-y-4">
          <div className="text-6xl">
            {isDragOver ? '📤' : '📁'}
          </div>
          <div>
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              {isDragOver ? '¡Suelta las imágenes aquí!' : 'Arrastra y suelta tus imágenes'}
            </h3>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              O haz clic para seleccionar archivos
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-500 mb-4">
              Soporta: JPEG, PNG, WebP, AVIF, BMP, TIFF, GIF, SVG (máximo {maxFiles} archivos, 50MB cada uno)
            </p>
          </div>
          
          <label className="inline-block">
            <input
              type="file"
              multiple
              accept="image/*"
              onChange={handleFileInput}
              className="hidden"
            />
            <span className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium transition-colors duration-200 cursor-pointer inline-block">
              Seleccionar Archivos
            </span>
          </label>
        </div>
      </div>

      {/* Error Messages */}
      {errors.length > 0 && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-red-900 dark:text-red-100 mb-2">
            ⚠️ Errores en algunos archivos:
          </h4>
          <ul className="text-sm text-red-800 dark:text-red-200 space-y-1">
            {errors.map((error, index) => (
              <li key={index}>• {error}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}