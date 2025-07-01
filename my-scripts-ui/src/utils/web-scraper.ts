import { ScrapingConfig, ScrapedPage, PageMetadata, TableData, ContentSection, UrlValidation } from '@/types/web-scraper';

// Validación de URL
export function validateUrl(url: string): UrlValidation {
  try {
    const parsed = new URL(url);
    
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return {
        isValid: false,
        error: 'Solo se admiten URLs HTTP y HTTPS'
      };
    }

    return {
      isValid: true,
      domain: parsed.hostname,
      protocol: parsed.protocol
    };
  } catch (error) {
    return {
      isValid: false,
      error: 'URL inválida'
    };
  }
}

// Limpiar y normalizar URL
export function normalizeUrl(url: string, baseUrl?: string): string {
  try {
    const fullUrl = baseUrl ? new URL(url, baseUrl).href : url;
    const parsed = new URL(fullUrl);
    
    // Remover fragmentos (#)
    parsed.hash = '';
    
    // Remover parámetros de tracking comunes
    const trackingParams = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'fbclid', 'gclid'];
    trackingParams.forEach(param => {
      parsed.searchParams.delete(param);
    });
    
    return parsed.href;
  } catch {
    return url;
  }
}

// Extraer dominio de URL
export function getDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return '';
  }
}

// Verificar si URL pertenece al mismo dominio
export function isSameDomain(url1: string, url2: string): boolean {
  return getDomain(url1) === getDomain(url2);
}

