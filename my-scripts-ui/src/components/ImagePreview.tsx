'use client';

import { ImageFile, ImageFormat } from '@/types/image-converter';
import { formatFileSize, generateFileName } from '@/utils/image-converter';

interface ImagePreviewProps {
  image: ImageFile;
  outputFormat: ImageFormat;
  onRemove: (id: string) => void;
  onDownload?: (id: string) => void;
}

export default function ImagePreview({ image, outputFormat, onRemove, onDownload }: ImagePreviewProps) {
  const getStatusIcon = () => {
    switch (image.status) {
      case 'pending':
        return '⏳';
      case 'converting':
        return '🔄';
      case 'completed':
        return '✅';
      case 'error':
        return '❌';
      default:
        return '📄';
    }
  };

  const getStatusColor = () => {
    switch (image.status) {
      case 'pending':
        return 'text-yellow-600 dark:text-yellow-400';
      case 'converting':
        return 'text-blue-600 dark:text-blue-400';
      case 'completed':
        return 'text-green-600 dark:text-green-400';
      case 'error':
        return 'text-red-600 dark:text-red-400';
      default:
        return 'text-stone-600 dark:text-stone-400';
    }
  };

  const getStatusText = () => {
    switch (image.status) {
      case 'pending':
        return 'Pendiente';
      case 'converting':
        return 'Convirtiendo...';
      case 'completed':
        return 'Completado';
      case 'error':
        return 'Error';
      default:
        return 'Desconocido';
    }
  };

  const outputFileName = generateFileName(image.name, outputFormat);
  const outputSize = image.convertedBlob ? formatFileSize(image.convertedBlob.size) : '-';

  return (
    <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-xl border border-stone-200/60 dark:border-stone-800/60 overflow-hidden shadow-lg hover:shadow-xl transition-all duration-300 hover:-translate-y-1">
      {/* Image Preview */}
      <div className="aspect-video bg-stone-100 dark:bg-stone-800 relative overflow-hidden">
        <img
          src={image.preview}
          alt={image.name}
          className="w-full h-full object-cover"
        />
        
        {/* Status Overlay */}
        <div className="absolute top-2 right-2 bg-black/50 text-white px-2 py-1 rounded text-sm">
          <span className={getStatusColor()}>{getStatusIcon()}</span>
        </div>

        {/* Remove Button */}
        <button
          onClick={() => onRemove(image.id)}
          className="absolute top-2 left-2 bg-red-600 hover:bg-red-700 text-white w-8 h-8 rounded-full flex items-center justify-center transition-colors duration-200"
          title="Eliminar imagen"
        >
          ✕
        </button>

        {/* Converting Animation */}
        {image.status === 'converting' && (
          <div className="absolute inset-0 bg-black/30 flex items-center justify-center">
            <div className="bg-white/90 dark:bg-stone-800/90 backdrop-blur-sm rounded-lg px-4 py-2 flex items-center space-x-2">
              <div className="animate-spin w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full"></div>
              <span className="text-sm font-medium text-stone-900 dark:text-stone-100">Convirtiendo...</span>
            </div>
          </div>
        )}
      </div>

      {/* Image Info */}
      <div className="p-4 space-y-3">
        {/* File Name */}
        <div>
          <h3 className="font-medium text-stone-900 dark:text-stone-100 truncate" title={image.name}>
            {image.name}
          </h3>
          <p className="text-sm text-stone-600 dark:text-stone-400">
            {formatFileSize(image.size)} • {image.originalFormat.toUpperCase()}
          </p>
        </div>

        {/* Conversion Arrow */}
        <div className="flex items-center justify-center">
          <div className="text-2xl text-stone-400 dark:text-stone-500">
            ↓
          </div>
        </div>

        {/* Output Info */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-stone-700 dark:text-stone-300">
              {outputFileName}
            </span>
            <span className={`text-sm font-medium ${getStatusColor()}`}>
              {getStatusIcon()} {getStatusText()}
            </span>
          </div>
          
          <div className="flex items-center justify-between text-sm text-stone-600 dark:text-stone-400">
            <span>{outputSize}</span>
            <span>{outputFormat.toUpperCase()}</span>
          </div>

          {/* Error Message */}
          {image.status === 'error' && image.error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-2">
              <p className="text-sm text-red-800 dark:text-red-200">{image.error}</p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex space-x-2 pt-2">
          {image.status === 'completed' && onDownload && (
            <button
              onClick={() => onDownload(image.id)}
              className="flex-1 bg-green-600 hover:bg-green-700 text-white py-2 px-3 rounded-lg text-sm font-medium transition-colors duration-200 flex items-center justify-center space-x-1"
            >
              <span>💾</span>
              <span>Descargar</span>
            </button>
          )}
          
          {image.status === 'completed' && image.convertedUrl && (
            <button
              onClick={() => window.open(image.convertedUrl, '_blank')}
              className="bg-blue-600 hover:bg-blue-700 text-white py-2 px-3 rounded-lg text-sm font-medium transition-colors duration-200"
              title="Ver imagen convertida"
            >
              👁️
            </button>
          )}
        </div>
      </div>
    </div>
  );
}