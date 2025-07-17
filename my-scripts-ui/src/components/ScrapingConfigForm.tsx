'use client';

import { useState } from 'react';
import { ScrapingConfig, CustomSelectors, ExtractOptions, LanguageFilter } from '@/types/web-scraper';
import { validateUrl } from '@/utils/web-scraper';

interface ScrapingConfigFormProps {
  onSubmit: (config: ScrapingConfig) => void;
  loading: boolean;
}

export default function ScrapingConfigForm({ onSubmit, loading }: ScrapingConfigFormProps) {
  const [config, setConfig] = useState<ScrapingConfig>({
    url: '',
    maxPages: 10,
    delay: 1000,
    concurrency: 3,
    outputFormat: 'markdown',
    useJavaScript: false,
    followLinks: true,
    customSelectors: {
      content: '',
      navigation: '',
      sidebar: '',
      exclude: []
    },
    extractOptions: {
      text: true,
      links: true,
      images: true,
      tables: true,
      metadata: true,
      removeMetadata: false,
      preserveFormatting: true
    },
    languageFilter: {
      enabled: false,
      selectedLanguages: [],
      autoDetect: true,
      skipUnsupportedLanguages: true
    }
  });

  const [urlError, setUrlError] = useState<string>('');
  const [customSelectorsText, setCustomSelectorsText] = useState<string>('');
  const [excludeSelectorsText, setExcludeSelectorsText] = useState<string>('');
  const [availableLanguages, setAvailableLanguages] = useState<{code: string, name: string}[]>([]);
  const [isDetectingLanguages, setIsDetectingLanguages] = useState(false);

  const handleUrlChange = (url: string) => {
    setConfig(prev => ({ ...prev, url }));
    
    if (url) {
      const validation = validateUrl(url);
      setUrlError(validation.isValid ? '' : validation.error || 'URL inválida');
    } else {
      setUrlError('');
    }
  };

  const handleCustomSelectorsChange = (text: string) => {
    setCustomSelectorsText(text);
    
    try {
      const selectors: any = {};
      if (text.trim()) {
        text.split(',').forEach(pair => {
          const [key, value] = pair.split('=').map(s => s.trim());
          if (key && value) {
            selectors[key] = value;
          }
        });
      }
      
      setConfig(prev => ({
        ...prev,
        customSelectors: { ...prev.customSelectors, ...selectors }
      }));
    } catch (error) {
      console.warn('Error parsing custom selectors:', error);
    }
  };

  const handleExcludeSelectorsChange = (text: string) => {
    setExcludeSelectorsText(text);
    
    const excludeList = text
      .split(',')
      .map(s => s.trim())
      .filter(s => s.length > 0);
    
    setConfig(prev => ({
      ...prev,
      customSelectors: {
        ...prev.customSelectors,
        exclude: excludeList
      }
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!config.url || urlError) {
      return;
    }
    
    onSubmit(config);
  };

  const isFormValid = config.url && !urlError && !loading;

  return (
    <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-8 border border-stone-200/60 dark:border-stone-800/60">
      <h2 className="text-2xl font-semibold text-stone-900 dark:text-stone-100 mb-6">
        ⚙️ Configuración de Web Scraping
      </h2>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* URL del sitio web */}
        <div>
          <label className="block text-sm font-semibold text-stone-900 dark:text-stone-100 mb-2">
            🌐 URL del sitio web *
          </label>
          <input
            type="url"
            value={config.url}
            onChange={(e) => handleUrlChange(e.target.value)}
            placeholder="https://docs.ejemplo.com"
            className={`w-full p-4 border rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 placeholder-stone-500 dark:placeholder-stone-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent ${
              urlError ? 'border-red-500' : 'border-stone-300 dark:border-stone-600'
            }`}
            required
          />
          {urlError && (
            <p className="text-red-600 text-sm mt-1">{urlError}</p>
          )}
        </div>

        {/* Configuración básica */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
              📄 Máximo de páginas
            </label>
            <input
              type="number"
              min="1"
              max="1000"
              value={config.maxPages || ''}
              onChange={(e) => setConfig(prev => ({ 
                ...prev, 
                maxPages: e.target.value ? parseInt(e.target.value) : undefined 
              }))}
              placeholder="Sin límite"
              className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
              ⏱️ Delay (ms)
            </label>
            <input
              type="number"
              min="0"
              max="10000"
              value={config.delay}
              onChange={(e) => setConfig(prev => ({ 
                ...prev, 
                delay: parseInt(e.target.value) || 0 
              }))}
              className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
              🔄 Concurrencia
            </label>
            <input
              type="number"
              min="1"
              max="10"
              value={config.concurrency}
              onChange={(e) => setConfig(prev => ({ 
                ...prev, 
                concurrency: parseInt(e.target.value) || 1 
              }))}
              className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
            />
          </div>
        </div>

        {/* Opciones generales */}
        <div>
          <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 mb-4">
            🔧 Opciones Generales
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="flex items-center space-x-3 p-3 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors duration-200">
              <input
                type="checkbox"
                checked={config.useJavaScript}
                onChange={(e) => setConfig(prev => ({ 
                  ...prev, 
                  useJavaScript: e.target.checked 
                }))}
                className="text-blue-600 rounded focus:ring-blue-500"
              />
              <div>
                <span className="text-stone-900 dark:text-stone-100 font-medium">Procesar JavaScript</span>
                <p className="text-sm text-stone-600 dark:text-stone-400">Para sitios con contenido dinámico</p>
              </div>
            </label>

            <label className="flex items-center space-x-3 p-3 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors duration-200">
              <input
                type="checkbox"
                checked={config.followLinks}
                onChange={(e) => setConfig(prev => ({ 
                  ...prev, 
                  followLinks: e.target.checked 
                }))}
                className="text-blue-600 rounded focus:ring-blue-500"
              />
              <div>
                <span className="text-stone-900 dark:text-stone-100 font-medium">Seguir enlaces</span>
                <p className="text-sm text-stone-600 dark:text-stone-400">Rastrear enlaces internos</p>
              </div>
            </label>

            <div>
              <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
                📝 Formato de salida
              </label>
              <select
                value={config.outputFormat}
                onChange={(e) => setConfig(prev => ({ 
                  ...prev, 
                  outputFormat: e.target.value as 'markdown' | 'mdx' 
                }))}
                className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
              >
                <option value="markdown">Markdown (.md)</option>
                <option value="mdx">MDX (.mdx)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Opciones de extracción */}
        <div>
          <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 mb-4">
            📋 Qué Extraer
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Object.entries({
              text: { label: 'Texto', icon: '📝' },
              links: { label: 'Enlaces', icon: '🔗' },
              images: { label: 'Imágenes', icon: '🖼️' },
              tables: { label: 'Tablas', icon: '📊' },
              metadata: { label: 'Metadatos', icon: '🏷️' },
              preserveFormatting: { label: 'Preservar formato', icon: '🎨' }
            }).map(([key, { label, icon }]) => (
              <label key={key} className="flex items-center space-x-2 p-2 rounded hover:bg-stone-50 dark:hover:bg-stone-800">
                <input
                  type="checkbox"
                  checked={config.extractOptions[key as keyof ExtractOptions]}
                  onChange={(e) => setConfig(prev => ({
                    ...prev,
                    extractOptions: {
                      ...prev.extractOptions,
                      [key]: e.target.checked
                    }
                  }))}
                  className="text-blue-600 rounded focus:ring-blue-500"
                />
                <span className="text-sm">{icon}</span>
                <span className="text-sm text-stone-700 dark:text-stone-300">{label}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Filtros de idioma */}
        <div>
          <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 mb-4">
            🌍 Filtros de Idioma
          </h3>
          <div className="space-y-4">
            <label className="flex items-center space-x-3 p-3 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors duration-200">
              <input
                type="checkbox"
                checked={config.languageFilter?.enabled || false}
                onChange={(e) => setConfig(prev => ({
                  ...prev,
                  languageFilter: {
                    ...prev.languageFilter!,
                    enabled: e.target.checked
                  }
                }))}
                className="text-blue-600 rounded focus:ring-blue-500"
              />
              <div>
                <span className="text-stone-900 dark:text-stone-100 font-medium">Activar filtro de idiomas</span>
                <p className="text-sm text-stone-600 dark:text-stone-400">Solo procesar páginas en idiomas específicos</p>
              </div>
            </label>

            {config.languageFilter?.enabled && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <label className="flex items-center space-x-3 p-3 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors duration-200">
                    <input
                      type="checkbox"
                      checked={config.languageFilter?.autoDetect || false}
                      onChange={(e) => setConfig(prev => ({
                        ...prev,
                        languageFilter: {
                          ...prev.languageFilter!,
                          autoDetect: e.target.checked
                        }
                      }))}
                      className="text-blue-600 rounded focus:ring-blue-500"
                    />
                    <div>
                      <span className="text-stone-900 dark:text-stone-100 font-medium">Detección automática</span>
                      <p className="text-sm text-stone-600 dark:text-stone-400">Detectar idiomas disponibles</p>
                    </div>
                  </label>

                  <label className="flex items-center space-x-3 p-3 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors duration-200">
                    <input
                      type="checkbox"
                      checked={config.languageFilter?.skipUnsupportedLanguages || false}
                      onChange={(e) => setConfig(prev => ({
                        ...prev,
                        languageFilter: {
                          ...prev.languageFilter!,
                          skipUnsupportedLanguages: e.target.checked
                        }
                      }))}
                      className="text-blue-600 rounded focus:ring-blue-500"
                    />
                    <div>
                      <span className="text-stone-900 dark:text-stone-100 font-medium">Omitir idiomas no soportados</span>
                      <p className="text-sm text-stone-600 dark:text-stone-400">Evitar procesar idiomas no seleccionados</p>
                    </div>
                  </label>
                </div>

                <div>
                  <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
                    Idiomas preferidos
                  </label>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {[
                      { code: 'es', name: 'Español' },
                      { code: 'en', name: 'English' },
                      { code: 'fr', name: 'Français' },
                      { code: 'de', name: 'Deutsch' },
                      { code: 'it', name: 'Italiano' },
                      { code: 'pt', name: 'Português' },
                      { code: 'zh', name: '中文' },
                      { code: 'ja', name: '日本語' },
                      { code: 'ko', name: '한국어' },
                      { code: 'ru', name: 'Русский' },
                      { code: 'ar', name: 'العربية' },
                      { code: 'hi', name: 'हिन्दी' }
                    ].map(lang => (
                      <label key={lang.code} className="flex items-center space-x-2 p-2 rounded hover:bg-stone-50 dark:hover:bg-stone-800">
                        <input
                          type="checkbox"
                          checked={config.languageFilter?.selectedLanguages.includes(lang.code) || false}
                          onChange={(e) => {
                            const currentLangs = config.languageFilter?.selectedLanguages || [];
                            const newLangs = e.target.checked
                              ? [...currentLangs, lang.code]
                              : currentLangs.filter(l => l !== lang.code);
                            
                            setConfig(prev => ({
                              ...prev,
                              languageFilter: {
                                ...prev.languageFilter!,
                                selectedLanguages: newLangs
                              }
                            }));
                          }}
                          className="text-blue-600 rounded focus:ring-blue-500"
                        />
                        <span className="text-sm text-stone-700 dark:text-stone-300">{lang.name}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {availableLanguages.length > 0 && (
                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                    <h4 className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-2">
                      Idiomas detectados en la página:
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {availableLanguages.map(lang => (
                        <span
                          key={lang.code}
                          className="bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 text-sm px-3 py-1 rounded-full"
                        >
                          {lang.name} ({lang.code})
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Selectores personalizados */}
        <div>
          <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 mb-4">
            🎯 Selectores Personalizados (Opcional)
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
                Selectores de contenido
              </label>
              <input
                type="text"
                value={customSelectorsText}
                onChange={(e) => handleCustomSelectorsChange(e.target.value)}
                placeholder="content=main, navigation=nav, sidebar=.sidebar"
                className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 placeholder-stone-500 dark:placeholder-stone-400"
              />
              <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">
                Formato: nombre=selector, separados por comas
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
                Elementos a excluir
              </label>
              <input
                type="text"
                value={excludeSelectorsText}
                onChange={(e) => handleExcludeSelectorsChange(e.target.value)}
                placeholder=".ads, .social, .comments"
                className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 placeholder-stone-500 dark:placeholder-stone-400"
              />
              <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">
                Selectores CSS separados por comas
              </p>
            </div>
          </div>
        </div>

        {/* Botón de submit */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!isFormValid}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-stone-400 disabled:cursor-not-allowed text-white px-8 py-3 rounded-lg font-semibold transition-colors duration-200 flex items-center space-x-2"
          >
            <span>{loading ? '🔄' : '🚀'}</span>
            <span>{loading ? 'Procesando...' : 'Iniciar Scraping'}</span>
          </button>
        </div>
      </form>
    </div>
  );
}