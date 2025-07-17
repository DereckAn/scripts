'use client';

import { useState, useCallback } from 'react';
import { ScrapingConfig, ScrapedPage, ScrapingSession, ExportOptions } from '@/types/web-scraper';
import { ContentProcessor, generateFilename, downloadMarkdown, createZipArchive, addFrontmatter } from '@/utils/web-scraper';
import ScrapingConfigForm from '@/components/ScrapingConfigForm';
import ScrapingProgress from '@/components/ScrapingProgress';
import ScrapedPageCard from '@/components/ScrapedPageCard';
import ContentPreviewModal from '@/components/ContentPreviewModal';

export default function WebScrapingPage() {
  const [session, setSession] = useState<ScrapingSession | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [selectedPage, setSelectedPage] = useState<ScrapedPage | null>(null);
  const [exportOptions, setExportOptions] = useState<ExportOptions>({
    format: 'individual',
    includeImages: true,
    includeMetadata: true
  });

  const createNewSession = useCallback((config: ScrapingConfig): ScrapingSession => {
    return {
      id: Date.now().toString(),
      config,
      startTime: new Date().toISOString(),
      status: 'running',
      progress: {
        current: 0,
        total: 0,
        percentage: 0,
        currentUrl: config.url,
        status: 'discovering',
        discovered: 0,
        processed: 0,
        successful: 0,
        failed: 0,
        skipped: 0
      },
      pages: [],
      errors: []
    };
  }, []);

  const handleStartScraping = useCallback(async (config: ScrapingConfig) => {
    setIsRunning(true);
    const newSession = createNewSession(config);
    setSession(newSession);

    try {
      // Simular proceso de scraping (en producción esto sería llamadas a la API)
      await simulateScrapingProcess(newSession, config);
    } catch (error) {
      console.error('Error during scraping:', error);
      setSession(prev => prev ? {
        ...prev,
        status: 'error',
        errors: [...prev.errors, error instanceof Error ? error.message : 'Error desconocido']
      } : null);
    } finally {
      setIsRunning(false);
    }
  }, [createNewSession]);

  // Simulación del proceso de scraping (reemplazar con lógica real)
  const simulateScrapingProcess = async (session: ScrapingSession, config: ScrapingConfig) => {
    const urls = [config.url]; // En producción, esto vendría del descubrimiento de enlaces
    const totalPages = Math.min(urls.length, config.maxPages || 10);

    // Actualizar progreso inicial
    setSession(prev => prev ? {
      ...prev,
      progress: {
        ...prev.progress,
        total: totalPages,
        discovered: totalPages,
        status: 'scraping'
      }
    } : null);

    for (let i = 0; i < totalPages; i++) {
      if (isPaused) {
        // Esperar mientras esté pausado
        while (isPaused) {
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      }

      const url = urls[i] || config.url;
      
      // Actualizar progreso actual
      setSession(prev => prev ? {
        ...prev,
        progress: {
          ...prev.progress,
          current: i + 1,
          percentage: Math.round(((i + 1) / totalPages) * 100),
          currentUrl: url,
          processed: i + 1
        }
      } : null);

      try {
        // Simular scraping de la página
        const scrapedPage = await simulatePageScraping(url, config);
        
        setSession(prev => prev ? {
          ...prev,
          pages: [...prev.pages, scrapedPage],
          progress: {
            ...prev.progress,
            successful: prev.progress.successful + 1
          }
        } : null);

      } catch (error) {
        const errorPage: ScrapedPage = {
          url,
          title: 'Error',
          content: '',
          metadata: {
            title: 'Error',
            description: '',
            keywords: [],
            scrapedAt: new Date().toISOString(),
            url,
            depth: 0
          },
          links: [],
          images: [],
          status: 'error',
          error: error instanceof Error ? error.message : 'Error desconocido',
          filename: generateFilename(url, config.outputFormat === 'mdx' ? '.mdx' : '.md'),
          size: 0
        };

        setSession(prev => prev ? {
          ...prev,
          pages: [...prev.pages, errorPage],
          progress: {
            ...prev.progress,
            failed: prev.progress.failed + 1
          },
          errors: [...prev.errors, `Error en ${url}: ${errorPage.error}`]
        } : null);
      }

      // Delay entre peticiones
      if (config.delay > 0) {
        await new Promise(resolve => setTimeout(resolve, config.delay));
      }
    }

    // Completar sesión
    setSession(prev => prev ? {
      ...prev,
      status: 'completed',
      endTime: new Date().toISOString(),
      progress: {
        ...prev.progress,
        status: 'completed'
      }
    } : null);
  };

  // Simulación del scraping de una página individual
  const simulatePageScraping = async (url: string, config: ScrapingConfig): Promise<ScrapedPage> => {
    const startTime = Date.now();

    // Simular fetch de la página
    const response = await fetch(`/api/scrape-page`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, config })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    const processingTime = (Date.now() - startTime) / 1000;

    return {
      url,
      title: data.title || 'Sin título',
      content: data.content || '',
      metadata: data.metadata || {
        title: data.title || 'Sin título',
        description: '',
        keywords: [],
        scrapedAt: new Date().toISOString(),
        url,
        depth: 0,
        language: data.languageDetection?.primaryLanguage,
        alternativeLanguages: data.languageDetection?.alternativeLanguages || []
      },
      links: data.links || [],
      images: data.images || [],
      status: 'completed',
      filename: generateFilename(url, config.outputFormat === 'mdx' ? '.mdx' : '.md'),
      size: (data.content || '').length,
      processingTime
    };
  };

  const handlePause = () => {
    setIsPaused(true);
  };

  const handleResume = () => {
    setIsPaused(false);
  };

  const handleStop = () => {
    setIsRunning(false);
    setIsPaused(false);
    setSession(prev => prev ? {
      ...prev,
      status: 'completed',
      endTime: new Date().toISOString()
    } : null);
  };

  const handlePreviewPage = (page: ScrapedPage) => {
    setSelectedPage(page);
  };

  const handleDownloadPage = (page: ScrapedPage) => {
    const content = exportOptions.includeMetadata 
      ? addFrontmatter(page.content, page.metadata)
      : page.content;
    downloadMarkdown(content, page.filename);
  };

  const handleDownloadAll = async () => {
    if (!session?.pages.length) return;

    const completedPages = session.pages.filter(p => p.status === 'completed');
    
    if (exportOptions.format === 'individual') {
      // Descargar archivos individuales
      completedPages.forEach(page => {
        const content = exportOptions.includeMetadata 
          ? addFrontmatter(page.content, page.metadata)
          : page.content;
        downloadMarkdown(content, page.filename);
      });
    } else if (exportOptions.format === 'zip') {
      // Crear y descargar ZIP
      const blob = await createZipArchive(completedPages);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `scraped-content-${Date.now()}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } else {
      // Archivo único
      const combinedContent = completedPages.map(page => {
        const content = exportOptions.includeMetadata 
          ? addFrontmatter(page.content, page.metadata)
          : page.content;
        return `# ${page.title}\n\n${content}`;
      }).join('\n\n---\n\n');
      
      downloadMarkdown(
        combinedContent, 
        `combined-content-${Date.now()}.${session.config.outputFormat === 'mdx' ? 'mdx' : 'md'}`
      );
    }
  };

  const handleRemovePage = (pageToRemove: ScrapedPage) => {
    setSession(prev => prev ? {
      ...prev,
      pages: prev.pages.filter(p => p.url !== pageToRemove.url)
    } : null);
  };

  const completedPages = session?.pages.filter(p => p.status === 'completed') || [];
  const errorPages = session?.pages.filter(p => p.status === 'error') || [];

  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-50 via-stone-100 to-stone-200 dark:from-stone-950 dark:via-stone-900 dark:to-stone-800">
      {/* Background Pattern */}
      <div className="absolute inset-0 bg-grid-stone-900/[0.04] dark:bg-grid-stone-100/[0.02]" />
      
      <div className="relative p-8 pt-20">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-12">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-r from-stone-900 to-stone-700 dark:from-stone-100 dark:to-stone-300 rounded-xl mb-8 shadow-lg">
            <span className="text-2xl">🕷️</span>
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-stone-900 dark:text-stone-100 mb-6">
            Web Scraping Avanzado
          </h1>
          <p className="text-lg text-stone-600 dark:text-stone-400 max-w-2xl mx-auto leading-relaxed">
            Extrae contenido de sitios web y conviértelo a Markdown/MDX con procesamiento inteligente de tablas
          </p>
        </div>

        <div className="space-y-8">
          {/* Formulario de configuración */}
          {!session && (
            <ScrapingConfigForm
              onSubmit={handleStartScraping}
              loading={isRunning}
            />
          )}

          {/* Progreso del scraping */}
          {session && (
            <ScrapingProgress
              progress={session.progress}
              onPause={handlePause}
              onResume={handleResume}
              onStop={handleStop}
              isPaused={isPaused}
            />
          )}

          {/* Opciones de exportación */}
          {session && completedPages.length > 0 && (
            <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 border border-stone-200/60 dark:border-stone-800/60">
              <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 mb-4">
                📦 Opciones de Exportación
              </h3>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div>
                  <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
                    Formato de exportación
                  </label>
                  <select
                    value={exportOptions.format}
                    onChange={(e) => setExportOptions(prev => ({ 
                      ...prev, 
                      format: e.target.value as ExportOptions['format'] 
                    }))}
                    className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
                  >
                    <option value="individual">Archivos individuales</option>
                    <option value="zip">Archivo ZIP</option>
                    <option value="single-file">Archivo único</option>
                  </select>
                </div>

                <div className="flex items-center space-x-4">
                  <label className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      checked={exportOptions.includeMetadata}
                      onChange={(e) => setExportOptions(prev => ({ 
                        ...prev, 
                        includeMetadata: e.target.checked 
                      }))}
                      className="text-blue-600 rounded focus:ring-blue-500"
                    />
                    <span className="text-sm text-stone-700 dark:text-stone-300">
                      Incluir metadatos
                    </span>
                  </label>

                  <label className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      checked={exportOptions.includeImages}
                      onChange={(e) => setExportOptions(prev => ({ 
                        ...prev, 
                        includeImages: e.target.checked 
                      }))}
                      className="text-blue-600 rounded focus:ring-blue-500"
                    />
                    <span className="text-sm text-stone-700 dark:text-stone-300">
                      Incluir imágenes
                    </span>
                  </label>
                </div>

                <div className="flex justify-end">
                  <button
                    onClick={handleDownloadAll}
                    className="bg-green-600 hover:bg-green-700 text-white px-6 py-3 rounded-lg font-semibold transition-colors duration-200 flex items-center space-x-2"
                  >
                    <span>💾</span>
                    <span>Descargar Todo ({completedPages.length})</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Resultados */}
          {session && session.pages.length > 0 && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-semibold text-stone-900 dark:text-stone-100">
                  📄 Páginas Procesadas ({session.pages.length})
                </h2>
                
                <div className="flex space-x-4 text-sm">
                  <span className="text-green-600 dark:text-green-400">
                    ✅ {completedPages.length} exitosas
                  </span>
                  <span className="text-red-600 dark:text-red-400">
                    ❌ {errorPages.length} fallidas
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {session.pages.map(page => (
                  <ScrapedPageCard
                    key={page.url}
                    page={page}
                    onPreview={handlePreviewPage}
                    onDownload={handleDownloadPage}
                    onRemove={handleRemovePage}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Estado vacío */}
          {!session && (
            <div className="text-center py-12">
              <div className="text-6xl mb-4">🕷️</div>
              <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 mb-2">
                ¡Comienza tu proyecto de scraping!
              </h3>
              <p className="text-stone-600 dark:text-stone-400">
                Configura los parámetros arriba para extraer contenido de sitios web
              </p>
            </div>
          )}

          {/* Características principales */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-2xl p-6 border border-blue-200 dark:border-blue-800">
            <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-100 mb-4">
              ✨ Características del Web Scraper
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm text-blue-800 dark:text-blue-200">
              <div>
                <h4 className="font-semibold mb-2">🔧 Procesamiento Avanzado:</h4>
                <ul className="space-y-1">
                  <li>• Extracción inteligente de contenido principal</li>
                  <li>• Procesamiento mejorado de tablas HTML</li>
                  <li>• Preservación de estructura y formato</li>
                  <li>• Conversión limpia a Markdown/MDX</li>
                  <li>• Soporte para selectores CSS personalizados</li>
                </ul>
              </div>
              
              <div>
                <h4 className="font-semibold mb-2">📊 Funcionalidades:</h4>
                <ul className="space-y-1">
                  <li>• Seguimiento automático de enlaces internos</li>
                  <li>• Extracción de metadatos y palabras clave</li>
                  <li>• Control de concurrencia y delays</li>
                  <li>• Soporte opcional para JavaScript</li>
                  <li>• Exportación en múltiples formatos</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        {/* Modal de vista previa */}
        <ContentPreviewModal
          page={selectedPage}
          onClose={() => setSelectedPage(null)}
        />
        </div>
      </div>
    </div>
  );
}