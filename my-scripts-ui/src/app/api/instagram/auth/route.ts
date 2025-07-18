import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const action = searchParams.get('action');

  if (action === 'login') {
    // Generar URL de autorización de Instagram
    const instagramAppId = process.env.INSTAGRAM_APP_ID;
    const redirectUri = process.env.INSTAGRAM_REDIRECT_URI;

    if (!instagramAppId || !redirectUri) {
      return NextResponse.json(
        { error: 'Instagram configuration missing' },
        { status: 500 }
      );
    }

    const authUrl = new URL('https://api.instagram.com/oauth/authorize');
    authUrl.searchParams.set('client_id', instagramAppId);
    authUrl.searchParams.set('redirect_uri', redirectUri);
    authUrl.searchParams.set('scope', 'user_profile,user_media');
    authUrl.searchParams.set('response_type', 'code');

    return NextResponse.json({ authUrl: authUrl.toString() });
  }

  return NextResponse.json(
    { error: 'Invalid action' },
    { status: 400 }
  );
}

export async function POST(request: NextRequest) {
  try {
    const { code } = await request.json();

    if (!code) {
      return NextResponse.json(
        { error: 'Authorization code is required' },
        { status: 400 }
      );
    }

    const instagramAppId = process.env.INSTAGRAM_APP_ID;
    const instagramAppSecret = process.env.INSTAGRAM_APP_SECRET;
    const redirectUri = process.env.INSTAGRAM_REDIRECT_URI;

    if (!instagramAppId || !instagramAppSecret || !redirectUri) {
      return NextResponse.json(
        { error: 'Instagram configuration missing' },
        { status: 500 }
      );
    }

    // Intercambiar código por token de acceso
    const tokenResponse = await fetch('https://api.instagram.com/oauth/access_token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: instagramAppId,
        client_secret: instagramAppSecret,
        grant_type: 'authorization_code',
        redirect_uri: redirectUri,
        code: code,
      }),
    });

    if (!tokenResponse.ok) {
      const errorData = await tokenResponse.json();
      return NextResponse.json(
        { error: 'Failed to exchange code for token', details: errorData },
        { status: tokenResponse.status }
      );
    }

    const tokenData = await tokenResponse.json();

    // Intercambiar token de corta duración por token de larga duración
    const longLivedTokenResponse = await fetch(
      `https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=${instagramAppSecret}&access_token=${tokenData.access_token}`
    );

    if (!longLivedTokenResponse.ok) {
      // Si falla, usar el token de corta duración
      return NextResponse.json({
        accessToken: tokenData.access_token,
        userId: tokenData.user_id,
        expiresIn: 3600 // 1 hora para tokens de corta duración
      });
    }

    const longLivedTokenData = await longLivedTokenResponse.json();

    return NextResponse.json({
      accessToken: longLivedTokenData.access_token,
      userId: tokenData.user_id,
      expiresIn: longLivedTokenData.expires_in || 5184000 // 60 días por defecto
    });

  } catch (error) {
    console.error('Instagram auth error:', error);
    return NextResponse.json(
      { error: 'Internal server error', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}