'use client';

import { useState } from 'react';
import { TwitterPhoto } from '@/types/twitter';
import { downloadTwitterPhoto, formatTwitterNumber, formatTwitterDate } from '@/utils/twitter-api';
import TwitterPhotoModal from './TwitterPhotoModal';

interface TwitterPhotoGridProps {
  photos: TwitterPhoto[];
  username: string;
  onDownloadAll?: () => void;
}

export default function TwitterPhotoGrid({ photos, username, onDownloadAll }: TwitterPhotoGridProps) {
  const [selectedPhoto, setSelectedPhoto] = useState<TwitterPhoto | null>(null);
  const [selectedPhotos, setSelectedPhotos] = useState<Set<string>>(new Set());
  const [isSelectionMode, setIsSelectionMode] = useState(false);

  const handlePhotoClick = (photo: TwitterPhoto) => {
    if (isSelectionMode) {
      togglePhotoSelection(photo.id);
    } else {
      setSelectedPhoto(photo);
    }
  };

  const togglePhotoSelection = (photoId: string) => {
    const newSelection = new Set(selectedPhotos);
    if (newSelection.has(photoId)) {
      newSelection.delete(photoId);
    } else {
      newSelection.add(photoId);
    }
    setSelectedPhotos(newSelection);
  };

  const handleSelectAll = () => {
    if (selectedPhotos.size === photos.length) {
      setSelectedPhotos(new Set());
    } else {
      setSelectedPhotos(new Set(photos.map(p => p.id)));
    }
  };

  const handleDownloadSelected = async () => {
    try {
      const selectedPhotoObjects = photos.filter(p => selectedPhotos.has(p.id));
      for (let i = 0; i < selectedPhotoObjects.length; i++) {
        const photo = selectedPhotoObjects[i];
        await downloadTwitterPhoto(photo, `${username}_${photo.id}.jpg`);
        
        // Delay para evitar problemas con el navegador
        if (i < selectedPhotoObjects.length - 1) {
          await new Promise(resolve => setTimeout(resolve, 600));
        }
      }
    } catch (error) {
      console.error('Error downloading selected photos:', error);
    }
  };

  const toggleSelectionMode = () => {
    setIsSelectionMode(!isSelectionMode);
    if (isSelectionMode) {
      setSelectedPhotos(new Set());
    }
  };

  if (photos.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-6xl mb-4">🐦</div>
        <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 mb-2">
          No hay imágenes disponibles
        </h3>
        <p className="text-stone-600 dark:text-stone-400">
          Este perfil no tiene imágenes públicas o aún no se han cargado.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Controles de la galería */}
      <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-xl shadow-lg p-6 border border-stone-200/60 dark:border-stone-800/60">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
              🐦 Galería de Imágenes de Twitter
            </h3>
            <p className="text-sm text-stone-600 dark:text-stone-400">
              {photos.length} imagen{photos.length === 1 ? '' : 'es'} encontrada{photos.length === 1 ? '' : 's'}
            </p>
          </div>
          
          <div className="flex items-center space-x-3">
            {isSelectionMode && (
              <>
                <button
                  onClick={handleSelectAll}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
                >
                  {selectedPhotos.size === photos.length ? 'Deseleccionar todo' : 'Seleccionar todo'}
                </button>
                
                {selectedPhotos.size > 0 && (
                  <button
                    onClick={handleDownloadSelected}
                    className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 flex items-center space-x-2"
                  >
                    <span>💾</span>
                    <span>Descargar ({selectedPhotos.size})</span>
                  </button>
                )}
              </>
            )}
            
            <button
              onClick={toggleSelectionMode}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 ${
                isSelectionMode
                  ? 'bg-red-600 hover:bg-red-700 text-white'
                  : 'bg-stone-600 hover:bg-stone-700 text-white'
              }`}
            >
              {isSelectionMode ? 'Cancelar selección' : 'Seleccionar imágenes'}
            </button>
            
            {onDownloadAll && (
              <button
                onClick={onDownloadAll}
                className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 flex items-center space-x-2"
              >
                <span>📦</span>
                <span>Descargar todas</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Grid de fotos */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        {photos.map((photo) => (
          <div
            key={photo.id}
            className={`relative group cursor-pointer rounded-xl overflow-hidden bg-stone-100 dark:bg-stone-800 aspect-square ${
              isSelectionMode && selectedPhotos.has(photo.id)
                ? 'ring-4 ring-blue-500 ring-offset-2 ring-offset-white dark:ring-offset-stone-900'
                : ''
            }`}
            onClick={() => handlePhotoClick(photo)}
          >
            {/* Imagen */}
            <img
              src={photo.thumbnailUrl}
              alt={photo.caption || `Imagen de ${username}`}
              className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
              loading="lazy"
            />
            
            {/* Overlay con información */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300">
              <div className="absolute bottom-0 left-0 right-0 p-3">
                <div className="flex items-center justify-between text-white text-sm">
                  <div className="flex items-center space-x-3">
                    {photo.likes && (
                      <div className="flex items-center space-x-1">
                        <span>❤️</span>
                        <span>{formatTwitterNumber(photo.likes)}</span>
                      </div>
                    )}
                    {photo.retweets && (
                      <div className="flex items-center space-x-1">
                        <span>🔄</span>
                        <span>{formatTwitterNumber(photo.retweets)}</span>
                      </div>
                    )}
                    {photo.comments && (
                      <div className="flex items-center space-x-1">
                        <span>💬</span>
                        <span>{formatTwitterNumber(photo.comments)}</span>
                      </div>
                    )}
                  </div>
                  
                  {photo.isVideo && (
                    <div className="bg-black/50 rounded-full p-2">
                      <span>▶️</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
            
            {/* Indicador de selección */}
            {isSelectionMode && (
              <div className="absolute top-2 right-2">
                <div className={`w-6 h-6 rounded-full border-2 border-white flex items-center justify-center ${
                  selectedPhotos.has(photo.id)
                    ? 'bg-blue-500'
                    : 'bg-black/30'
                }`}>
                  {selectedPhotos.has(photo.id) && (
                    <span className="text-white text-xs">✓</span>
                  )}
                </div>
              </div>
            )}
            
            {/* Badge de video */}
            {photo.isVideo && !isSelectionMode && (
              <div className="absolute top-2 left-2 bg-black/70 text-white px-2 py-1 rounded text-xs">
                Video
              </div>
            )}
            
            {/* Badge de tweet */}
            <div className="absolute top-2 left-2 bg-blue-500/80 text-white px-2 py-1 rounded text-xs">
              Tweet
            </div>
          </div>
        ))}
      </div>
      
      {/* Modal de foto */}
      <TwitterPhotoModal
        photo={selectedPhoto}
        username={username}
        onClose={() => setSelectedPhoto(null)}
      />
    </div>
  );
}