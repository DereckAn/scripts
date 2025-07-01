'use client';

import { useState, useCallback } from 'react';
import { ImageFile, ConversionSettings, ConversionProgress } from '@/types/image-converter';
import { convertImage, downloadBlob, downloadMultipleImages, generateFileName } from '@/utils/image-converter';
import ImageUploader from '@/components/ImageUploader';
import ImagePreview from '@/components/ImagePreview';
import ConversionSettingsComponent from '@/components/ConversionSettings';

export default function ConvertImagesPage() {
  const [images, setImages] = useState<ImageFile[]>([]);
  const [settings, setSettings] = useState<ConversionSettings>({
    format: 'jpg',
    quality: 80,
    maintainAspectRatio: true,
    removeMetadata: false,
    backgroundColor: '#ffffff'
  });
  const [isConverting, setIsConverting] = useState(false);
  const [progress, setProgress] = useState<ConversionProgress | null>(null);

  const handleImagesAdded = useCallback((newImages: ImageFile[]) => {
    setImages(prev => [...prev, ...newImages]);
  }, []);

  const handleRemoveImage = useCallback((id: string) => {
    setImages(prev => {
      const imageToRemove = prev.find(img => img.id === id);
      if (imageToRemove) {
        // Cleanup blob URLs
        URL.revokeObjectURL(imageToRemove.preview);
        if (imageToRemove.convertedUrl) {
          URL.revokeObjectURL(imageToRemove.convertedUrl);
        }
      }
      return prev.filter(img => img.id !== id);
    });
  }, []);

  const handleDownloadSingle = useCallback((id: string) => {
    const image = images.find(img => img.id === id);
    if (image && image.convertedBlob) {
      const filename = generateFileName(image.name, settings.format);
      downloadBlob(image.convertedBlob, filename);
    }
  }, [images, settings.format]);

  const handleDownloadAll = useCallback(() => {
    const completedImages = images.filter(img => img.status === 'completed');
    if (completedImages.length > 0) {
      downloadMultipleImages(completedImages, settings.format);
    }
  }, [images, settings.format]);

  const handleClearAll = useCallback(() => {
    // Cleanup all blob URLs
    images.forEach(image => {
      URL.revokeObjectURL(image.preview);
      if (image.convertedUrl) {
        URL.revokeObjectURL(image.convertedUrl);
      }
    });
    setImages([]);
  }, [images]);

  const handleConvertAll = useCallback(async () => {
    if (images.length === 0 || isConverting) return;

    setIsConverting(true);
    setProgress({
      current: 0,
      total: images.length,
      percentage: 0,
      currentFile: ''
    });

    const updatedImages = [...images];

    for (let i = 0; i < updatedImages.length; i++) {
      const image = updatedImages[i];
      
      // Update progress
      setProgress({
        current: i,
        total: images.length,
        percentage: Math.round((i / images.length) * 100),
        currentFile: image.name
      });

      // Update image status to converting
      setImages(prev => prev.map(img => 
        img.id === image.id 
          ? { ...img, status: 'converting' }
          : img
      ));

      try {
        // Convert image
        const convertedBlob = await convertImage(image, settings);
        const convertedUrl = URL.createObjectURL(convertedBlob);

        // Update image with converted result
        setImages(prev => prev.map(img => 
          img.id === image.id 
            ? { 
                ...img, 
                status: 'completed', 
                convertedBlob, 
                convertedUrl 
              }
            : img
        ));

        updatedImages[i] = {
          ...image,
          status: 'completed',
          convertedBlob,
          convertedUrl
        };

      } catch (error) {
        // Update image with error
        const errorMessage = error instanceof Error ? error.message : 'Error desconocido';
        setImages(prev => prev.map(img => 
          img.id === image.id 
            ? { 
                ...img, 
                status: 'error', 
                error: errorMessage 
              }
            : img
        ));

        updatedImages[i] = {
          ...image,
          status: 'error',
          error: errorMessage
        };
      }

      // Small delay to prevent UI blocking
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    // Final progress update
    setProgress({
      current: images.length,
      total: images.length,
      percentage: 100,
      currentFile: 'Completado'
    });

    setIsConverting(false);
    
    // Clear progress after a delay
    setTimeout(() => setProgress(null), 2000);
  }, [images, settings, isConverting]);

  const completedImages = images.filter(img => img.status === 'completed');
  const errorImages = images.filter(img => img.status === 'error');
  const pendingImages = images.filter(img => img.status === 'pending');

  return (
    <div className="min-h-screen p-8 pt-20">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
            🖼️ Convertidor de Imágenes
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-400">
            Convierte tus imágenes a diferentes formatos de manera rápida y sencilla
          </p>
        </div>

        <div className="space-y-8">
          {/* Image Uploader */}
          <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-8 border border-gray-200 dark:border-gray-700">
            <ImageUploader onImagesAdded={handleImagesAdded} maxFiles={50} />
          </div>

          {/* Conversion Settings */}
          {images.length > 0 && (
            <ConversionSettingsComponent
              settings={settings}
              onChange={setSettings}
              totalImages={images.length}
            />
          )}

          {/* Progress Bar */}
          {progress && (
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-6 border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  🔄 Convirtiendo imágenes...
                </h3>
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  {progress.current} de {progress.total} ({progress.percentage}%)
                </span>
              </div>
              
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3 mb-2">
                <div 
                  className="bg-blue-600 h-3 rounded-full transition-all duration-300"
                  style={{ width: `${progress.percentage}%` }}
                ></div>
              </div>
              
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {progress.currentFile}
              </p>
            </div>
          )}

          {/* Action Buttons */}
          {images.length > 0 && (
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-6 border border-gray-200 dark:border-gray-700">
              <div className="flex flex-wrap gap-4 items-center justify-between">
                <div className="flex flex-wrap gap-4">
                  <button
                    onClick={handleConvertAll}
                    disabled={isConverting || pendingImages.length === 0}
                    className="bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white px-6 py-3 rounded-lg font-semibold transition-colors duration-200 flex items-center space-x-2"
                  >
                    <span>🎯</span>
                    <span>
                      {isConverting ? 'Convirtiendo...' : `Convertir ${pendingImages.length} imagen${pendingImages.length === 1 ? '' : 'es'}`}
                    </span>
                  </button>

                  {completedImages.length > 0 && (
                    <button
                      onClick={handleDownloadAll}
                      className="bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg font-semibold transition-colors duration-200 flex items-center space-x-2"
                    >
                      <span>💾</span>
                      <span>Descargar todas ({completedImages.length})</span>
                    </button>
                  )}

                  <button
                    onClick={handleClearAll}
                    disabled={isConverting}
                    className="bg-red-600 hover:bg-red-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white px-6 py-3 rounded-lg font-semibold transition-colors duration-200 flex items-center space-x-2"
                  >
                    <span>🗑️</span>
                    <span>Limpiar todo</span>
                  </button>
                </div>

                <div className="text-sm text-gray-600 dark:text-gray-400">
                  Total: {images.length} | Completadas: {completedImages.length} | Errores: {errorImages.length}
                </div>
              </div>
            </div>
          )}

          {/* Images Grid */}
          {images.length > 0 && (
            <div className="space-y-6">
              <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">
                📁 Imágenes ({images.length})
              </h2>
              
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {images.map(image => (
                  <ImagePreview
                    key={image.id}
                    image={image}
                    outputFormat={settings.format}
                    onRemove={handleRemoveImage}
                    onDownload={handleDownloadSingle}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Empty State */}
          {images.length === 0 && (
            <div className="text-center py-12">
              <div className="text-6xl mb-4">📸</div>
              <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                ¡Comienza subiendo algunas imágenes!
              </h3>
              <p className="text-gray-600 dark:text-gray-400">
                Arrastra y suelta archivos o haz clic en el botón de arriba para seleccionar imágenes
              </p>
            </div>
          )}

          {/* Help Section */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-2xl p-6 border border-blue-200 dark:border-blue-800">
            <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-100 mb-4">
              💡 Consejos y formatos soportados
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm text-blue-800 dark:text-blue-200">
              <div>
                <h4 className="font-semibold mb-2">Formatos de entrada:</h4>
                <ul className="space-y-1">
                  <li>• JPEG/JPG - Fotografías</li>
                  <li>• PNG - Gráficos con transparencia</li>
                  <li>• WebP - Formato moderno de Google</li>
                  <li>• AVIF - Formato de nueva generación</li>
                  <li>• BMP, TIFF, GIF, SVG</li>
                </ul>
              </div>
              
              <div>
                <h4 className="font-semibold mb-2">Consejos de uso:</h4>
                <ul className="space-y-1">
                  <li>• Usa JPEG para fotografías (menor tamaño)</li>
                  <li>• Usa PNG para gráficos con transparencia</li>
                  <li>• WebP ofrece la mejor relación calidad/tamaño</li>
                  <li>• Ajusta la calidad según tus necesidades</li>
                  <li>• Máximo 50MB por archivo</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}