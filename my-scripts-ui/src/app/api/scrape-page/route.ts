import { NextRequest, NextResponse } from 'next/server';
import { ScrapingConfig, LanguageDetection, AlternativeLanguage } from '@/types/web-scraper';

export async function POST(request: NextRequest) {
  try {
    const { url, config }: { url: string; config: ScrapingConfig } = await request.json();

    if (!url) {
      return NextResponse.json(
        { error: 'URL is required' },
        { status: 400 }
      );
    }

    // Validar URL
    try {
      new URL(url);
    } catch {
      return NextResponse.json(
        { error: 'Invalid URL format' },
        { status: 400 }
      );
    }

    // Headers para simular un navegador real
    const headers = {
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.5',
      'Accept-Encoding': 'gzip, deflate, br',
      'DNT': '1',
      'Connection': 'keep-alive',
      'Upgrade-Insecure-Requests': '1',
    };

    // Fetch de la página
    const response = await fetch(url, {
      headers,
      // Timeout de 30 segundos
      signal: AbortSignal.timeout(30000)
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `HTTP ${response.status}: ${response.statusText}` },
        { status: response.status }
      );
    }

    const html = await response.text();
    
    // Procesar el HTML para extraer contenido
    const processedContent = await processHTML(html, url, config);

    return NextResponse.json(processedContent);

  } catch (error) {
    console.error('Error in scrape-page API:', error);
    
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        return NextResponse.json(
          { error: 'Request timeout - the page took too long to load' },
          { status: 408 }
        );
      }
      
      return NextResponse.json(
        { error: error.message },
        { status: 500 }
      );
    }

    return NextResponse.json(
      { error: 'Unknown error occurred' },
      { status: 500 }
    );
  }
}

async function processHTML(html: string, url: string, config: ScrapingConfig) {
  // Aquí procesaríamos el HTML usando una librería como Cheerio en el servidor
  // Por ahora, simularemos el procesamiento con el HTML raw
  
  // Extraer metadatos básicos
  const titleMatch = html.match(/<title>(.*?)<\/title>/i);
  const title = titleMatch ? titleMatch[1].trim() : 'Sin título';

  const descMatch = html.match(/<meta\s+name="description"\s+content="([^"]*)"[^>]*>/i);
  const description = descMatch ? descMatch[1] : '';

  const keywordsMatch = html.match(/<meta\s+name="keywords"\s+content="([^"]*)"[^>]*>/i);
  const keywords = keywordsMatch ? keywordsMatch[1].split(',').map(k => k.trim()) : [];

  const authorMatch = html.match(/<meta\s+name="author"\s+content="([^"]*)"[^>]*>/i);
  const author = authorMatch ? authorMatch[1] : '';

  // Detectar idiomas
  const languageDetection = detectLanguages(html, url);
  
  // Filtrar por idioma si está configurado
  if (config.languageFilter?.enabled && shouldSkipPage(languageDetection, config)) {
    throw new Error(`Página omitida: idioma no seleccionado (${languageDetection.primaryLanguage || 'desconocido'})`);
  }

  // Extraer enlaces (simplificado)
  const linkRegex = /<a\s+[^>]*href="([^"]*)"[^>]*>/gi;
  const links: string[] = [];
  let linkMatch;
  while ((linkMatch = linkRegex.exec(html)) !== null) {
    const href = linkMatch[1];
    if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
      try {
        const absoluteUrl = new URL(href, url).href;
        const urlObj = new URL(absoluteUrl);
        const baseUrlObj = new URL(url);
        
        // Solo incluir enlaces del mismo dominio
        if (urlObj.hostname === baseUrlObj.hostname) {
          links.push(absoluteUrl);
        }
      } catch {
        // Ignorar URLs inválidas
      }
    }
  }

  // Extraer imágenes (simplificado)
  const imageRegex = /<img\s+[^>]*src="([^"]*)"[^>]*>/gi;
  const images: string[] = [];
  let imageMatch;
  while ((imageMatch = imageRegex.exec(html)) !== null) {
    const src = imageMatch[1];
    if (src) {
      try {
        const absoluteUrl = new URL(src, url).href;
        images.push(absoluteUrl);
      } catch {
        // Ignorar URLs inválidas
      }
    }
  }

  // Procesamiento básico del contenido
  // En una implementación real, usaríamos librerías como Cheerio o Playwright
  let content = html;
  
  // Remover scripts, styles, etc.
  content = content.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
  content = content.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
  content = content.replace(/<noscript[^>]*>[\s\S]*?<\/noscript>/gi, '');
  
  // Procesamiento mejorado de tablas
  content = processTablesInHTML(content);
  
  // Conversión básica a markdown (simplificada)
  content = convertToMarkdown(content);

  // Limpiar el contenido
  content = cleanMarkdown(content);

  const metadata = {
    title,
    description,
    keywords,
    author,
    scrapedAt: new Date().toISOString(),
    url,
    depth: 0,
    language: languageDetection.primaryLanguage,
    alternativeLanguages: languageDetection.alternativeLanguages
  };

  return {
    title,
    content,
    metadata,
    links: [...new Set(links)], // Remover duplicados
    images: [...new Set(images)], // Remover duplicados
    languageDetection
  };
}

