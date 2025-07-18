'use client';

import { useEffect } from 'react';
import { InstagramPhoto } from '@/types/instagram';
import { downloadInstagramPhoto, formatInstagramNumber, formatInstagramDate } from '@/utils/instagram-scraper';

interface InstagramPhotoModalProps {
  photo: InstagramPhoto | null;
  username: string;
  onClose: () => void;
}

export default function InstagramPhotoModal({ photo, username, onClose }: InstagramPhotoModalProps) {
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

  if (!photo) return null;

  const handleDownload = async () => {
    try {
      await downloadInstagramPhoto(photo, `${username}_${photo.id}.jpg`);
    } catch (error) {
      console.error('Error downloading photo:', error);
    }
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div 
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={handleBackdropClick}
    >
      <div className="bg-white/95 dark:bg-stone-900/95 backdrop-blur-md rounded-2xl max-w-6xl max-h-[90vh] overflow-hidden shadow-2xl border border-stone-200/50 dark:border-stone-800/50">
        <div className="flex flex-col lg:flex-row max-h-[90vh]">
          {/* Imagen */}
          <div className="flex-1 flex items-center justify-center bg-stone-100 dark:bg-stone-800 relative">
            <img
              src={photo.url}
              alt={photo.caption || `Foto de ${username}`}
              className="max-w-full max-h-full object-contain"
            />
            
            {photo.isVideo && (
              <div className="absolute top-4 left-4 bg-black/70 text-white px-3 py-1 rounded-full text-sm">
                📹 Video
              </div>
            )}
            
            {/* Botón de cerrar */}
            <button
              onClick={onClose}
              className="absolute top-4 right-4 bg-black/50 hover:bg-black/70 text-white w-10 h-10 rounded-full flex items-center justify-center transition-colors duration-200"
            >
              ✕
            </button>
          </div>
          
          {/* Panel de información */}
          <div className="w-full lg:w-96 p-6 space-y-6 overflow-y-auto">
            {/* Header */}
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-gradient-to-r from-stone-400 to-stone-600 rounded-full flex items-center justify-center text-white font-bold">
                {username.charAt(0).toUpperCase()}
              </div>
              <div>
                <h3 className="font-semibold text-stone-900 dark:text-stone-100">
                  {username}
                </h3>
                {photo.timestamp && (
                  <p className="text-sm text-stone-600 dark:text-stone-400">
                    {formatInstagramDate(photo.timestamp)}
                  </p>
                )}
              </div>
            </div>
            
            {/* Estadísticas */}
            <div className="flex items-center space-x-6 text-sm">
              {photo.likes && (
                <div className="flex items-center space-x-2">
                  <span className="text-red-500">❤️</span>
                  <span className="font-medium text-stone-900 dark:text-stone-100">
                    {formatInstagramNumber(photo.likes)}
                  </span>
                  <span className="text-stone-600 dark:text-stone-400">me gusta</span>
                </div>
              )}
              
              {photo.comments && (
                <div className="flex items-center space-x-2">
                  <span className="text-blue-500">💬</span>
                  <span className="font-medium text-stone-900 dark:text-stone-100">
                    {formatInstagramNumber(photo.comments)}
                  </span>
                  <span className="text-stone-600 dark:text-stone-400">comentarios</span>
                </div>
              )}
            </div>
            
            {/* Caption */}
            {photo.caption && (
              <div>
                <h4 className="font-medium text-stone-900 dark:text-stone-100 mb-2">
                  Descripción
                </h4>
                <p className="text-stone-700 dark:text-stone-300 text-sm leading-relaxed">
                  {photo.caption}
                </p>
              </div>
            )}
            
            {/* Información técnica */}
            <div>
              <h4 className="font-medium text-stone-900 dark:text-stone-100 mb-3">
                Información técnica
              </h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-stone-600 dark:text-stone-400">Tipo:</span>
                  <span className="text-stone-900 dark:text-stone-100">
                    {photo.isVideo ? 'Video' : 'Imagen'}
                  </span>
                </div>
                
                {photo.dimensions && (
                  <div className="flex justify-between">
                    <span className="text-stone-600 dark:text-stone-400">Dimensiones:</span>
                    <span className="text-stone-900 dark:text-stone-100">
                      {photo.dimensions.width} × {photo.dimensions.height}
                    </span>
                  </div>
                )}
                
                <div className="flex justify-between">
                  <span className="text-stone-600 dark:text-stone-400">ID:</span>
                  <span className="text-stone-900 dark:text-stone-100 font-mono text-xs">
                    {photo.id}
                  </span>
                </div>
              </div>
            </div>
            
            {/* Acciones */}
            <div className="space-y-3">
              <button
                onClick={handleDownload}
                className="w-full bg-green-600 hover:bg-green-700 text-white py-3 px-4 rounded-lg font-medium transition-colors duration-200 flex items-center justify-center space-x-2"
              >
                <span>💾</span>
                <span>Descargar imagen</span>
              </button>
              
              <button
                onClick={() => window.open(photo.url, '_blank')}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white py-3 px-4 rounded-lg font-medium transition-colors duration-200 flex items-center justify-center space-x-2"
              >
                <span>🔗</span>
                <span>Abrir en nueva pestaña</span>
              </button>
              
              <button
                onClick={onClose}
                className="w-full bg-stone-600 hover:bg-stone-700 text-white py-3 px-4 rounded-lg font-medium transition-colors duration-200"
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