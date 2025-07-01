'use client';

import { useState } from 'react';
import { ScrapedPage } from '@/types/web-scraper';
import { downloadMarkdown, addFrontmatter } from '@/utils/web-scraper';

interface ContentPreviewModalProps {
  page: ScrapedPage | null;
  onClose: () => void;
}

export default function ContentPreviewModal({ page, onClose }: ContentPreviewModalProps) {
  const [activeTab, setActiveTab] = useState<'content' | 'metadata' | 'raw'>('content');
  const [showFrontmatter, setShowFrontmatter] = useState(true);

  if (!page) return null;

  const handleDownload = () => {
    const content = showFrontmatter 
      ? addFrontmatter(page.content, page.metadata)
      : page.content;
    downloadMarkdown(content, page.filename);
  };

  const handleCopyToClipboard = async () => {
    const content = showFrontmatter 
      ? addFrontmatter(page.content, page.metadata)
      : page.content;
    
    try {
      await navigator.clipboard.writeText(content);
      // Aquí podrías añadir una notificación
    } catch (err) {
      console.error('Error copying to clipboard:', err);
    }
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'content':
        const displayContent = showFrontmatter 
          ? addFrontmatter(page.content, page.metadata)
          : page.content;
        
        return (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={showFrontmatter}
                  onChange={(e) => setShowFrontmatter(e.target.checked)}
                  className="text-blue-600 rounded focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  Incluir frontmatter
                </span>
              </label>
            </div>
            
            <div className="bg-gray-900 rounded-lg p-4 overflow-auto max-h-96">
              <pre className="text-sm text-green-400 font-mono whitespace-pre-wrap">
                {displayContent}
              </pre>
            </div>
          </div>
        );

      case 'metadata':
        return (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Título
                </label>
                <p className="text-sm text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-800 p-2 rounded">
                  {page.metadata.title || 'Sin título'}
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  URL
                </label>
                <p className="text-sm text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-800 p-2 rounded break-all">
                  {page.metadata.url}
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Autor
                </label>
                <p className="text-sm text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-800 p-2 rounded">
                  {page.metadata.author || 'No especificado'}
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Fecha de scraping
                </label>
                <p className="text-sm text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-800 p-2 rounded">
                  {new Date(page.metadata.scrapedAt).toLocaleString()}
                </p>
              </div>
            </div>

            {page.metadata.description && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Descripción
                </label>
                <p className="text-sm text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-800 p-3 rounded">
                  {page.metadata.description}
                </p>
              </div>
            )}

            {page.metadata.keywords.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Palabras clave
                </label>
                <div className="flex flex-wrap gap-2">
                  {page.metadata.keywords.map((keyword, index) => (
                    <span
                      key={index}
                      className="bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 text-sm px-3 py-1 rounded-full"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Información de idioma */}
            {page.metadata.language && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Idioma detectado
                </label>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 text-sm px-3 py-1 rounded-full">
                      {page.metadata.language.toUpperCase()}
                    </span>
                    <span className="text-sm text-gray-600 dark:text-gray-400">Idioma principal</span>
                  </div>
                  
                  {page.metadata.alternativeLanguages && page.metadata.alternativeLanguages.length > 0 && (
                    <div>
                      <span className="text-sm text-gray-600 dark:text-gray-400 mb-2 block">
                        Idiomas alternativos disponibles:
                      </span>
                      <div className="flex flex-wrap gap-2">
                        {page.metadata.alternativeLanguages.map((lang, index) => (
                          <span
                            key={index}
                            className="bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 text-xs px-2 py-1 rounded"
                            title={lang.url}
                          >
                            {lang.name} ({lang.code})
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Enlaces encontrados
                </label>
                <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                  {page.links.length}
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Imágenes encontradas
                </label>
                <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                  {page.images.length}
                </p>
              </div>
            </div>
          </div>
        );

      case 'raw':
        return (
          <div className="bg-gray-900 rounded-lg p-4 overflow-auto max-h-96">
            <pre className="text-sm text-gray-300 font-mono whitespace-pre-wrap">
              {JSON.stringify(page, null, 2)}
            </pre>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                Vista Previa del Contenido
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-400 break-all mt-1">
                {page.url}
              </p>
            </div>
            
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 text-2xl"
            >
              ✕
            </button>
          </div>

          {/* Tabs */}
          <div className="flex space-x-1 mt-4">
            {[
              { id: 'content', label: 'Contenido', icon: '📄' },
              { id: 'metadata', label: 'Metadatos', icon: '🏷️' },
              { id: 'raw', label: 'Raw JSON', icon: '🔧' }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-4 py-2 rounded-lg font-medium transition-colors duration-200 ${
                  activeTab === tab.id
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                }`}
              >
                <span className="mr-2">{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 p-6 overflow-auto">
          {renderContent()}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200 dark:border-gray-700">
          <div className="flex justify-between items-center">
            <div className="text-sm text-gray-600 dark:text-gray-400">
              <span className="font-medium">{page.filename}</span>
              <span className="mx-2">•</span>
              <span>{(page.content.length / 1024).toFixed(1)} KB</span>
            </div>
            
            <div className="flex space-x-3">
              <button
                onClick={handleCopyToClipboard}
                className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center space-x-2"
              >
                <span>📋</span>
                <span>Copiar</span>
              </button>
              
              <button
                onClick={handleDownload}
                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center space-x-2"
              >
                <span>💾</span>
                <span>Descargar</span>
              </button>
              
              <button
                onClick={onClose}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors duration-200"
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}