function processTablesInHTML(html: string): string {
  // Procesamiento mejorado específicamente para tablas
  return html.replace(/<table[^>]*>([\s\S]*?)<\/table>/gi, (match, tableContent) => {
    // Extraer caption si existe
    const captionMatch = tableContent.match(/<caption[^>]*>(.*?)<\/caption>/i);
    const caption = captionMatch ? captionMatch[1].trim() : '';

    // Extraer headers
    const headerRowMatch = tableContent.match(/<thead[^>]*>([\s\S]*?)<\/thead>/i) ||
                          tableContent.match(/<tr[^>]*>\s*<th[^>]*>[\s\S]*?<\/tr>/i);
    
    let headers: string[] = [];
    if (headerRowMatch) {
      const headerContent = headerRowMatch[1] || headerRowMatch[0];
      const thMatches = headerContent.match(/<th[^>]*>([\s\S]*?)<\/th>/gi) ||
                       headerContent.match(/<td[^>]*>([\s\S]*?)<\/td>/gi);
      
      if (thMatches) {
        headers = thMatches.map((th:any) => 
          th.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim()
        );
      }
    }

    // Extraer filas de datos
    const dataRows: string[][] = [];
    const tbodyMatch = tableContent.match(/<tbody[^>]*>([\s\S]*?)<\/tbody>/i);
    const rowsContent = tbodyMatch ? tbodyMatch[1] : tableContent;
    
    const rowMatches = rowsContent.match(/<tr[^>]*>[\s\S]*?<\/tr>/gi);
    if (rowMatches) {
      rowMatches.forEach((row:any) => {
        // Skip if it's a header row
        if (row.includes('<th')) return;
        
        const cellMatches = row.match(/<td[^>]*>([\s\S]*?)<\/td>/gi);
        if (cellMatches) {
          const rowData = cellMatches.map((cell:any) => 
            cell.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim()
          );
          if (rowData.some((cell:any) => cell.length > 0)) {
            dataRows.push(rowData);
          }
        }
      });
    }

    // Si no hay headers explícitos pero hay datos, usar primera fila como headers
    if (headers.length === 0 && dataRows.length > 0) {
      headers = dataRows[0];
      dataRows.shift();
    }

    // Generar markdown de la tabla
    if (headers.length > 0) {
      let tableMarkdown = '';
      
      if (caption) {
        tableMarkdown += `*${caption}*\n\n`;
      }

      // Headers
      tableMarkdown += '| ' + headers.map(h => h.replace(/\|/g, '\\|')).join(' | ') + ' |\n';
      tableMarkdown += '| ' + headers.map(() => '---').join(' | ') + ' |\n';

      // Rows
      dataRows.forEach(row => {
        // Asegurar que la fila tenga el mismo número de columnas
        while (row.length < headers.length) {
          row.push('');
        }
        tableMarkdown += '| ' + row.map(cell => (cell || '').replace(/\|/g, '\\|')).join(' | ') + ' |\n';
      });

      return `\n\n${tableMarkdown}\n\n`;
    }

    return match; // Si no se puede procesar, devolver la tabla original
  });
}

