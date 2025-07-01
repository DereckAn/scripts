'use client';

import { ScrapedPage } from '@/types/web-scraper';
import { formatFileSize, downloadMarkdown } from '@/utils/web-scraper';

interface ScrapedPageCardProps {
  page: ScrapedPage;
  onPreview: (page: ScrapedPage) => void;
  onDownload: (page: ScrapedPage) => void;
  onRemove?: (page: ScrapedPage) => void;
}

export default function ScrapedPageCard({ 
  page, 
  onPreview, 
  onDownload, 
  onRemove 
}: ScrapedPageCardProps) {
  const getStatusIcon = () => {
    switch (page.status) {
      case 'pending':
        return '⏳';
      case 'processing':
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
    switch (page.status) {
      case 'pending':
        return 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20';
      case 'processing':
        return 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20';
      case 'completed':
        return 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20';
      case 'error':
        return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20';
      default:
        return 'text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-800';
    }
  };

  const getStatusText = () => {
    switch (page.status) {
      case 'pending':
        return 'Pendiente';
      case 'processing':
        return 'Procesando...';
      case 'completed':
        return 'Completado';
      case 'error':
        return 'Error';
      default:
        return 'Desconocido';
    }
  };

  const handleQuickDownload = () => {
    if (page.status === 'completed') {
      downloadMarkdown(page.content, page.filename);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      {/* Header con URL y estado */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h3 className="font-medium text-gray-900 dark:text-white truncate" title={page.title}>
              {page.title || 'Sin título'}
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 break-all mt-1">
              {page.url}
            </p>
          </div>
          
          <div className={`ml-4 px-3 py-1 rounded-full text-xs font-medium ${getStatusColor()}`}>
            <span className="mr-1">{getStatusIcon()}</span>
            {getStatusText()}
          </div>
        </div>
      </div>

      {/* Información del contenido */}
      <div className="p-4">
        {page.status === 'completed' && (
          <div className="space-y-3">
            {/* Metadata */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-600 dark:text-gray-400">Archivo:</span>
                <p className="font-medium text-gray-900 dark:text-white">{page.filename}</p>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400">Tamaño:</span>
                <p className="font-medium text-gray-900 dark:text-white">{formatFileSize(page.size)}</p>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400">Enlaces:</span>
                <p className="font-medium text-gray-900 dark:text-white">{page.links.length}</p>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400">Imágenes:</span>
                <p className="font-medium text-gray-900 dark:text-white">{page.images.length}</p>
              </div>
            </div>

            {/* Información de idioma */}
            {page.metadata.language && (
              <div>
                <span className="text-sm text-gray-600 dark:text-gray-400">Idioma:</span>
                <div className="flex items-center gap-2 mt-1">
                  <span className="bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 text-xs px-2 py-1 rounded">
                    {page.metadata.language.toUpperCase()}
                  </span>
                  {page.metadata.alternativeLanguages && page.metadata.alternativeLanguages.length > 0 && (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      +{page.metadata.alternativeLanguages.length} idiomas disponibles
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Metadatos adicionales */}
            {page.metadata.description && (
              <div>
                <span className="text-sm text-gray-600 dark:text-gray-400">Descripción:</span>
                <p className="text-sm text-gray-900 dark:text-white mt-1 line-clamp-2">
                  {page.metadata.description}
                </p>
              </div>
            )}

            {/* Keywords */}
            {page.metadata.keywords.length > 0 && (
              <div>
                <span className="text-sm text-gray-600 dark:text-gray-400">Palabras clave:</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {page.metadata.keywords.slice(0, 5).map((keyword, index) => (
                    <span
                      key={index}
                      className="bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 text-xs px-2 py-1 rounded"
                    >
                      {keyword}
                    </span>
                  ))}
                  {page.metadata.keywords.length > 5 && (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      +{page.metadata.keywords.length - 5} más
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Vista previa del contenido */}
            <div>
              <span className="text-sm text-gray-600 dark:text-gray-400">Vista previa:</span>
              <div className="bg-gray-50 dark:bg-gray-800 rounded p-3 mt-1">
                <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-3">
                  {page.content.replace(/[#*`\-\[\]]/g, '').substring(0, 200)}...
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Error information */}
        {page.status === 'error' && page.error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-3">
            <p className="text-sm text-red-800 dark:text-red-200">
              <strong>Error:</strong> {page.error}
            </p>
          </div>
        )}

        {/* Processing animation */}
        {page.status === 'processing' && (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full"></div>
            <span className="ml-3 text-sm text-gray-600 dark:text-gray-400">
              Procesando contenido...
            </span>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 mt-4">
          {page.status === 'completed' && (
            <>
              <button
                onClick={() => onPreview(page)}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 px-3 rounded-lg text-sm font-medium transition-colors duration-200 flex items-center justify-center space-x-1"
              >
                <span>👁️</span>
                <span>Vista previa</span>
              </button>
              
              <button
                onClick={handleQuickDownload}
                className="bg-green-600 hover:bg-green-700 text-white py-2 px-3 rounded-lg text-sm font-medium transition-colors duration-200"
                title="Descarga rápida"
              >
                💾
              </button>
            </>
          )}

          {onRemove && (
            <button
              onClick={() => onRemove(page)}
              className="bg-red-600 hover:bg-red-700 text-white py-2 px-3 rounded-lg text-sm font-medium transition-colors duration-200"
              title="Eliminar"
            >
              🗑️
            </button>
          )}
        </div>

        {/* Processing time */}
        {page.processingTime && page.status === 'completed' && (
          <div className="mt-2 text-xs text-gray-500 dark:text-gray-400 text-center">
            Procesado en {page.processingTime.toFixed(2)}s
          </div>
        )}
      </div>
    </div>
  );
}