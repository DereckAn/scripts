import { 
  InstagramProfile, 
  InstagramPhoto, 
  InstagramScrapingResult 
} from '@/types/instagram';

// Función para validar nombre de usuario de Instagram
export function validateInstagramUsername(username: string): { valid: boolean; error?: string } {
  if (!username.trim()) {
    return { valid: false, error: 'El nombre de usuario es obligatorio' };
  }
  
  if (username.length < 1 || username.length > 30) {
    return { valid: false, error: 'El nombre de usuario debe tener entre 1 y 30 caracteres' };
  }
  
  // Remover @ si está presente
  const cleanUsername = username.replace('@', '');
  
  // Validar caracteres permitidos (letras, números, puntos y guiones bajos)
  const validPattern = /^[a-zA-Z0-9._]+$/;
  if (!validPattern.test(cleanUsername)) {
    return { valid: false, error: 'El nombre de usuario solo puede contener letras, números, puntos y guiones bajos' };
  }
  
  return { valid: true };
}

// Función para limpiar nombre de usuario
export function cleanInstagramUsername(username: string): string {
  return username.replace('@', '').toLowerCase().trim();
}

// Función para formatear números (seguidores, etc.)
export function formatInstagramNumber(num?: number): string {
  if (!num) return '0';
  
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M';
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K';
  }
  
  return num.toString();
}

// Función para formatear fecha
export function formatInstagramDate(timestamp?: string): string {
  if (!timestamp) return '';
  
  const date = new Date(timestamp);
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);
  
  if (diffInSeconds < 60) {
    return 'Hace unos segundos';
  } else if (diffInSeconds < 3600) {
    const minutes = Math.floor(diffInSeconds / 60);
    return `Hace ${minutes} minuto${minutes > 1 ? 's' : ''}`;
  } else if (diffInSeconds < 86400) {
    const hours = Math.floor(diffInSeconds / 3600);
    return `Hace ${hours} hora${hours > 1 ? 's' : ''}`;
  } else if (diffInSeconds < 604800) {
    const days = Math.floor(diffInSeconds / 86400);
    return `Hace ${days} día${days > 1 ? 's' : ''}`;
  } else {
    return date.toLocaleDateString('es-ES', {
      day: 'numeric',
      month: 'short',
      year: 'numeric'
    });
  }
}

// Función para descargar imagen
export async function downloadInstagramPhoto(photo: InstagramPhoto, filename?: string): Promise<void> {
  try {
    const response = await fetch(photo.url);
    if (!response.ok) throw new Error('Error al descargar la imagen');
    
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `instagram_${photo.id}.jpg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error('Error downloading photo:', error);
    throw new Error('No se pudo descargar la imagen');
  }
}

// Función para descargar múltiples fotos como ZIP
export async function downloadInstagramPhotosAsZip(
  photos: InstagramPhoto[], 
  username: string
): Promise<void> {
  // Nota: Esta función requeriría una librería como JSZip
  // Por ahora, descargaremos las fotos una por una
  try {
    for (let i = 0; i < photos.length; i++) {
      const photo = photos[i];
      await downloadInstagramPhoto(photo, `${username}_${i + 1}_${photo.id}.jpg`);
      
      // Delay para evitar problemas con el navegador
      if (i < photos.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }
  } catch (error) {
    console.error('Error downloading photos as ZIP:', error);
    throw new Error('Error al descargar las fotos');
  }
}

// Función simulada para obtener perfil de Instagram (en producción sería una API real)
export async function scrapeInstagramProfile(username: string): Promise<InstagramScrapingResult> {
  const cleanUsername = cleanInstagramUsername(username);
  
  // Simular delay de red
  await new Promise(resolve => setTimeout(resolve, 2000));
  
  // Simular diferentes casos
  if (cleanUsername === 'private_user') {
    throw new InstagramScrapingError('PRIVATE_PROFILE', 'Este perfil es privado');
  }
  
  if (cleanUsername === 'not_found') {
    throw new InstagramScrapingError('PROFILE_NOT_FOUND', 'Usuario no encontrado');
  }
  
  // Datos simulados
  const mockProfile: InstagramProfile = {
    username: cleanUsername,
    fullName: `Usuario ${cleanUsername}`,
    bio: `Bienvenido al perfil de ${cleanUsername}. Este es un perfil de ejemplo para mostrar la funcionalidad.`,
    profilePicUrl: `https://via.placeholder.com/150/6366f1/white?text=${cleanUsername.charAt(0).toUpperCase()}`,
    followersCount: Math.floor(Math.random() * 10000) + 1000,
    followingCount: Math.floor(Math.random() * 1000) + 100,
    postsCount: Math.floor(Math.random() * 100) + 20,
    isVerified: Math.random() > 0.8,
    isPrivate: false,
    externalUrl: `https://example.com/${cleanUsername}`
  };
  
  // Generar fotos simuladas
  const mockPhotos: InstagramPhoto[] = [];
  const photoCount = mockProfile.postsCount || 24;
  
  for (let i = 0; i < photoCount; i++) {
    const photoId = `photo_${i + 1}`;
    const size = 400 + (i % 3) * 100; // Diferentes tamaños
    
    mockPhotos.push({
      id: photoId,
      url: `https://picsum.photos/${size}/${size}?random=${i}`,
      thumbnailUrl: `https://picsum.photos/300/300?random=${i}`,
      caption: i % 3 === 0 ? `Esta es la descripción de la foto ${i + 1} #photo #${cleanUsername}` : undefined,
      likes: Math.floor(Math.random() * 1000) + 10,
      comments: Math.floor(Math.random() * 100) + 1,
      timestamp: new Date(Date.now() - (i * 24 * 60 * 60 * 1000)).toISOString(),
      isVideo: i % 7 === 0, // Algunos videos aleatorios
      dimensions: {
        width: size,
        height: size
      }
    });
  }
  
  return {
    profile: mockProfile,
    photos: mockPhotos,
    totalCount: photoCount,
    hasMore: false
  };
}

// Clase de error personalizada
export class InstagramScrapingError extends Error {
  constructor(
    public code: 'PROFILE_NOT_FOUND' | 'PRIVATE_PROFILE' | 'RATE_LIMITED' | 'NETWORK_ERROR' | 'UNKNOWN_ERROR',
    message: string,
    public details?: string
  ) {
    super(message);
    this.name = 'InstagramScrapingError';
  }
}

// Función para obtener URL de perfil de Instagram
export function getInstagramProfileUrl(username: string): string {
  const cleanUsername = cleanInstagramUsername(username);
  return `https://instagram.com/${cleanUsername}`;
}

// Función para validar si una URL es de Instagram
export function isInstagramUrl(url: string): boolean {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname === 'instagram.com' || urlObj.hostname === 'www.instagram.com';
  } catch {
    return false;
  }
}

// Función para extraer username de URL de Instagram
export function extractUsernameFromInstagramUrl(url: string): string | null {
  try {
    const urlObj = new URL(url);
    if (!isInstagramUrl(url)) return null;
    
    const pathSegments = urlObj.pathname.split('/').filter(segment => segment);
    return pathSegments[0] || null;
  } catch {
    return null;
  }
}