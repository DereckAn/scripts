import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get('code');
  const error = searchParams.get('error');
  const errorDescription = searchParams.get('error_description');

  // Crear la URL de redirección a la página de Instagram con los parámetros
  const redirectUrl = new URL('/instagram-photos', request.url);

  if (error) {
    redirectUrl.searchParams.set('error', error);
    if (errorDescription) {
      redirectUrl.searchParams.set('error_description', errorDescription);
    }
  } else if (code) {
    redirectUrl.searchParams.set('code', code);
  }

  return NextResponse.redirect(redirectUrl);
}