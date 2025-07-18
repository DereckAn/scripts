import { InstagramScrapingResult } from '@/types/instagram';

interface InstagramAuthResponse {
  accessToken: string;
  userId: string;
  expiresIn: number;
}

interface InstagramAuthError {
  error: string;
  details?: any;
}

// Función para iniciar el proceso de autenticación
export async function initiateInstagramAuth(): Promise<string> {
  try {
    const response = await fetch('/api/instagram/auth?action=login');
    const data = await response.json();
    
    if (!response.ok) {
      throw new Error(data.error || 'Failed to get auth URL');
    }
    
    return data.authUrl;
  } catch (error) {
    console.error('Error initiating Instagram auth:', error);
    throw new Error('No se pudo iniciar la autenticación con Instagram');
  }
}

// Función para intercambiar código por token de acceso
export async function exchangeCodeForToken(code: string): Promise<InstagramAuthResponse> {
  try {
    const response = await fetch('/api/instagram/auth', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Failed to exchange code for token');
    }

    return data;
  } catch (error) {
    console.error('Error exchanging code for token:', error);
    throw new Error('No se pudo obtener el token de acceso');
  }
}

// Función para obtener el perfil y fotos usando el token
export async function fetchInstagramProfile(accessToken: string): Promise<InstagramScrapingResult> {
  try {
    const response = await fetch('/api/instagram/profile', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ accessToken }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Failed to fetch Instagram profile');
    }

    return data;
  } catch (error) {
    console.error('Error fetching Instagram profile:', error);
    throw new Error('No se pudo obtener el perfil de Instagram');
  }
}

// Función para manejar tokens en localStorage
export const InstagramTokenManager = {
  save: (token: string, userId: string, expiresIn: number) => {
    const expiresAt = Date.now() + (expiresIn * 1000);
    localStorage.setItem('instagram_token', token);
    localStorage.setItem('instagram_user_id', userId);
    localStorage.setItem('instagram_expires_at', expiresAt.toString());
  },

  get: (): { token: string; userId: string } | null => {
    const token = localStorage.getItem('instagram_token');
    const userId = localStorage.getItem('instagram_user_id');
    const expiresAt = localStorage.getItem('instagram_expires_at');

    if (!token || !userId || !expiresAt) {
      return null;
    }

    // Verificar si el token ha expirado
    if (Date.now() > parseInt(expiresAt)) {
      InstagramTokenManager.clear();
      return null;
    }

    return { token, userId };
  },

  clear: () => {
    localStorage.removeItem('instagram_token');
    localStorage.removeItem('instagram_user_id');
    localStorage.removeItem('instagram_expires_at');
  },

  isValid: (): boolean => {
    return InstagramTokenManager.get() !== null;
  }
};

// Función para obtener perfil con token guardado o iniciar auth
export async function getInstagramProfileWithAuth(): Promise<{
  result?: InstagramScrapingResult;
  needsAuth?: boolean;
  authUrl?: string;
}> {
  // Verificar si hay un token válido guardado
  const tokenData = InstagramTokenManager.get();
  
  if (tokenData) {
    try {
      const result = await fetchInstagramProfile(tokenData.token);
      return { result };
    } catch (error) {
      // Token inválido, limpiar y pedir nueva autenticación
      InstagramTokenManager.clear();
    }
  }

  // Necesita nueva autenticación
  const authUrl = await initiateInstagramAuth();
  return { needsAuth: true, authUrl };
}