'use client';

import { useState, useEffect } from 'react';
import { 
  initiateInstagramAuth, 
  exchangeCodeForToken, 
  fetchInstagramProfile,
  InstagramTokenManager 
} from '@/utils/instagram-api';
import { InstagramScrapingResult } from '@/types/instagram';

interface InstagramAuthButtonProps {
  onSuccess: (result: InstagramScrapingResult) => void;
  onError: (error: string) => void;
  onLoading: (loading: boolean) => void;
}

export default function InstagramAuthButton({ 
  onSuccess, 
  onError, 
  onLoading 
}: InstagramAuthButtonProps) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState<string>('');

  useEffect(() => {
    // Verificar si hay un token válido al cargar
    const tokenData = InstagramTokenManager.get();
    if (tokenData) {
      setIsAuthenticated(true);
      // Opcional: cargar el perfil automáticamente
    }

    // Verificar si hay un código de autorización en la URL
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    const error = urlParams.get('error');

    if (error) {
      onError(`Error de autorización: ${error}`);
      // Limpiar URL
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (code) {
      handleAuthCallback(code);
    }
  }, []);

  const handleAuthCallback = async (code: string) => {
    try {
      onLoading(true);
      
      // Intercambiar código por token
      const authResponse = await exchangeCodeForToken(code);
      
      // Guardar token
      InstagramTokenManager.save(
        authResponse.accessToken, 
        authResponse.userId, 
        authResponse.expiresIn
      );
      
      // Obtener perfil
      const result = await fetchInstagramProfile(authResponse.accessToken);
      
      setIsAuthenticated(true);
      setUsername(result.profile.username || '');
      onSuccess(result);
      
      // Limpiar URL
      window.history.replaceState({}, document.title, window.location.pathname);
      
    } catch (error) {
      console.error('Auth callback error:', error);
      onError(error instanceof Error ? error.message : 'Error de autenticación');
    } finally {
      onLoading(false);
    }
  };

  const handleLogin = async () => {
    try {
      onLoading(true);
      const authUrl = await initiateInstagramAuth();
      
      // Abrir ventana de autorización
      window.location.href = authUrl;
      
    } catch (error) {
      console.error('Login error:', error);
      onError(error instanceof Error ? error.message : 'Error al iniciar sesión');
      onLoading(false);
    }
  };

  const handleLoadProfile = async () => {
    try {
      onLoading(true);
      const tokenData = InstagramTokenManager.get();
      
      if (!tokenData) {
        setIsAuthenticated(false);
        return;
      }

      const result = await fetchInstagramProfile(tokenData.token);
      onSuccess(result);
      
    } catch (error) {
      console.error('Load profile error:', error);
      // Token probablemente inválido, limpiar
      InstagramTokenManager.clear();
      setIsAuthenticated(false);
      onError(error instanceof Error ? error.message : 'Error al cargar perfil');
    } finally {
      onLoading(false);
    }
  };

  const handleLogout = () => {
    InstagramTokenManager.clear();
    setIsAuthenticated(false);
    setUsername('');
  };

  if (isAuthenticated) {
    return (
      <div className="space-y-4">
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-green-800 dark:text-green-200 font-medium">
                ✅ Conectado a Instagram
              </p>
              {username && (
                <p className="text-green-600 dark:text-green-400 text-sm">
                  Usuario: @{username}
                </p>
              )}
            </div>
            <button
              onClick={handleLogout}
              className="text-green-700 dark:text-green-300 hover:text-green-900 dark:hover:text-green-100 text-sm underline"
            >
              Desconectar
            </button>
          </div>
        </div>
        
        <button
          onClick={handleLoadProfile}
          className="w-full bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-semibold transition-colors duration-200 flex items-center justify-center space-x-2"
        >
          <span>📸</span>
          <span>Cargar mis fotos</span>
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <h4 className="text-blue-900 dark:text-blue-100 font-medium mb-2">
          🔐 Autenticación requerida
        </h4>
        <p className="text-blue-800 dark:text-blue-200 text-sm mb-3">
          Para ver las fotos de tu perfil de Instagram, necesitas autorizar esta aplicación.
        </p>
        <ul className="text-blue-700 dark:text-blue-300 text-xs space-y-1">
          <li>• Solo puedes ver tu propio perfil</li>
          <li>• Requiere una aplicación Instagram configurada</li>
          <li>• Los datos no se almacenan en nuestros servidores</li>
        </ul>
      </div>
      
      <button
        onClick={handleLogin}
        className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white px-6 py-3 rounded-lg font-semibold transition-all duration-200 flex items-center justify-center space-x-2 shadow-lg hover:shadow-xl"
      >
        <span>📱</span>
        <span>Conectar con Instagram</span>
      </button>
    </div>
  );
}