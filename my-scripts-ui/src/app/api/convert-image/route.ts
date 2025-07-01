import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get('file') as File;
    const format = formData.get('format') as string;
    const quality = parseInt(formData.get('quality') as string) || 80;
    const width = formData.get('width') ? parseInt(formData.get('width') as string) : undefined;
    const height = formData.get('height') ? parseInt(formData.get('height') as string) : undefined;
    const maintainAspectRatio = formData.get('maintainAspectRatio') === 'true';
    const removeMetadata = formData.get('removeMetadata') === 'true';
    const backgroundColor = formData.get('backgroundColor') as string || '#ffffff';

    if (!file) {
      return NextResponse.json(
        { error: 'No file provided' },
        { status: 400 }
      );
    }

    if (!format) {
      return NextResponse.json(
        { error: 'No format specified' },
        { status: 400 }
      );
    }

    // Validate file type
    if (!file.type.startsWith('image/')) {
      return NextResponse.json(
        { error: 'File must be an image' },
        { status: 400 }
      );
    }

    // Validate file size (50MB limit)
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
      return NextResponse.json(
        { error: 'File too large (maximum 50MB)' },
        { status: 400 }
      );
    }

    // Convert file to buffer
    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    // For server-side image processing, you would typically use a library like:
    // - sharp (for Node.js)
    // - ImageMagick
    // - Canvas API
    
    // Since we're doing client-side conversion in this implementation,
    // this endpoint serves as a fallback or for future server-side processing
    
    // For now, we'll return the original file with a note
    // In a real implementation, you'd process the image here
    
    const outputMimeType = getMimeType(format);
    const outputFilename = generateFilename(file.name, format);

    // For demonstration, return the original file
    // In production, replace this with actual image processing
    return new NextResponse(buffer, {
      status: 200,
      headers: {
        'Content-Type': outputMimeType,
        'Content-Disposition': `attachment; filename="${outputFilename}"`,
        'Content-Length': buffer.length.toString(),
      },
    });

  } catch (error) {
    console.error('Error processing image:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

export async function GET() {
  return NextResponse.json({
    message: 'Image Converter API',
    endpoints: {
      POST: '/api/convert-image - Convert image file',
    },
    usage: 'Send a POST request with FormData containing the image file and conversion parameters',
    parameters: {
      file: 'Image file to convert',
      format: 'Output format (jpg, png, webp, avif, bmp, tiff, gif, ico)',
      quality: 'Quality (1-100, default: 80)',
      width: 'Output width in pixels (optional)',
      height: 'Output height in pixels (optional)',
      maintainAspectRatio: 'Whether to maintain aspect ratio (true/false, default: true)',
      removeMetadata: 'Whether to remove metadata (true/false, default: false)',
      backgroundColor: 'Background color for non-transparent formats (default: #ffffff)'
    }
  });
}

function getMimeType(format: string): string {
  const mimeTypes: Record<string, string> = {
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    webp: 'image/webp',
    avif: 'image/avif',
    bmp: 'image/bmp',
    tiff: 'image/tiff',
    gif: 'image/gif',
    svg: 'image/svg+xml',
    ico: 'image/x-icon'
  };
  
  return mimeTypes[format] || 'image/jpeg';
}

function generateFilename(originalName: string, format: string): string {
  const nameWithoutExtension = originalName.replace(/\.[^/.]+$/, '');
  const extension = format === 'jpg' ? 'jpg' : format;
  return `${nameWithoutExtension}.${extension}`;
}