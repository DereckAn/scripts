'use client';

import { useCallback, useState } from 'react';
import { FileMusic, Loader2, Upload } from 'lucide-react';
import { SvgFile } from '@/types/svg-to-pdf';
import { createSvgFile, validateSvgFile } from '@/utils/svg-to-pdf';

interface SvgUploaderProps {
  onFilesAdded: (files: SvgFile[]) => void;
  maxFiles?: number;
}

export default function SvgUploader({ onFilesAdded, maxFiles = 100 }: SvgUploaderProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [isReading, setIsReading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const handleFiles = useCallback(
    async (fileList: FileList | File[]) => {
      const incoming = Array.from(fileList).slice(0, maxFiles);
      const newErrors: string[] = [];
      const accepted: File[] = [];

      incoming.forEach((file) => {
        const validation = validateSvgFile(file);
        if (validation.valid) {
          accepted.push(file);
        } else {
          newErrors.push(`${file.name}: ${validation.error}`);
        }
      });

      if (accepted.length > 0) {
        setIsReading(true);
        try {
          const svgFiles = await Promise.all(
            accepted.map(async (file) => {
              try {
                return await createSvgFile(file);
              } catch {
                newErrors.push(`${file.name}: no se pudo leer el archivo`);
                return null;
              }
            })
          );
          const valid = svgFiles.filter((svgFile): svgFile is SvgFile => svgFile !== null);
          if (valid.length > 0) {
            onFilesAdded(valid);
          }
        } finally {
          setIsReading(false);
        }
      }

      if (newErrors.length > 0) {
        setErrors(newErrors);
        setTimeout(() => setErrors([]), 6000);
      }
    },
    [maxFiles, onFilesAdded]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        void handleFiles(e.dataTransfer.files);
      }
    },
    [handleFiles]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        void handleFiles(files);
      }
      // Reset input value to allow selecting the same file again
      e.target.value = '';
    },
    [handleFiles]
  );

  return (
    <div className="space-y-4">
      <div
        className={`border-2 border-dashed rounded-xl p-12 text-center transition-all duration-300 ${
          isDragOver
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
            : 'border-stone-300 dark:border-stone-600 hover:border-stone-400 dark:hover:border-stone-500'
        }`}
        onDrop={handleDrop}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsDragOver(false);
        }}
      >
        <div className="space-y-4">
          <div className="flex justify-center">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-indigo-100 dark:bg-indigo-950/40">
              {isReading ? (
                <Loader2 className="w-8 h-8 text-indigo-600 dark:text-indigo-400 animate-spin" />
              ) : isDragOver ? (
                <Upload className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />
              ) : (
                <FileMusic className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />
              )}
            </div>
          </div>

          <div>
            <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 mb-2">
              {isReading
                ? 'Leyendo partituras…'
                : isDragOver
                ? '¡Suelta las partituras aquí!'
                : 'Arrastra y suelta tus SVG'}
            </h3>
            <p className="text-stone-600 dark:text-stone-400 mb-4">
              O haz clic para seleccionar archivos
            </p>
            <p className="text-sm text-stone-500 dark:text-stone-500">
              Solo archivos SVG (máximo {maxFiles} archivos, 25MB cada uno). Se ordenan
              automáticamente por nombre.
            </p>
          </div>

          <label className="inline-block">
            <input
              type="file"
              multiple
              accept=".svg,image/svg+xml"
              onChange={handleFileInput}
              className="hidden"
            />
            <span className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-lg font-medium transition-colors duration-200 cursor-pointer inline-block">
              Seleccionar Archivos
            </span>
          </label>
        </div>
      </div>

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
