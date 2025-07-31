'use client';

import { useEffect } from 'react';
import { TwitterPhoto } from '@/types/twitter';
import { downloadTwitterPhoto, formatTwitterNumber, formatTwitterDate } from '@/utils/twitter-api';

interface TwitterPhotoModalProps {
  photo: TwitterPhoto | null;
  username: string;
  onClose: () => void;
}

export default function TwitterPhotoModal({ photo, username, onClose }: TwitterPhotoModalProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    if (photo) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [photo, onClose]);

  const handleDownload = async () => {
    if (!photo) return;
    
    try {
      await downloadTwitterPhoto(photo, `${username}_${photo.id}.jpg`);
    } catch (error) {
      console.error('Error downloading photo:', error);
    }
  };

  const handleViewTweet = () => {
    if (!photo) return;
    window.open(`https://twitter.com/${username}/status/${photo.tweetId}`, '_blank');
  };

  if (!photo) return null;

  return (
    <div 
      className="fixed inset-0 bg-black/90 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div 
        className="relative max-w-4xl max-h-[90vh] w-full bg-white dark:bg-stone-900 rounded-xl overflow-hidden shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 bg-stone-50 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700">
          <div className="flex items-center space-x-3">
            <span className="text-xl">🐦</span>
            <div>
              <h3 className="font-semibold text-stone-900 dark:text-stone-100">
                Imagen de @{username}
              </h3>
              <p className="text-sm text-stone-600 dark:text-stone-400">
                {formatTwitterDate(photo.publishedAt)}
              </p>
            </div>
          </div>
          
          <div className="flex items-center space-x-2">
            <button
              onClick={handleViewTweet}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 flex items-center space-x-2"
            >
              <span>🔗</span>
              <span>Ver Tweet</span>
            </button>
            
            <button
              onClick={handleDownload}
              className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 flex items-center space-x-2"
            >
              <span>💾</span>
              <span>Descargar</span>
            </button>
            
            <button
              onClick={onClose}
              className="bg-stone-600 hover:bg-stone-700 text-white p-2 rounded-lg transition-colors duration-200"
            >
              <span className="text-lg">✕</span>
            </button>
          </div>
        </div>

        {/* Contenido */}
        <div className="flex flex-col lg:flex-row max-h-[calc(90vh-80px)]">
          {/* Imagen */}
          <div className="flex-1 flex items-center justify-center bg-black p-4">
            {photo.isVideo ? (
              <div className="text-center text-white">
                <div className="text-6xl mb-4">▶️</div>
                <p className="text-lg mb-4">Este es un video</p>
                {photo.videoUrl && (
                  <video
                    src={photo.videoUrl}
                    controls
                    className="max-w-full max-h-full rounded-lg"
                    poster={photo.thumbnailUrl}
                  />
                )}
              </div>
            ) : (
              <img
                src={photo.highResUrl || photo.url}
                alt={photo.caption || `Imagen de ${username}`}
                className="max-w-full max-h-full object-contain rounded-lg"
              />
            )}
          </div>

          {/* Panel lateral con información */}
          <div className="lg:w-80 bg-stone-50 dark:bg-stone-800 p-6 overflow-y-auto">
            <div className="space-y-6">
              {/* Estadísticas */}
              <div>
                <h4 className="font-semibold text-stone-900 dark:text-stone-100 mb-3">
                  📊 Estadísticas
                </h4>
                <div className="space-y-2">
                  {photo.likes && (
                    <div className="flex items-center justify-between">
                      <span className="text-stone-600 dark:text-stone-400">❤️ Me gusta</span>
                      <span className="font-medium text-stone-900 dark:text-stone-100">
                        {formatTwitterNumber(photo.likes)}
                      </span>
                    </div>
                  )}
                  
                  {photo.retweets && (
                    <div className="flex items-center justify-between">
                      <span className="text-stone-600 dark:text-stone-400">🔄 Retweets</span>
                      <span className="font-medium text-stone-900 dark:text-stone-100">
                        {formatTwitterNumber(photo.retweets)}
                      </span>
                    </div>
                  )}
                  
                  {photo.comments && (
                    <div className="flex items-center justify-between">
                      <span className="text-stone-600 dark:text-stone-400">💬 Comentarios</span>
                      <span className="font-medium text-stone-900 dark:text-stone-100">
                        {formatTwitterNumber(photo.comments)}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Descripción/Caption */}
              {photo.caption && (
                <div>
                  <h4 className="font-semibold text-stone-900 dark:text-stone-100 mb-3">
                    📝 Descripción
                  </h4>
                  <p className="text-stone-700 dark:text-stone-300 leading-relaxed">
                    {photo.caption}
                  </p>
                </div>
              )}

              {/* Información técnica */}
              <div>
                <h4 className="font-semibold text-stone-900 dark:text-stone-100 mb-3">
                  🔧 Información
                </h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-stone-600 dark:text-stone-400">Tipo</span>
                    <span className="text-stone-900 dark:text-stone-100">
                      {photo.isVideo ? 'Video' : 'Imagen'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-stone-600 dark:text-stone-400">Dimensiones</span>
                    <span className="text-stone-900 dark:text-stone-100">
                      {photo.width} × {photo.height}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-stone-600 dark:text-stone-400">ID del Tweet</span>
                    <span className="text-stone-900 dark:text-stone-100 font-mono text-xs">
                      {photo.tweetId}
                    </span>
                  </div>
                </div>
              </div>

              {/* Acciones adicionales */}
              <div className="pt-4 border-t border-stone-200 dark:border-stone-700">
                <button
                  onClick={handleViewTweet}
                  className="w-full bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-lg font-medium transition-colors duration-200 flex items-center justify-center space-x-2"
                >
                  <span>🐦</span>
                  <span>Ver Tweet original</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Indicador de ESC para cerrar */}
        <div className="absolute bottom-4 left-4 bg-black/50 text-white px-3 py-1 rounded text-sm">
          Presiona ESC para cerrar
        </div>
      </div>
    </div>
  );
}