function convertToMarkdown(html: string): string {
  let markdown = html;
  
  // Conversiones básicas HTML a Markdown
  // Headings
  markdown = markdown.replace(/<h1[^>]*>(.*?)<\/h1>/gi, '\n# $1\n\n');
  markdown = markdown.replace(/<h2[^>]*>(.*?)<\/h2>/gi, '\n## $1\n\n');
  markdown = markdown.replace(/<h3[^>]*>(.*?)<\/h3>/gi, '\n### $1\n\n');
  markdown = markdown.replace(/<h4[^>]*>(.*?)<\/h4>/gi, '\n#### $1\n\n');
  markdown = markdown.replace(/<h5[^>]*>(.*?)<\/h5>/gi, '\n##### $1\n\n');
  markdown = markdown.replace(/<h6[^>]*>(.*?)<\/h6>/gi, '\n###### $1\n\n');
  
  // Párrafos
  markdown = markdown.replace(/<p[^>]*>(.*?)<\/p>/gi, '\n$1\n\n');
  
  // Strong/Bold
  markdown = markdown.replace(/<(strong|b)[^>]*>(.*?)<\/\1>/gi, '**$2**');
  
  // Emphasis/Italic
  markdown = markdown.replace(/<(em|i)[^>]*>(.*?)<\/\1>/gi, '*$2*');
  
  // Code
  markdown = markdown.replace(/<code[^>]*>(.*?)<\/code>/gi, '`$1`');
  
  // Pre
  markdown = markdown.replace(/<pre[^>]*>(.*?)<\/pre>/gi, '\n```\n$1\n```\n\n');
  
  // Links
  markdown = markdown.replace(/<a[^>]*href="([^"]*)"[^>]*>(.*?)<\/a>/gi, '[$2]($1)');
  
  // Images
  markdown = markdown.replace(/<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*>/gi, '![$2]($1)');
  markdown = markdown.replace(/<img[^>]*src="([^"]*)"[^>]*>/gi, '![]($1)');
  
  // Lists
  markdown = markdown.replace(/<ul[^>]*>([\s\S]*?)<\/ul>/gi, (match, content) => {
    const items = content.match(/<li[^>]*>(.*?)<\/li>/gi);
    if (items) {
      return '\n' + items.map((item: string) => 
        '- ' + item.replace(/<li[^>]*>(.*?)<\/li>/i, '$1').trim()
      ).join('\n') + '\n\n';
    }
    return match;
  });
  
  markdown = markdown.replace(/<ol[^>]*>([\s\S]*?)<\/ol>/gi, (match, content) => {
    const items = content.match(/<li[^>]*>(.*?)<\/li>/gi);
    if (items) {
      return '\n' + items.map((item: string, index: number) => 
        `${index + 1}. ` + item.replace(/<li[^>]*>(.*?)<\/li>/i, '$1').trim()
      ).join('\n') + '\n\n';
    }
    return match;
  });
  
  // Blockquotes
  markdown = markdown.replace(/<blockquote[^>]*>(.*?)<\/blockquote>/gi, '\n> $1\n\n');
  
  // Line breaks
  markdown = markdown.replace(/<br[^>]*>/gi, '\n');
  markdown = markdown.replace(/<hr[^>]*>/gi, '\n---\n\n');
  
  // Remover tags HTML restantes
  markdown = markdown.replace(/<[^>]*>/g, '');
  
  return markdown;
}

function cleanMarkdown(content: string): string {
  return content
    // Decodificar entidades HTML
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    
    // Limpiar espacios en blanco excesivos
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/[ \t]+\n/g, '\n')
    
    // Limpiar líneas vacías al principio y final
    .trim();
}

