'use client';

import { useState, useCallback } from 'react';
import { 
  TwitterScrapingResult, 
  TwitterScrapingProgress, 
  TwitterScrapingError
} from '@/types/twitter';
import { 
  scrapeTwitterProfile, 
  validateTwitterUsername, 
  cleanTwitterUsername,
  downloadTwitterPhotosAsZip,
  extractUsernameFromTwitterUrl,
  isTwitterUrl
} from '@/utils/twitter-api';
import TwitterProfileCard from '@/components/TwitterProfileCard';
import TwitterPhotoGrid from '@/components/TwitterPhotoGrid';

export default function TwitterPhotosPage() {
  const [username, setUsername] = useState('');
  const [result, setResult] = useState<TwitterScrapingResult | null>(null);
  const [progress, setProgress] = useState<TwitterScrapingProgress | null>(null);
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);

  const handleUsernameChange = (value: string) => {
    setUsername(value);
    setError('');
    
    // Si es una URL de Twitter, extraer el username
    if (isTwitterUrl(value)) {
      const extractedUsername = extractUsernameFromTwitterUrl(value);
      if (extractedUsername) {
        setUsername(extractedUsername);
      }
    }
  };

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (isLoading) return;
    
    // Validar username
    const validation = validateTwitterUsername(username);
    if (!validation.valid) {
      setError(validation.error || 'Username inválido');
      return;
    }
    
    const cleanUsername = cleanTwitterUsername(username);
    setIsLoading(true);
    setError('');
    setResult(null);
    
    // Progreso inicial
    setProgress({
      current: 0,
      total: 100,
      percentage: 0,
      status: 'loading',
      message: 'Iniciando búsqueda...'
    });
    
    try {
      // Simular progreso
      const progressSteps = [
        { percentage: 20, message: 'Conectando con Twitter/X...' },
        { percentage: 40, message: 'Verificando perfil...' },
        { percentage: 60, message: 'Obteniendo información del perfil...' },
        { percentage: 80, message: 'Cargando imágenes de tweets...' },
        { percentage: 100, message: 'Completado' }
      ];
      
      for (const step of progressSteps) {
        setProgress(prev => prev ? {
          ...prev,
          percentage: step.percentage,
          current: step.percentage,
          message: step.message,
          status: step.percentage === 100 ? 'completed' : 'scraping'
        } : null);
        
        await new Promise(resolve => setTimeout(resolve, 600));
      }
      
      // Realizar scraping/consulta API
      const scrapingResult = await scrapeTwitterProfile(cleanUsername);
      setResult(scrapingResult);
      
    } catch (err) {
      console.error('Error scraping Twitter:', err);
      
      if (err && typeof err === 'object' && 'code' in err) {
        const twitterErr = err as TwitterScrapingError;
        switch (twitterErr.code) {
          case 'PROFILE_NOT_FOUND':
            setError('👤 Perfil no encontrado. Verifica que el nombre de usuario sea correcto.');
            break;
          case 'PRIVATE_PROFILE':
            setError('🔒 Este perfil es privado. Solo se pueden visualizar perfiles públicos.');
            break;
          case 'AUTH_REQUIRED':
            setError('🔐 Se requiere autenticación para acceder a este perfil. Configura las credenciales de Twitter API.');
            break;
          case 'RATE_LIMITED':
            setError('⏱️ Demasiadas solicitudes. Intenta de nuevo en unos minutos.');
            break;
          case 'NETWORK_ERROR':
            setError('🌐 Error de conexión. Verifica tu conexión a internet.');
            break;
          default:
            setError('❌ Error desconocido. Intenta de nuevo más tarde.');
        }
      } else {
        setError('❌ Error inesperado. Intenta de nuevo más tarde.');
      }
      
      setProgress(prev => prev ? {
        ...prev,
        status: 'error',
        message: 'Error en la búsqueda'
      } : null);
    } finally {
      setIsLoading(false);
      // Limpiar progreso después de un delay
      setTimeout(() => setProgress(null), 3000);
    }
  }, [username, isLoading]);

  const handleDownloadAll = useCallback(async () => {
    if (!result?.photos.length) return;
    
    try {
      await downloadTwitterPhotosAsZip(result.photos, result.profile.username);
    } catch (error) {
      console.error('Error downloading all photos:', error);
      setError('Error al descargar las imágenes. Intenta de nuevo.');
    }
  }, [result]);

  const handleClear = () => {
    setUsername('');
    setResult(null);
    setError('');
    setProgress(null);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200 dark:from-blue-950 dark:via-blue-900 dark:to-blue-800">
      {/* Background Pattern */}
      <div className="absolute inset-0 bg-grid-blue-900/[0.04] dark:bg-grid-blue-100/[0.02]" />
      
      <div className="relative p-8 pt-20">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="text-center mb-12">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-r from-blue-600 to-blue-400 rounded-xl mb-8 shadow-lg">
              <span className="text-2xl">🐦</span>
            </div>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-blue-900 dark:text-blue-100 mb-6">
              Twitter Image Viewer
            </h1>
            <p className="text-lg text-blue-700 dark:text-blue-300 max-w-2xl mx-auto leading-relaxed">
              Visualiza y descarga imágenes de perfiles públicos de Twitter/X. Funciona con cuentas públicas y requiere configuración de API.
            </p>
          </div>

          <div className="space-y-8">
            {/* Formulario de búsqueda */}
            <div className="bg-white/80 dark:bg-blue-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-8 border border-blue-200/60 dark:border-blue-800/60">
              <form onSubmit={handleSubmit} className="space-y-6">
                <div>
                  <label className="block text-sm font-semibold text-blue-900 dark:text-blue-100 mb-3">
                    🐦 Usuario de Twitter/X
                  </label>
                  <div className="flex space-x-4">
                    <input
                      type="text"
                      value={username}
                      onChange={(e) => handleUsernameChange(e.target.value)}
                      placeholder="username o https://twitter.com/username"
                      className="flex-1 p-4 border border-blue-300 dark:border-blue-600 rounded-lg bg-white dark:bg-blue-800 text-blue-900 dark:text-blue-100 placeholder-blue-500 dark:placeholder-blue-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
                      disabled={isLoading}
                    />
                    <button
                      type="submit"
                      disabled={isLoading || !username.trim()}
                      className="bg-blue-600 hover:bg-blue-700 disabled:bg-stone-400 disabled:cursor-not-allowed text-white px-8 py-4 rounded-lg font-semibold transition-colors duration-200 flex items-center space-x-2 min-w-[140px]"
                    >
                      <span>{isLoading ? '🔄' : '🔍'}</span>
                      <span>{isLoading ? 'Buscando...' : 'Buscar'}</span>
                    </button>
                  </div>
                  
                  <div className="mt-3 text-sm text-blue-600 dark:text-blue-400">
                    💡 Puedes escribir solo el nombre de usuario (ej: <code>twitter</code>) o pegar la URL completa
                  </div>
                </div>

                {/* Botón de limpiar */}
                {(result || error) && (
                  <div className="flex justify-center">
                    <button
                      type="button"
                      onClick={handleClear}
                      className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition-colors duration-200"
                    >
                      🗑️ Limpiar resultados
                    </button>
                  </div>
                )}
              </form>
            </div>

            {/* Barra de progreso */}
            {progress && (
              <div className="bg-white/80 dark:bg-blue-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 border border-blue-200/60 dark:border-blue-800/60">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-100">
                    {progress.status === 'error' ? '❌ Error' : '🔍 Buscando perfil...'}
                  </h3>
                  <span className="text-sm text-blue-600 dark:text-blue-400">
                    {progress.percentage}%
                  </span>
                </div>
                
                <div className="w-full bg-blue-200 dark:bg-blue-700 rounded-full h-3 mb-2">
                  <div 
                    className={`h-3 rounded-full transition-all duration-300 ${
                      progress.status === 'error' 
                        ? 'bg-red-600' 
                        : 'bg-blue-600'
                    }`}
                    style={{ width: `${progress.percentage}%` }}
                  ></div>
                </div>
                
                <p className="text-sm text-blue-600 dark:text-blue-400">
                  {progress.message}
                </p>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-2xl p-6">
                <div className="flex items-start space-x-3">
                  <span className="text-2xl">⚠️</span>
                  <div>
                    <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
                      Error al buscar el perfil
                    </h3>
                    <p className="text-red-800 dark:text-red-200">
                      {error}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Resultados */}
            {result && (
              <div className="space-y-8">
                {/* Información del perfil */}
                <TwitterProfileCard profile={result.profile} />

                {/* Grid de fotos */}
                <TwitterPhotoGrid 
                  photos={result.photos}
                  username={result.profile.username}
                  onDownloadAll={handleDownloadAll}
                />
              </div>
            )}

            {/* Estado vacío */}
            {!result && !error && !progress && (
              <div className="text-center py-12">
                <div className="text-6xl mb-4">🐦</div>
                <h3 className="text-xl font-semibold text-blue-900 dark:text-blue-100 mb-2">
                  ¡Busca un perfil de Twitter!
                </h3>
                <p className="text-blue-600 dark:text-blue-400">
                  Escribe un nombre de usuario para empezar
                </p>
              </div>
            )}

            {/* Información adicional */}
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-2xl p-6 border border-blue-200 dark:border-blue-800">
              <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-100 mb-4">
                📋 Información importante
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm text-blue-800 dark:text-blue-200">
                <div>
                  <h4 className="font-semibold mb-2">✅ Funcionalidades:</h4>
                  <ul className="space-y-1">
                    <li>• Visualización de perfiles públicos</li>
                    <li>• Descarga individual de imágenes</li>
                    <li>• Descarga múltiple seleccionada</li>
                    <li>• Vista previa en modal</li>
                    <li>• Enlace al tweet original</li>
                    <li>• Información de estadísticas</li>
                  </ul>
                </div>
                
                <div>
                  <h4 className="font-semibold mb-2">⚠️ Limitaciones:</h4>
                  <ul className="space-y-1">
                    <li>• Solo perfiles públicos</li>
                    <li>• Requiere configuración de Twitter API</li>
                    <li>• Límites de tasa de Twitter/X</li>
                    <li>• Respeta los términos de Twitter</li>
                    <li>• Uso personal únicamente</li>
                    <li>• No almacenamos datos</li>
                  </ul>
                </div>
              </div>
              
              <div className="mt-6 p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800">
                <h4 className="font-semibold text-yellow-900 dark:text-yellow-100 mb-2">
                  🔧 Configuración requerida
                </h4>
                <p className="text-yellow-800 dark:text-yellow-200 text-sm">
                  Para que esta funcionalidad opere completamente, necesitas configurar las credenciales de la Twitter API. 
                  Contacta al desarrollador para obtener acceso o configura tu propia API de Twitter.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}