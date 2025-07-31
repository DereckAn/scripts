'use client';

import { TwitterProfile } from '@/types/twitter';
import { formatTwitterNumber, formatTwitterDate } from '@/utils/twitter-api';

interface TwitterProfileCardProps {
  profile: TwitterProfile;
}

export default function TwitterProfileCard({ profile }: TwitterProfileCardProps) {
  return (
    <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl border border-stone-200/60 dark:border-stone-800/60 overflow-hidden">
      {/* Banner */}
      {profile.bannerUrl && (
        <div className="h-32 sm:h-48 bg-gradient-to-r from-blue-500 to-purple-600 relative">
          <img
            src={profile.bannerUrl}
            alt={`Banner de ${profile.displayName}`}
            className="w-full h-full object-cover"
          />
        </div>
      )}
      
      <div className="p-6 sm:p-8 relative">
        {/* Foto de perfil */}
        <div className="flex flex-col sm:flex-row items-start sm:items-end space-y-4 sm:space-y-0 sm:space-x-6 mb-6">
          <div className={`relative ${profile.bannerUrl ? '-mt-16 sm:-mt-20' : ''}`}>
            <img
              src={profile.profileImageUrl}
              alt={`Foto de perfil de ${profile.displayName}`}
              className="w-24 h-24 sm:w-32 sm:h-32 rounded-full border-4 border-white dark:border-stone-900 shadow-lg bg-white"
            />
            {profile.isVerified && (
              <div className="absolute -bottom-2 -right-2 bg-blue-500 rounded-full p-2 border-2 border-white dark:border-stone-900">
                <span className="text-white text-sm">✓</span>
              </div>
            )}
          </div>
          
          <div className="flex-1 min-w-0">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-2xl sm:text-3xl font-bold text-stone-900 dark:text-stone-100 break-words">
                  {profile.displayName}
                  {profile.isVerified && (
                    <span className="ml-2 text-blue-500">✓</span>
                  )}
                </h2>
                <p className="text-lg text-stone-600 dark:text-stone-400">
                  @{profile.username}
                </p>
              </div>
              
              {profile.isPrivate && (
                <div className="mt-2 sm:mt-0">
                  <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400">
                    🔒 Cuenta privada
                  </span>
                </div>
              )}
            </div>
            
            {/* Bio */}
            {profile.bio && (
              <p className="mt-4 text-stone-700 dark:text-stone-300 leading-relaxed">
                {profile.bio}
              </p>
            )}
            
            {/* Información adicional */}
            <div className="mt-4 flex flex-wrap items-center text-sm text-stone-600 dark:text-stone-400 space-x-4">
              {profile.location && (
                <div className="flex items-center space-x-1">
                  <span>📍</span>
                  <span>{profile.location}</span>
                </div>
              )}
              
              {profile.website && (
                <div className="flex items-center space-x-1">
                  <span>🔗</span>
                  <a
                    href={profile.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 hover:underline"
                  >
                    {profile.website.replace(/^https?:\/\//, '')}
                  </a>
                </div>
              )}
              
              <div className="flex items-center space-x-1">
                <span>📅</span>
                <span>Se unió en {formatTwitterDate(profile.joinDate)}</span>
              </div>
            </div>
          </div>
        </div>
        
        {/* Estadísticas */}
        <div className="grid grid-cols-3 gap-4 pt-6 border-t border-stone-200 dark:border-stone-700">
          <div className="text-center">
            <div className="text-2xl sm:text-3xl font-bold text-stone-900 dark:text-stone-100">
              {formatTwitterNumber(profile.tweetsCount)}
            </div>
            <div className="text-sm text-stone-600 dark:text-stone-400">
              Tweets
            </div>
          </div>
          
          <div className="text-center">
            <div className="text-2xl sm:text-3xl font-bold text-stone-900 dark:text-stone-100">
              {formatTwitterNumber(profile.followingCount)}
            </div>
            <div className="text-sm text-stone-600 dark:text-stone-400">
              Siguiendo
            </div>
          </div>
          
          <div className="text-center">
            <div className="text-2xl sm:text-3xl font-bold text-stone-900 dark:text-stone-100">
              {formatTwitterNumber(profile.followersCount)}
            </div>
            <div className="text-sm text-stone-600 dark:text-stone-400">
              Seguidores
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}