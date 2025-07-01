export interface ScrapingConfig {
  url: string;
  maxPages?: number;
  delay: number;
  concurrency: number;
  outputFormat: 'markdown' | 'mdx';
  useJavaScript: boolean;
  followLinks: boolean;
  customSelectors?: CustomSelectors;
  extractOptions: ExtractOptions;
  languageFilter?: LanguageFilter;
}

export interface CustomSelectors {
  content?: string;
  navigation?: string;
  sidebar?: string;
  exclude?: string[];
}

export interface ExtractOptions {
  text: boolean;
  links: boolean;
  images: boolean;
  tables: boolean;
  metadata: boolean;
  removeMetadata: boolean;
  preserveFormatting: boolean;
}

export interface ScrapingProgress {
  current: number;
  total: number;
  percentage: number;
  currentUrl: string;
  status: 'discovering' | 'scraping' | 'processing' | 'completed' | 'error';
  discovered: number;
  processed: number;
  successful: number;
  failed: number;
  skipped: number;
}

export interface ScrapedPage {
  url: string;
  title: string;
  content: string;
  metadata: PageMetadata;
  links: string[];
  images: string[];
  status: 'pending' | 'processing' | 'completed' | 'error';
  error?: string;
  filename: string;
  size: number;
  processingTime?: number;
}

export interface PageMetadata {
  title: string;
  description?: string;
  keywords: string[];
  author?: string;
  scrapedAt: string;
  url: string;
  depth: number;
  language?: string;
  alternativeLanguages?: AlternativeLanguage[];
}

export interface ScrapingSession {
  id: string;
  config: ScrapingConfig;
  startTime: string;
  endTime?: string;
  status: 'running' | 'paused' | 'completed' | 'error';
  progress: ScrapingProgress;
  pages: ScrapedPage[];
  errors: string[];
}

export interface TableData {
  headers: string[];
  rows: string[][];
  caption?: string;
}

export interface ContentSection {
  type: 'heading' | 'paragraph' | 'list' | 'table' | 'code' | 'image';
  content: string;
  level?: number; // Para headings
  data?: TableData; // Para tablas
}

// Opciones de exportación
export type ExportFormat = 'zip' | 'individual' | 'single-file';

export interface ExportOptions {
  format: ExportFormat;
  includeImages: boolean;
  includeMetadata: boolean;
  filename?: string;
}

// Validación de URL
export interface UrlValidation {
  isValid: boolean;
  error?: string;
  domain?: string;
  protocol?: string;
}

// Estadísticas de scraping
export interface ScrapingStats {
  totalUrls: number;
  processedUrls: number;
  successfulUrls: number;
  failedUrls: number;
  skippedUrls: number;
  totalSize: number;
  averagePageSize: number;
  processingTime: number;
  averageTimePerPage: number;
}

// Configuración de filtros de idioma
export interface LanguageFilter {
  enabled: boolean;
  selectedLanguages: string[];
  autoDetect: boolean;
  skipUnsupportedLanguages: boolean;
}

// Idiomas alternativos detectados
export interface AlternativeLanguage {
  code: string;
  name: string;
  url: string;
  isActive?: boolean;
}

// Detección de idiomas en la página
export interface LanguageDetection {
  primaryLanguage?: string;
  alternativeLanguages: AlternativeLanguage[];
  hasMultipleLanguages: boolean;
  languageSelectors?: LanguageSelector[];
}

// Selectores de cambio de idioma
export interface LanguageSelector {
  type: 'dropdown' | 'links' | 'tabs';
  selector: string;
  languages: AlternativeLanguage[];
}