'use client';

import { ScrapingProgress as Progress } from '@/types/web-scraper';

interface ScrapingProgressProps {
  progress: Progress;
  onPause?: () => void;
  onResume?: () => void;
  onStop?: () => void;
  isPaused?: boolean;
}

export default function ScrapingProgress({ 
  progress, 
  onPause, 
  onResume, 
  onStop, 
  isPaused 
}: ScrapingProgressProps) {
  const getStatusIcon = () => {
    switch (progress.status) {
      case 'discovering':
        return '🔍';
      case 'scraping':
        return '📥';
      case 'processing':
        return '⚙️';
      case 'completed':
        return '✅';
      case 'error':
        return '❌';
      default:
        return '⏳';
    }
  };

  const getStatusText = () => {
    switch (progress.status) {
      case 'discovering':
        return 'Descubriendo páginas...';
      case 'scraping':
        return 'Extrayendo contenido...';
      case 'processing':
        return 'Procesando datos...';
      case 'completed':
        return 'Completado';
      case 'error':
        return 'Error en el proceso';
      default:
        return 'Preparando...';
    }
  };

  const getStatusColor = () => {
    switch (progress.status) {
      case 'discovering':
        return 'text-blue-600 dark:text-blue-400';
      case 'scraping':
        return 'text-purple-600 dark:text-purple-400';
      case 'processing':
        return 'text-yellow-600 dark:text-yellow-400';
      case 'completed':
        return 'text-green-600 dark:text-green-400';
      case 'error':
        return 'text-red-600 dark:text-red-400';
      default:
        return 'text-stone-600 dark:text-stone-400';
    }
  };

  return (
    <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 border border-stone-200/60 dark:border-stone-800/60">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          <span className="text-2xl">{getStatusIcon()}</span>
          <div>
            <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
              Progreso del Scraping
            </h3>
            <p className={`text-sm font-medium ${getStatusColor()}`}>
              {isPaused ? '⏸️ Pausado' : getStatusText()}
            </p>
          </div>
        </div>

        {/* Controles */}
        <div className="flex space-x-2">
          {progress.status === 'scraping' && (
            <>
              {isPaused ? (
                <button
                  onClick={onResume}
                  className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
                >
                  ▶️ Reanudar
                </button>
              ) : (
                <button
                  onClick={onPause}
                  className="bg-yellow-600 hover:bg-yellow-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
                >
                  ⏸️ Pausar
                </button>
              )}
            </>
          )}
          
          {(progress.status === 'scraping' || progress.status === 'processing') && (
            <button
              onClick={onStop}
              className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
            >
              ⏹️ Detener
            </button>
          )}
        </div>
      </div>

      {/* Barra de progreso principal */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-stone-700 dark:text-stone-300">
            Progreso general
          </span>
          <span className="text-sm text-stone-600 dark:text-stone-400">
            {progress.current} de {progress.total} ({progress.percentage}%)
          </span>
        </div>
        
        <div className="w-full bg-stone-200 dark:bg-stone-700 rounded-full h-3">
          <div 
            className="bg-blue-600 h-3 rounded-full transition-all duration-300 relative overflow-hidden"
            style={{ width: `${progress.percentage}%` }}
          >
            {!isPaused && progress.status === 'scraping' && (
              <div className="absolute inset-0 bg-white/20 animate-pulse"></div>
            )}
          </div>
        </div>
      </div>

      {/* URL actual */}
      {progress.currentUrl && (
        <div className="mb-6">
          <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
            Procesando actualmente:
          </label>
          <div className="bg-stone-100 dark:bg-stone-800 rounded-lg p-3">
            <p className="text-sm text-stone-700 dark:text-stone-300 break-all">
              {progress.currentUrl}
            </p>
          </div>
        </div>
      )}

      {/* Estadísticas detalladas */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="text-center p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
          <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
            {progress.discovered}
          </div>
          <div className="text-xs text-blue-700 dark:text-blue-300 font-medium">
            Descubiertas
          </div>
        </div>

        <div className="text-center p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
          <div className="text-2xl font-bold text-purple-600 dark:text-purple-400">
            {progress.processed}
          </div>
          <div className="text-xs text-purple-700 dark:text-purple-300 font-medium">
            Procesadas
          </div>
        </div>

        <div className="text-center p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
          <div className="text-2xl font-bold text-green-600 dark:text-green-400">
            {progress.successful}
          </div>
          <div className="text-xs text-green-700 dark:text-green-300 font-medium">
            Exitosas
          </div>
        </div>

        <div className="text-center p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
          <div className="text-2xl font-bold text-red-600 dark:text-red-400">
            {progress.failed}
          </div>
          <div className="text-xs text-red-700 dark:text-red-300 font-medium">
            Fallidas
          </div>
        </div>

        <div className="text-center p-3 bg-stone-50 dark:bg-stone-800 rounded-lg">
          <div className="text-2xl font-bold text-stone-600 dark:text-stone-400">
            {progress.skipped}
          </div>
          <div className="text-xs text-stone-700 dark:text-stone-300 font-medium">
            Omitidas
          </div>
        </div>
      </div>

      {/* Estimación de tiempo */}
      {progress.status === 'scraping' && progress.current > 0 && (
        <div className="mt-4 text-center">
          <p className="text-sm text-stone-600 dark:text-stone-400">
            {isPaused ? 'Scraping pausado' : 'Estimando tiempo restante...'}
          </p>
        </div>
      )}
    </div>
  );
}