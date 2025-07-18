import { NextRequest, NextResponse } from 'next/server';

// Tipos para la respuesta de Instagram API
interface InstagramUser {
  id: string;
  username: string;
  account_type: string;
  media_count: number;
}

interface InstagramMedia {
  id: string;
  media_type: 'IMAGE' | 'VIDEO' | 'CAROUSEL_ALBUM';
  media_url: string;
  thumbnail_url?: string;
  caption?: string;
  timestamp: string;
  permalink: string;
}

interface InstagramApiResponse {
  data: InstagramMedia[];
  paging?: {
    cursors: {
      before: string;
      after: string;
    };
    next?: string;
  };
}

export async function POST(request: NextRequest) {
  try {
    const { accessToken } = await request.json();

    if (!accessToken) {
      return NextResponse.json(
        { error: 'Access token is required' },
        { status: 400 }
      );
    }

    // Obtener información del usuario
    const userResponse = await fetch(
      `https://graph.instagram.com/me?fields=id,username,account_type,media_count&access_token=${accessToken}`
    );

    if (!userResponse.ok) {
      const errorData = await userResponse.json();
      return NextResponse.json(
        { error: 'Failed to fetch user data', details: errorData },
        { status: userResponse.status }
      );
    }

    const userData: InstagramUser = await userResponse.json();

    // Obtener medios del usuario
    const mediaResponse = await fetch(
      `https://graph.instagram.com/me/media?fields=id,media_type,media_url,thumbnail_url,caption,timestamp,permalink&limit=50&access_token=${accessToken}`
    );

    if (!mediaResponse.ok) {
      const errorData = await mediaResponse.json();
      return NextResponse.json(
        { error: 'Failed to fetch media data', details: errorData },
        { status: mediaResponse.status }
      );
    }

    const mediaData: InstagramApiResponse = await mediaResponse.json();

    // Filtrar solo imágenes y videos para la respuesta
    const photos = mediaData.data
      .filter(media => media.media_type === 'IMAGE' || media.media_type === 'VIDEO')
      .map(media => ({
        id: media.id,
        url: media.media_url,
        thumbnailUrl: media.thumbnail_url || media.media_url,
        caption: media.caption,
        timestamp: media.timestamp,
        isVideo: media.media_type === 'VIDEO',
        permalink: media.permalink
      }));

    const result = {
      profile: {
        username: userData.username,
        postsCount: userData.media_count,
        isPrivate: false, // Las cuentas autorizadas no son privadas
        accountType: userData.account_type
      },
      photos: photos,
      totalCount: photos.length,
      hasMore: !!mediaData.paging?.next
    };

    return NextResponse.json(result);

  } catch (error) {
    console.error('Instagram API error:', error);
    return NextResponse.json(
      { error: 'Internal server error', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}

export async function GET() {
  return NextResponse.json(
    { error: 'Method not allowed. Use POST instead.' },
    { status: 405 }
  );
}