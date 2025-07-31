import { TwitterScrapingResult, TwitterScrapingError, TwitterPhoto, TwitterProfile } from '@/types/twitter';

interface TwitterApiResponse {
  data?: any;
  includes?: any;
  errors?: any[];
}

// Función para validar nombre de usuario de Twitter
export function validateTwitterUsername(username: string): { valid: boolean; error?: string } {
  const cleanUsername = cleanTwitterUsername(username);
  
  if (!cleanUsername) {
    return { valid: false, error: 'El nombre de usuario no puede estar vacío' };
  }
  
  if (cleanUsername.length > 15) {
    return { valid: false, error: 'El nombre de usuario no puede tener más de 15 caracteres' };
  }
  
  if (!/^[a-zA-Z0-9_]+$/.test(cleanUsername)) {
    return { valid: false, error: 'El nombre de usuario solo puede contener letras, números y guiones bajos' };
  }
  
  return { valid: true };
}

// Función para limpiar nombre de usuario de Twitter
export function cleanTwitterUsername(username: string): string {
  return username.trim().replace(/^@/, '');
}

// Función para extraer username de URL de Twitter
export function extractUsernameFromTwitterUrl(url: string): string | null {
  try {
    const urlObj = new URL(url);
    if (urlObj.hostname === 'twitter.com' || urlObj.hostname === 'x.com') {
      const pathParts = urlObj.pathname.split('/').filter(Boolean);
      if (pathParts.length > 0) {
        return pathParts[0];
      }
    }
  } catch {
    // URL inválida
  }
  return null;
}

// Función para verificar si es una URL de Twitter
export function isTwitterUrl(text: string): boolean {
  try {
    const url = new URL(text);
    return url.hostname === 'twitter.com' || url.hostname === 'x.com';
  } catch {
    return false;
  }
}

// Función para formatear números (similar a Instagram)
export function formatTwitterNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
  }
  return num.toString();
}

// Función para formatear fechas
export function formatTwitterDate(dateString: string): string {
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('es-ES', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(date);
}

// Función principal para obtener perfil y fotos de Twitter
export async function scrapeTwitterProfile(username: string): Promise<TwitterScrapingResult> {
  try {
    const response = await fetch('/api/twitter/profile', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw createTwitterError(response.status, errorData);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error scraping Twitter profile:', error);
    
    if (error instanceof Error && 'code' in error) {
      throw error;
    }
    
    throw createTwitterError(500, { message: 'Error inesperado al obtener el perfil' });
  }
}

// Función para crear errores tipificados
function createTwitterError(status: number, errorData: any): TwitterScrapingError {
  let code: TwitterScrapingError['code'] = 'UNKNOWN_ERROR';
  let message = 'Error desconocido';

  switch (status) {
    case 404:
      code = 'PROFILE_NOT_FOUND';
      message = 'Perfil no encontrado';
      break;
    case 401:
      code = 'PRIVATE_PROFILE';
      message = 'Perfil privado o requiere autenticación';
      break;
    case 429:
      code = 'RATE_LIMITED';
      message = 'Demasiadas solicitudes. Intenta de nuevo más tarde';
      break;
    case 403:
      code = 'AUTH_REQUIRED';
      message = 'Se requiere autenticación para acceder a este perfil';
      break;
    default:
      code = 'NETWORK_ERROR';
      message = errorData.message || 'Error de red';
  }

  return {
    code,
    message,
    details: errorData
  };
}

// Función para descargar una foto de Twitter
export async function downloadTwitterPhoto(photo: TwitterPhoto, filename?: string): Promise<void> {
  try {
    const imageUrl = photo.highResUrl || photo.url;
    const response = await fetch(imageUrl);
    
    if (!response.ok) {
      throw new Error('Error al descargar la imagen');
    }
    
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `twitter_${photo.id}.jpg`;
    document.body.appendChild(a);
    a.click();
    
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (error) {
    console.error('Error downloading photo:', error);
    throw new Error('Error al descargar la foto');
  }
}

// Función para descargar múltiples fotos como ZIP (placeholder)
export async function downloadTwitterPhotosAsZip(photos: TwitterPhoto[], username: string): Promise<void> {
  // Para implementar en el futuro si se necesita
  // Por ahora, descargar una por una con delay
  for (let i = 0; i < photos.length; i++) {
    const photo = photos[i];
    await downloadTwitterPhoto(photo, `${username}_${photo.id}.jpg`);
    
    // Delay para evitar problemas con el navegador
    if (i < photos.length - 1) {
      await new Promise(resolve => setTimeout(resolve, 800));
    }
  }
}

// Función para iniciar autenticación con Twitter OAuth
export async function initiateTwitterAuth(): Promise<string> {
  try {
    const response = await fetch('/api/twitter/auth?action=login');
    const data = await response.json();
    
    if (!response.ok) {
      throw new Error(data.error || 'Failed to get auth URL');
    }
    
    return data.authUrl;
  } catch (error) {
    console.error('Error initiating Twitter auth:', error);
    throw new Error('No se pudo iniciar la autenticación con Twitter');
  }
}

// Función para manejar tokens en localStorage
export const TwitterTokenManager = {
  save: (token: string, userId: string, expiresIn: number) => {
    const expiresAt = Date.now() + (expiresIn * 1000);
    localStorage.setItem('twitter_token', token);
    localStorage.setItem('twitter_user_id', userId);
    localStorage.setItem('twitter_expires_at', expiresAt.toString());
  },

  get: (): { token: string; userId: string } | null => {
    const token = localStorage.getItem('twitter_token');
    const userId = localStorage.getItem('twitter_user_id');
    const expiresAt = localStorage.getItem('twitter_expires_at');

    if (!token || !userId || !expiresAt) {
      return null;
    }

    if (Date.now() > parseInt(expiresAt)) {
      TwitterTokenManager.clear();
      return null;
    }

    return { token, userId };
  },

  clear: () => {
    localStorage.removeItem('twitter_token');
    localStorage.removeItem('twitter_user_id');
    localStorage.removeItem('twitter_expires_at');
  },

  isValid: (): boolean => {
    return TwitterTokenManager.get() !== null;
  }
};