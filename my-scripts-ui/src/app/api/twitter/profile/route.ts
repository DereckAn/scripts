import { NextRequest, NextResponse } from 'next/server';
import { TwitterScrapingResult, TwitterScrapingError, TwitterProfile, TwitterPhoto } from '@/types/twitter';

export async function POST(request: NextRequest) {
  try {
    const { username } = await request.json();

    if (!username) {
      return NextResponse.json(
        { error: 'Username is required' },
        { status: 400 }
      );
    }

    // TODO: Implementar la lógica real de Twitter API
    // Por ahora, devolvemos datos de ejemplo o un error indicando que se necesita configuración
    
    // Verificar si hay credenciales de Twitter configuradas
    const hasTwitterCredentials = process.env.TWITTER_API_KEY && 
                                 process.env.TWITTER_API_SECRET && 
                                 process.env.TWITTER_ACCESS_TOKEN && 
                                 process.env.TWITTER_ACCESS_TOKEN_SECRET;

    if (!hasTwitterCredentials) {
      return NextResponse.json(
        { 
          code: 'AUTH_REQUIRED',
          message: 'Twitter API credentials not configured. Please set up TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, and TWITTER_ACCESS_TOKEN_SECRET environment variables.',
          details: 'Contact the developer to configure Twitter API access.'
        },
        { status: 403 }
      );
    }

    // Aquí iría la implementación real con Twitter API
    // Ejemplo de lo que se podría implementar:
    
    /*
    import { TwitterApi } from 'twitter-api-v2';
    
    const twitterClient = new TwitterApi({
      appKey: process.env.TWITTER_API_KEY!,
      appSecret: process.env.TWITTER_API_SECRET!,
      accessToken: process.env.TWITTER_ACCESS_TOKEN!,
      accessSecret: process.env.TWITTER_ACCESS_TOKEN_SECRET!,
    });

    // Obtener información del usuario
    const user = await twitterClient.v2.userByUsername(username, {
      'user.fields': ['public_metrics', 'description', 'profile_image_url', 'created_at', 'verified', 'protected', 'location', 'url']
    });

    if (!user.data) {
      return NextResponse.json(
        { code: 'PROFILE_NOT_FOUND', message: 'User not found' },
        { status: 404 }
      );
    }

    if (user.data.protected) {
      return NextResponse.json(
        { code: 'PRIVATE_PROFILE', message: 'This profile is private' },
        { status: 401 }
      );
    }

    // Obtener tweets con imágenes del usuario
    const tweets = await twitterClient.v2.userTimeline(user.data.id, {
      max_results: 100,
      exclude: ['retweets', 'replies'],
      expansions: ['attachments.media_keys'],
      'media.fields': ['url', 'preview_image_url', 'type', 'width', 'height', 'public_metrics'],
      'tweet.fields': ['created_at', 'public_metrics', 'text']
    });

    // Filtrar tweets que tengan imágenes
    const photosWithTweets = [];
    for (const tweet of tweets.data || []) {
      if (tweet.attachments?.media_keys) {
        const media = tweets.includes?.media?.filter(m => 
          tweet.attachments.media_keys.includes(m.media_key) && 
          (m.type === 'photo' || m.type === 'video')
        );
        
        if (media && media.length > 0) {
          for (const mediaItem of media) {
            photosWithTweets.push({
              id: mediaItem.media_key,
              url: mediaItem.url || '',
              thumbnailUrl: mediaItem.preview_image_url || mediaItem.url || '',
              highResUrl: mediaItem.url || '',
              width: mediaItem.width || 0,
              height: mediaItem.height || 0,
              caption: tweet.text,
              likes: tweet.public_metrics?.like_count,
              retweets: tweet.public_metrics?.retweet_count,
              comments: tweet.public_metrics?.reply_count,
              publishedAt: tweet.created_at || '',
              tweetId: tweet.id,
              isVideo: mediaItem.type === 'video',
              videoUrl: mediaItem.type === 'video' ? mediaItem.url : undefined
            });
          }
        }
      }
    }
    */

    // Por ahora, devolver datos de ejemplo para demostrar la funcionalidad
    const mockProfile: TwitterProfile = {
      id: '123456789',
      username: username,
      displayName: `Usuario de ejemplo (${username})`,
      bio: 'Este es un perfil de ejemplo. Para ver datos reales, configura la Twitter API.',
      profileImageUrl: 'https://via.placeholder.com/150x150/1DA1F2/ffffff?text=T',
      bannerUrl: 'https://via.placeholder.com/1500x500/1DA1F2/ffffff?text=Twitter+Banner',
      followersCount: 1000,
      followingCount: 500,
      tweetsCount: 2500,
      isVerified: false,
      isPrivate: false,
      joinDate: '2020-01-01T00:00:00.000Z',
      website: 'https://example.com',
      location: 'Internet'
    };

    const mockPhotos: TwitterPhoto[] = [
      {
        id: 'mock_photo_1',
        url: 'https://via.placeholder.com/800x600/1DA1F2/ffffff?text=Tweet+Image+1',
        thumbnailUrl: 'https://via.placeholder.com/300x300/1DA1F2/ffffff?text=Tweet+Image+1',
        highResUrl: 'https://via.placeholder.com/1200x900/1DA1F2/ffffff?text=Tweet+Image+1',
        width: 800,
        height: 600,
        caption: 'Esta es una imagen de ejemplo de un tweet. Configura la Twitter API para ver contenido real.',
        likes: 42,
        retweets: 12,
        comments: 5,
        publishedAt: '2024-01-15T10:30:00.000Z',
        tweetId: 'mock_tweet_1',
        isVideo: false
      },
      {
        id: 'mock_photo_2',
        url: 'https://via.placeholder.com/600x800/1DA1F2/ffffff?text=Tweet+Image+2',
        thumbnailUrl: 'https://via.placeholder.com/300x300/1DA1F2/ffffff?text=Tweet+Image+2',
        highResUrl: 'https://via.placeholder.com/900x1200/1DA1F2/ffffff?text=Tweet+Image+2',
        width: 600,
        height: 800,
        caption: 'Otra imagen de ejemplo. Los datos reales requieren configuración de API.',
        likes: 28,
        retweets: 8,
        comments: 3,
        publishedAt: '2024-01-14T15:45:00.000Z',
        tweetId: 'mock_tweet_2',
        isVideo: false
      }
    ];

    const result: TwitterScrapingResult = {
      profile: mockProfile,
      photos: mockPhotos,
      hasMore: false,
      nextCursor: undefined
    };

    return NextResponse.json(result);

  } catch (error) {
    console.error('Error in Twitter profile API:', error);
    
    return NextResponse.json(
      { 
        code: 'UNKNOWN_ERROR',
        message: 'Internal server error',
        details: error instanceof Error ? error.message : 'Unknown error'
      },
      { status: 500 }
    );
  }
}