function detectLanguages(html: string, url: string): LanguageDetection {
  const alternativeLanguages: AlternativeLanguage[] = [];
  
  // Detectar idioma principal del HTML
  const htmlLangMatch = html.match(/<html[^>]*lang=["']([^"']*)["'][^>]*>/i);
  const primaryLanguage = htmlLangMatch ? htmlLangMatch[1].split('-')[0] : undefined;
  
  // Detectar enlaces de idiomas alternativos
  const langLinkRegex = /<link[^>]*rel=["']alternate["'][^>]*hreflang=["']([^"']*)["'][^>]*href=["']([^"']*)["'][^>]*>/gi;
  let langMatch;
  while ((langMatch = langLinkRegex.exec(html)) !== null) {
    const langCode = langMatch[1].split('-')[0];
    const langUrl = langMatch[2];
    
    if (langCode && langUrl) {
      try {
        const absoluteUrl = new URL(langUrl, url).href;
        alternativeLanguages.push({
          code: langCode,
          name: getLanguageName(langCode),
          url: absoluteUrl
        });
      } catch {
        // Ignorar URLs inválidas
      }
    }
  }
  
  // Buscar selectores de idioma en la página
  const languageSelectorsRegex = /<[^>]*(?:class|id)=["'][^"']*(?:lang|language)[^"']*["'][^>]*>/gi;
  const languageSelectors: any[] = [];
  
  // Detectar enlaces de cambio de idioma comunes
  const langToggleRegex = /<a[^>]*href=["']([^"']*)["'][^>]*>\s*(?:<[^>]*>\s*)?([a-z]{2}(?:-[a-z]{2})?)\s*(?:<\/[^>]*>\s*)?<\/a>/gi;
  let toggleMatch;
  while ((toggleMatch = langToggleRegex.exec(html)) !== null) {
    const href = toggleMatch[1];
    const langText = toggleMatch[2];
    
    if (href && langText) {
      try {
        const absoluteUrl = new URL(href, url).href;
        const langCode = langText.toLowerCase().split('-')[0];
        
        // Evitar duplicados
        if (!alternativeLanguages.some(alt => alt.code === langCode)) {
          alternativeLanguages.push({
            code: langCode,
            name: getLanguageName(langCode),
            url: absoluteUrl
          });
        }
      } catch {
        // Ignorar URLs inválidas
      }
    }
  }
  
  return {
    primaryLanguage,
    alternativeLanguages,
    hasMultipleLanguages: alternativeLanguages.length > 0,
    languageSelectors
  };
}

function getLanguageName(code: string): string {
  const languages: Record<string, string> = {
    'es': 'Español',
    'en': 'English',
    'fr': 'Français',
    'de': 'Deutsch',
    'it': 'Italiano',
    'pt': 'Português',
    'zh': '中文',
    'ja': '日本語',
    'ko': '한국어',
    'ru': 'Русский',
    'ar': 'العربية',
    'hi': 'हिन्दी',
    'nl': 'Nederlands',
    'sv': 'Svenska',
    'no': 'Norsk',
    'da': 'Dansk',
    'fi': 'Suomi',
    'pl': 'Polski',
    'tr': 'Türkçe',
    'el': 'Ελληνικά',
    'he': 'עברית',
    'th': 'ไทย',
    'vi': 'Tiếng Việt',
    'id': 'Bahasa Indonesia',
    'ms': 'Bahasa Melayu',
    'tl': 'Filipino',
    'uk': 'Українська',
    'cs': 'Čeština',
    'sk': 'Slovenčina',
    'hu': 'Magyar',
    'ro': 'Română',
    'bg': 'Български',
    'hr': 'Hrvatski',
    'sr': 'Српски',
    'sl': 'Slovenščina',
    'et': 'Eesti',
    'lv': 'Latviešu',
    'lt': 'Lietuvių',
    'mt': 'Malti',
    'cy': 'Cymraeg',
    'ga': 'Gaeilge',
    'is': 'Íslenska',
    'mk': 'Македонски',
    'sq': 'Shqip',
    'eu': 'Euskera',
    'ca': 'Català',
    'gl': 'Galego'
  };
  
  return languages[code.toLowerCase()] || code.toUpperCase();
}

function shouldSkipPage(languageDetection: LanguageDetection, config: ScrapingConfig): boolean {
  if (!config.languageFilter?.enabled || !config.languageFilter.selectedLanguages.length) {
    return false;
  }
  
  const selectedLangs = config.languageFilter.selectedLanguages;
  
  // Verificar idioma principal
  if (languageDetection.primaryLanguage && selectedLangs.includes(languageDetection.primaryLanguage)) {
    return false;
  }
  
  // Verificar idiomas alternativos
  const hasSelectedAlternative = languageDetection.alternativeLanguages.some(
    alt => selectedLangs.includes(alt.code)
  );
  
  if (hasSelectedAlternative) {
    return false;
  }
  
  // Si está configurado para omitir idiomas no soportados
  return config.languageFilter.skipUnsupportedLanguages;
}

export async function GET() {
  return NextResponse.json({
    message: 'Web Scraping API',
    endpoints: {
      POST: '/api/scrape-page - Scrape a single page',
    },
    usage: 'Send a POST request with { url: string, config: ScrapingConfig }',
    features: [
      'Content extraction with CSS selectors',
      'Enhanced table processing',
      'Language detection and filtering',
      'Metadata extraction',
      'Link and image discovery',
      'Markdown conversion',
      'Error handling and timeouts'
    ]
  });
}