// Generar nombre de archivo desde URL
export function generateFilename(url: string, extension: string = '.md'): string {
  try {
    const parsed = new URL(url);
    let path = parsed.pathname;
    
    // Remover extension si existe
    path = path.replace(/\.[^/.]+$/, '');
    
    // Limpiar caracteres problemáticos
    let filename = path
      .replace(/^\/+|\/+$/g, '') // Remover slashes al inicio y final
      .replace(/\//g, '_') // Reemplazar slashes con underscore
      .replace(/[<>:"/\\|?*]/g, '_') // Reemplazar caracteres problemáticos
      .replace(/_{2,}/g, '_') // Reducir múltiples underscores
      .trim();
    
    // Si está vacío, usar 'index'
    if (!filename) {
      filename = 'index';
    }
    
    // Limitar longitud
    if (filename.length > 100) {
      filename = filename.substring(0, 100);
    }
    
    return filename + extension;
  } catch {
    return 'page' + extension;
  }
}

// Procesador mejorado de tablas
export class TableProcessor {
  static extractTableData(tableElement: Element): TableData | null {
    try {
      const headers: string[] = [];
      const rows: string[][] = [];
      let caption: string | undefined;

      // Extraer caption si existe
      const captionElement = tableElement.querySelector('caption');
      if (captionElement) {
        caption = this.cleanText(captionElement.textContent || '');
      }

      // Extraer headers
      const headerRows = tableElement.querySelectorAll('thead tr, tr:has(th)');
      if (headerRows.length > 0) {
        const firstHeaderRow = headerRows[0];
        const headerCells = firstHeaderRow.querySelectorAll('th, td');
        
        headerCells.forEach(cell => {
          headers.push(this.cleanText(cell.textContent || ''));
        });
      }

      // Si no hay headers explícitos, usar primera fila como headers
      if (headers.length === 0) {
        const firstRow = tableElement.querySelector('tr');
        if (firstRow) {
          const cells = firstRow.querySelectorAll('td, th');
          cells.forEach(cell => {
            headers.push(this.cleanText(cell.textContent || ''));
          });
        }
      }

      // Extraer filas de datos
      const dataRows = tableElement.querySelectorAll('tbody tr, tr:not(:has(th)):not(:first-child)');
      
      dataRows.forEach(row => {
        const rowData: string[] = [];
        const cells = row.querySelectorAll('td, th');
        
        cells.forEach(cell => {
          rowData.push(this.cleanText(cell.textContent || ''));
        });
        
        if (rowData.some(cell => cell.trim() !== '')) {
          rows.push(rowData);
        }
      });

      // Si no tenemos headers ni rows, intentar extraer todas las filas
      if (headers.length === 0 && rows.length === 0) {
        const allRows = tableElement.querySelectorAll('tr');
        
        allRows.forEach((row, index) => {
          const rowData: string[] = [];
          const cells = row.querySelectorAll('td, th');
          
          cells.forEach(cell => {
            rowData.push(this.cleanText(cell.textContent || ''));
          });
          
          if (rowData.some(cell => cell.trim() !== '')) {
            if (index === 0 && headers.length === 0) {
              headers.push(...rowData);
            } else {
              rows.push(rowData);
            }
          }
        });
      }

      if (headers.length === 0 && rows.length === 0) {
        return null;
      }

      return { headers, rows, caption };
    } catch (error) {
      console.error('Error extracting table data:', error);
      return null;
    }
  }

  static tableToMarkdown(tableData: TableData): string {
    if (!tableData.headers.length && !tableData.rows.length) {
      return '';
    }

    let markdown = '';

    // Añadir caption si existe
    if (tableData.caption) {
      markdown += `*${tableData.caption}*\n\n`;
    }

    // Si no hay headers, usar la primera fila como headers
    let headers = tableData.headers;
    let rows = tableData.rows;

    if (headers.length === 0 && rows.length > 0) {
      headers = rows[0];
      rows = rows.slice(1);
    }

    if (headers.length === 0) {
      return '';
    }

    // Asegurar que todas las filas tengan el mismo número de columnas
    const maxCols = Math.max(headers.length, ...rows.map(row => row.length));
    
    // Completar headers si es necesario
    while (headers.length < maxCols) {
      headers.push('');
    }

    // Construir tabla markdown
    markdown += '| ' + headers.map(h => this.escapeMarkdown(h || '')).join(' | ') + ' |\n';
    markdown += '| ' + headers.map(() => '---').join(' | ') + ' |\n';

    rows.forEach(row => {
      // Completar fila si es necesario
      const completeRow = [...row];
      while (completeRow.length < maxCols) {
        completeRow.push('');
      }

      markdown += '| ' + completeRow.map(cell => this.escapeMarkdown(cell || '')).join(' | ') + ' |\n';
    });

    return markdown + '\n';
  }

  private static cleanText(text: string): string {
    return text
      .replace(/\s+/g, ' ')
      .replace(/\n/g, ' ')
      .trim();
  }

  private static escapeMarkdown(text: string): string {
    return text
      .replace(/\|/g, '\\|')
      .replace(/\n/g, '<br>')
      .trim();
  }
}

// Procesador de contenido HTML
export class ContentProcessor {
  private config: ScrapingConfig;

  constructor(config: ScrapingConfig) {
    this.config = config;
  }

  processHTML(html: string, url: string): { content: string; metadata: PageMetadata; links: string[] } {
    // Como estamos en el cliente, usaremos DOMParser
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    // Extraer metadata
    const metadata = this.extractMetadata(doc, url);

    // Extraer enlaces si está habilitado
    const links = this.config.extractOptions.links ? this.extractLinks(doc, url) : [];

    // Procesar contenido principal
    const contentElement = this.findMainContent(doc);
    const content = this.processContent(contentElement);

    return { content, metadata, links };
  }

  private extractMetadata(doc: Document, url: string): PageMetadata {
    const metadata: PageMetadata = {
      title: '',
      description: '',
      keywords: [],
      author: '',
      scrapedAt: new Date().toISOString(),
      url,
      depth: 0
    };

    // Título
    const titleElement = doc.querySelector('title');
    if (titleElement) {
      metadata.title = titleElement.textContent?.trim() || '';
    }

    // Meta description
    const descElement = doc.querySelector('meta[name="description"], meta[property="og:description"]');
    if (descElement) {
      metadata.description = descElement.getAttribute('content') || '';
    }

    // Keywords
    const keywordsElement = doc.querySelector('meta[name="keywords"]');
    if (keywordsElement) {
      const keywords = keywordsElement.getAttribute('content') || '';
      metadata.keywords = keywords.split(',').map(k => k.trim()).filter(k => k);
    }

    // Author
    const authorElement = doc.querySelector('meta[name="author"]');
    if (authorElement) {
      metadata.author = authorElement.getAttribute('content') || '';
    }

    return metadata;
  }

  private extractLinks(doc: Document, baseUrl: string): string[] {
    const links: string[] = [];
    const linkElements = doc.querySelectorAll('a[href]');

    linkElements.forEach(link => {
      const href = link.getAttribute('href');
      if (href) {
        try {
          const absoluteUrl = new URL(href, baseUrl).href;
          const normalizedUrl = normalizeUrl(absoluteUrl);
          
          if (isSameDomain(normalizedUrl, baseUrl)) {
            links.push(normalizedUrl);
          }
        } catch {
          // Ignorar URLs inválidas
        }
      }
    });

    return [...new Set(links)]; // Remover duplicados
  }

  private findMainContent(doc: Document): Element {
    // Intentar encontrar el contenido principal usando selectores comunes
    const selectors = [
      this.config.customSelectors?.content,
      'main',
      'article',
      '.content',
      '.main-content',
      '.documentation',
      '.docs',
      '.doc-content',
      '#content',
      '#main',
      '.markdown-body',
      '[role="main"]',
      '.prose'
    ].filter(Boolean);

    for (const selector of selectors) {
      const element = doc.querySelector(selector as string);
      if (element) {
        return element;
      }
    }

    // Si no encuentra contenido específico, limpiar body
    const body = doc.body;
    if (body) {
      this.removeUnwantedElements(body);
      return body;
    }

    return doc.documentElement;
  }

  private removeUnwantedElements(element: Element) {
    const unwantedSelectors = [
      'script', 'style', 'noscript',
      'nav', 'header', 'footer', 'aside',
      '.navigation', '.nav', '.sidebar', '.menu',
      '.header', '.footer', '.ad', '.ads',
      '.advertisement', '.cookie-notice', '.banner',
      '.social', '.share', '.related', '.comments',
      ...(this.config.customSelectors?.exclude || [])
    ];

    unwantedSelectors.forEach(selector => {
      const elements = element.querySelectorAll(selector);
      elements.forEach(el => el.remove());
    });
  }

  private processContent(element: Element): string {
    let markdown = '';

    // Procesar elemento por elemento para mantener estructura
    const children = Array.from(element.children);

    children.forEach(child => {
      markdown += this.processElement(child);
    });

    // Limpiar markdown final
    return this.cleanMarkdown(markdown);
  }

  private processElement(element: Element): string {
    const tagName = element.tagName.toLowerCase();

    switch (tagName) {
      case 'h1':
      case 'h2':
      case 'h3':
      case 'h4':
      case 'h5':
      case 'h6':
        const level = parseInt(tagName[1]);
        const headerText = this.getTextContent(element);
        return '#'.repeat(level) + ' ' + headerText + '\n\n';

      case 'p':
        const pText = this.getTextContent(element);
        return pText ? pText + '\n\n' : '';

      case 'ul':
      case 'ol':
        return this.processList(element, tagName === 'ol') + '\n';

      case 'table':
        if (this.config.extractOptions.tables) {
          const tableData = TableProcessor.extractTableData(element);
          if (tableData) {
            return TableProcessor.tableToMarkdown(tableData) + '\n';
          }
        }
        return '';

      case 'pre':
        const codeText = this.getTextContent(element);
        return '```\n' + codeText + '\n```\n\n';

      case 'blockquote':
        const quoteText = this.getTextContent(element);
        const lines = quoteText.split('\n');
        return lines.map(line => '> ' + line).join('\n') + '\n\n';

      case 'img':
        if (this.config.extractOptions.images) {
          const src = element.getAttribute('src');
          const alt = element.getAttribute('alt') || '';
          if (src) {
            return `![${alt}](${src})\n\n`;
          }
        }
        return '';

      case 'a':
        const href = element.getAttribute('href');
        const linkText = this.getTextContent(element);
        if (href && linkText) {
          return `[${linkText}](${href})`;
        }
        return linkText;

      case 'strong':
      case 'b':
        const strongText = this.getTextContent(element);
        return `**${strongText}**`;

      case 'em':
      case 'i':
        const emText = this.getTextContent(element);
        return `*${emText}*`;

      case 'code':
        const inlineCode = this.getTextContent(element);
        return `\`${inlineCode}\``;

      case 'br':
        return '\n';

      case 'hr':
        return '\n---\n\n';

      default:
        // Para otros elementos, procesar recursivamente
        if (element.children.length > 0) {
          let content = '';
          Array.from(element.children).forEach(child => {
            content += this.processElement(child);
          });
          return content;
        } else {
          return this.getTextContent(element);
        }
    }
  }

  private processList(listElement: Element, isOrdered: boolean): string {
    let markdown = '';
    const items = listElement.querySelectorAll('li');

    items.forEach((item, index) => {
      const marker = isOrdered ? `${index + 1}.` : '-';
      const itemText = this.getTextContent(item);
      markdown += `${marker} ${itemText}\n`;
    });

    return markdown;
  }

  private getTextContent(element: Element): string {
    // Procesar contenido manteniendo formato interno
    let text = '';
    
    Array.from(element.childNodes).forEach(node => {
      if (node.nodeType === Node.TEXT_NODE) {
        text += node.textContent || '';
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        const el = node as Element;
        if (el.tagName.toLowerCase() === 'br') {
          text += '\n';
        } else if (['strong', 'b', 'em', 'i', 'code', 'a'].includes(el.tagName.toLowerCase())) {
          text += this.processElement(el);
        } else {
          text += el.textContent || '';
        }
      }
    });

    return text.replace(/\s+/g, ' ').trim();
  }

  private cleanMarkdown(markdown: string): string {
    return markdown
      // Remover líneas vacías excesivas
      .replace(/\n{4,}/g, '\n\n\n')
      // Limpiar espacios al final de líneas
      .replace(/ +$/gm, '')
      // Limpiar espacios en enlaces
      .replace(/\[\s+([^\]]+)\s+\]/g, '[$1]')
      .replace(/\]\s+\(/g, '](')
      .trim();
  }
}

// Utilidades de exportación
export function downloadMarkdown(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function createZipArchive(pages: ScrapedPage[]): Promise<Blob> {
  // Esta sería la implementación para crear un ZIP
  // Por ahora retornamos un placeholder
  return new Promise((resolve) => {
    const content = pages.map(page => 
      `File: ${page.filename}\n${'='.repeat(50)}\n${page.content}\n\n`
    ).join('\n');
    
    const blob = new Blob([content], { type: 'text/plain' });
    resolve(blob);
  });
}

export function addFrontmatter(content: string, metadata: PageMetadata): string {
  const frontmatter = [
    '---',
    `title: "${metadata.title.replace(/"/g, '\\"')}"`,
    metadata.description ? `description: "${metadata.description.replace(/"/g, '\\"')}"` : '',
    metadata.keywords.length > 0 ? `keywords: [${metadata.keywords.map(k => `"${k}"`).join(', ')}]` : '',
    metadata.author ? `author: "${metadata.author}"` : '',
    `url: "${metadata.url}"`,
    `scraped_at: "${metadata.scrapedAt}"`,
    '---',
    ''
  ].filter(line => line !== '').join('\n');

  return frontmatter + content;
}

export function formatFileSize(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = bytes;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }

  return `${size.toFixed(1)} ${units[unitIndex]}`;
}