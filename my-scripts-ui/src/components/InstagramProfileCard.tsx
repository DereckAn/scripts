'use client';

import { InstagramProfile } from '@/types/instagram';
import { formatInstagramNumber, getInstagramProfileUrl } from '@/utils/instagram-scraper';

interface InstagramProfileCardProps {
  profile: InstagramProfile;
}

export default function InstagramProfileCard({ profile }: InstagramProfileCardProps) {
  return (
    <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-8 border border-stone-200/60 dark:border-stone-800/60">
      <div className="flex flex-col md:flex-row items-center md:items-start space-y-6 md:space-y-0 md:space-x-8">
        {/* Foto de perfil */}
        <div className="relative">
          <div className="w-32 h-32 rounded-full overflow-hidden bg-gradient-to-r from-stone-400 to-stone-600 flex items-center justify-center">
            {profile.profilePicUrl ? (
              <img
                src={profile.profilePicUrl}
                alt={`Foto de perfil de ${profile.username}`}
                className="w-full h-full object-cover"
              />
            ) : (
              <span className="text-4xl text-white font-bold">
                {profile.username.charAt(0).toUpperCase()}
              </span>
            )}
          </div>
          
          {/* Badge de verificado */}
          {profile.isVerified && (
            <div className="absolute -bottom-2 -right-2 bg-blue-500 text-white w-8 h-8 rounded-full flex items-center justify-center text-sm">
              ✓
            </div>
          )}
        </div>
        
        {/* Información del perfil */}
        <div className="flex-1 text-center md:text-left space-y-4">
          {/* Username y nombre */}
          <div>
            <div className="flex items-center justify-center md:justify-start space-x-2 mb-2">
              <h1 className="text-2xl font-bold text-stone-900 dark:text-stone-100">
                @{profile.username}
              </h1>
              {profile.isVerified && (
                <span className="text-blue-500 text-xl">✓</span>
              )}
            </div>
            
            {profile.fullName && (
              <h2 className="text-lg text-stone-700 dark:text-stone-300 font-medium">
                {profile.fullName}
              </h2>
            )}
          </div>
          
          {/* Estadísticas */}
          <div className="grid grid-cols-3 gap-6 py-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-stone-900 dark:text-stone-100">
                {formatInstagramNumber(profile.postsCount)}
              </div>
              <div className="text-sm text-stone-600 dark:text-stone-400">
                publicaciones
              </div>
            </div>
            
            <div className="text-center">
              <div className="text-2xl font-bold text-stone-900 dark:text-stone-100">
                {formatInstagramNumber(profile.followersCount)}
              </div>
              <div className="text-sm text-stone-600 dark:text-stone-400">
                seguidores
              </div>
            </div>
            
            <div className="text-center">
              <div className="text-2xl font-bold text-stone-900 dark:text-stone-100">
                {formatInstagramNumber(profile.followingCount)}
              </div>
              <div className="text-sm text-stone-600 dark:text-stone-400">
                siguiendo
              </div>
            </div>
          </div>
          
          {/* Bio */}
          {profile.bio && (
            <div>
              <p className="text-stone-700 dark:text-stone-300 leading-relaxed">
                {profile.bio}
              </p>
            </div>
          )}
          
          {/* Enlace externo */}
          {profile.externalUrl && (
            <div>
              <a
                href={profile.externalUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:underline text-sm"
              >
                {profile.externalUrl}
              </a>
            </div>
          )}
          
          {/* Estado del perfil */}
          <div className="flex items-center justify-center md:justify-start space-x-4 text-sm">
            <div className={`px-3 py-1 rounded-full ${
              profile.isPrivate 
                ? 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200'
                : 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200'
            }`}>
              {profile.isPrivate ? '🔒 Privado' : '🌍 Público'}
            </div>
            
            {profile.isVerified && (
              <div className="bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 px-3 py-1 rounded-full">
                ✓ Verificado
              </div>
            )}
          </div>
          
          {/* Botón para ir a Instagram */}
          <div className="pt-4">
            <a
              href={getInstagramProfileUrl(profile.username)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center space-x-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white px-6 py-3 rounded-lg font-medium transition-all duration-200 shadow-lg hover:shadow-xl"
            >
              <span>📱</span>
              <span>Ver en Instagram</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}