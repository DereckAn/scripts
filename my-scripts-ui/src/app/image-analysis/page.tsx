'use client';

import { useState, useCallback } from 'react';
import { ImageFile, ImageAnalysisResult, AIProviderConfig, AnalysisProgress, DEFAULT_ANALYSIS_PROMPT, AI_PROVIDER_PRESETS } from '@/types/image-analysis';
import { analyzeImageWithAI, getImageDimensions, downloadResultsAsCSV, downloadResultsAsJSON } from '@/utils/image-analysis';
import ImageAnalysisUploader from '@/components/ImageAnalysisUploader';
import AIProviderConfigComponent from '@/components/AIProviderConfig';

interface AnalysisResultsTableProps {
  results: ImageAnalysisResult[];
  onDownloadCSV: () => void;
  onDownloadJSON: () => void;
}

function AnalysisResultsTable({ results, onDownloadCSV, onDownloadJSON }: AnalysisResultsTableProps) {
  if (results.length === 0) {
    return null;
  }

  return (
    <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-xl shadow-lg border border-stone-200/60 dark:border-stone-800/60">
      <div className="p-6 border-b border-stone-200 dark:border-stone-800">
        <div className="flex items-center justify-between">
          <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100">
            📊 Resultados del Análisis ({results.length})
          </h3>
          <div className="flex space-x-3">
            <button
              onClick={onDownloadCSV}
              className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 flex items-center space-x-2"
            >
              <span>📄</span>
              <span>Descargar CSV</span>
            </button>
            <button
              onClick={onDownloadJSON}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 flex items-center space-x-2"
            >
              <span>📋</span>
              <span>Descargar JSON</span>
            </button>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-stone-50 dark:bg-stone-800">
            <tr>
              <th className="px-6 py-4 text-left text-xs font-medium text-stone-500 dark:text-stone-400 uppercase tracking-wider">
                Archivo
              </th>
              <th className="px-6 py-4 text-left text-xs font-medium text-stone-500 dark:text-stone-400 uppercase tracking-wider">
                Estado
              </th>
              <th className="px-6 py-4 text-left text-xs font-medium text-stone-500 dark:text-stone-400 uppercase tracking-wider">
                Análisis
              </th>
              <th className="px-6 py-4 text-left text-xs font-medium text-stone-500 dark:text-stone-400 uppercase tracking-wider">
                Tiempo
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-200 dark:divide-stone-700">
            {results.map((result) => (
              <tr key={result.id} className="hover:bg-stone-50 dark:hover:bg-stone-800/50">
                <td className="px-6 py-4">
                  <div className="flex flex-col">
                    <div className="text-sm font-medium text-stone-900 dark:text-stone-100">
                      {result.filename}
                    </div>
                    <div className="text-xs text-stone-500 dark:text-stone-400">
                      {result.dimensions.width}×{result.dimensions.height}px
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    result.status === 'completed' 
                      ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                      : result.status === 'error'
                      ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                      : result.status === 'analyzing'
                      ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                      : 'bg-stone-100 text-stone-800 dark:bg-stone-900 dark:text-stone-200'
                  }`}>
                    {result.status === 'completed' && '✅ Completado'}
                    {result.status === 'error' && '❌ Error'}
                    {result.status === 'analyzing' && '⏳ Analizando'}
                    {result.status === 'pending' && '⏸️ Pendiente'}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <div className="text-sm text-stone-900 dark:text-stone-100 max-w-md">
                    {result.error ? (
                      <span className="text-red-600 dark:text-red-400">{result.error}</span>
                    ) : result.analysis ? (
                      <details className="cursor-pointer">
                        <summary className="hover:text-purple-600 dark:hover:text-purple-400">
                          Ver análisis completo...
                        </summary>
                        <div className="mt-2 p-3 bg-stone-50 dark:bg-stone-800 rounded-lg text-xs whitespace-pre-wrap">
                          {result.analysis}
                        </div>
                      </details>
                    ) : (
                      <span className="text-stone-500 dark:text-stone-400">Sin análisis</span>
                    )}
                  </div>
                </td>
                <td className="px-6 py-4 text-sm text-stone-500 dark:text-stone-400">
                  {result.processingTime ? `${result.processingTime.toFixed(2)}s` : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function ImageAnalysisPage() {
  const [images, setImages] = useState<ImageFile[]>([]);
  const [results, setResults] = useState<ImageAnalysisResult[]>([]);
  const [aiConfig, setAIConfig] = useState<AIProviderConfig>(AI_PROVIDER_PRESETS[0].config);
  const [customPrompt, setCustomPrompt] = useState(DEFAULT_ANALYSIS_PROMPT);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [progress, setProgress] = useState<AnalysisProgress | null>(null);

  const handleImagesAdded = useCallback((newImages: ImageFile[]) => {
    setImages(prev => [...prev, ...newImages]);
  }, []);

  const handleRemoveImage = useCallback((imageId: string) => {
    setImages(prev => prev.filter(img => img.id !== imageId));
    setResults(prev => prev.filter(result => result.id !== imageId));
  }, []);

  const handleClearAll = useCallback(() => {
    setImages([]);
    setResults([]);
    setProgress(null);
  }, []);

  const handleAnalyzeImages = useCallback(async () => {
    if (images.length === 0) {
      alert('Por favor, sube al menos una imagen para analizar.');
      return;
    }

    setIsAnalyzing(true);
    setProgress({
      current: 0,
      total: images.length,
      percentage: 0,
      currentFile: '',
      status: 'preparing'
    });

    const newResults: ImageAnalysisResult[] = [];

    for (let i = 0; i < images.length; i++) {
      const image = images[i];
      
      setProgress(prev => prev ? {
        ...prev,
        current: i,
        currentFile: image.filename,
        percentage: (i / images.length) * 100,
        status: 'analyzing'
      } : null);

      try {
        const startTime = Date.now();
        
        // Obtener dimensiones de la imagen
        const dimensions = await getImageDimensions(image.file);
        
        // Crear resultado inicial
        const result: ImageAnalysisResult = {
          id: image.id,
          filename: image.filename,
          fileSize: image.fileSize,
          dimensions,
          analysis: '',
          timestamp: new Date().toISOString(),
          status: 'analyzing'
        };

        // Actualizar estado inmediatamente
        setResults(prev => {
          const filtered = prev.filter(r => r.id !== image.id);
          return [...filtered, result];
        });

        // Realizar análisis con IA
        const analysis = await analyzeImageWithAI(image, customPrompt, aiConfig);
        const endTime = Date.now();
        const processingTime = (endTime - startTime) / 1000;

        // Actualizar resultado completado
        const completedResult: ImageAnalysisResult = {
          ...result,
          analysis,
          processingTime,
          status: 'completed'
        };

        newResults.push(completedResult);

        setResults(prev => {
          const filtered = prev.filter(r => r.id !== image.id);
          return [...filtered, completedResult];
        });

      } catch (error) {
        console.error(`Error analyzing ${image.filename}:`, error);
        
        const errorResult: ImageAnalysisResult = {
          id: image.id,
          filename: image.filename,
          fileSize: image.fileSize,
          dimensions: { width: 0, height: 0 },
          analysis: '',
          timestamp: new Date().toISOString(),
          status: 'error',
          error: error instanceof Error ? error.message : 'Error desconocido'
        };

        newResults.push(errorResult);

        setResults(prev => {
          const filtered = prev.filter(r => r.id !== image.id);
          return [...filtered, errorResult];
        });
      }
    }

    setProgress(prev => prev ? {
      ...prev,
      current: images.length,
      percentage: 100,
      status: 'completed'
    } : null);

    setIsAnalyzing(false);
    
    setTimeout(() => {
      setProgress(null);
    }, 3000);
  }, [images, customPrompt, aiConfig]);

  const handleDownloadCSV = useCallback(() => {
    const completedResults = results.filter(r => r.status === 'completed');
    if (completedResults.length > 0) {
      downloadResultsAsCSV(completedResults);
    }
  }, [results]);

  const handleDownloadJSON = useCallback(() => {
    const completedResults = results.filter(r => r.status === 'completed');
    if (completedResults.length > 0) {
      downloadResultsAsJSON(completedResults);
    }
  }, [results]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-50 via-stone-100 to-stone-200 dark:from-stone-900 dark:via-stone-800 dark:to-stone-700">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-stone-900 dark:text-stone-100 mb-4">
            🤖 Análisis de Imágenes con IA Local
          </h1>
          <p className="text-lg text-stone-600 dark:text-stone-400 max-w-3xl mx-auto">
            Sube múltiples imágenes y analízalas con IA local sin censura. 
            Compatible con Ollama, LM Studio y endpoints personalizados.
          </p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
          {/* Left Column - Configuration */}
          <div className="space-y-6">
            {/* AI Provider Configuration */}
            <AIProviderConfigComponent 
              config={aiConfig} 
              onChange={setAIConfig} 
            />

            {/* Custom Prompt */}
            <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-xl shadow-lg p-6 border border-stone-200/60 dark:border-stone-800/60">
              <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 mb-4">
                ✏️ Prompt de Análisis
              </h3>
              <textarea
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                rows={12}
                className="w-full p-4 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 text-sm resize-y"
                placeholder="Personaliza el prompt para el análisis de imágenes..."
              />
              <div className="mt-3 flex justify-between items-center">
                <span className="text-xs text-stone-500 dark:text-stone-400">
                  {customPrompt.length} caracteres
                </span>
                <button
                  onClick={() => setCustomPrompt(DEFAULT_ANALYSIS_PROMPT)}
                  className="text-sm text-purple-600 dark:text-purple-400 hover:text-purple-800 dark:hover:text-purple-200"
                >
                  Restaurar prompt por defecto
                </button>
              </div>
            </div>
          </div>

          {/* Right Column - Upload and Images */}
          <div className="space-y-6">
            {/* Image Upload */}
            <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-xl shadow-lg p-6 border border-stone-200/60 dark:border-stone-800/60">
              <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 mb-4">
                📁 Subir Imágenes
              </h3>
              <ImageAnalysisUploader onImagesAdded={handleImagesAdded} />
            </div>

            {/* Uploaded Images */}
            {images.length > 0 && (
              <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-xl shadow-lg p-6 border border-stone-200/60 dark:border-stone-800/60">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                    🖼️ Imágenes Cargadas ({images.length})
                  </h3>
                  <div className="flex space-x-3">
                    <button
                      onClick={handleClearAll}
                      className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
                    >
                      Limpiar Todo
                    </button>
                    <button
                      onClick={handleAnalyzeImages}
                      disabled={isAnalyzing}
                      className="bg-purple-600 hover:bg-purple-700 disabled:bg-stone-400 text-white px-6 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center space-x-2"
                    >
                      {isAnalyzing ? (
                        <>
                          <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
                          <span>Analizando...</span>
                        </>
                      ) : (
                        <>
                          <span>🔍</span>
                          <span>Analizar Imágenes</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Progress Bar */}
                {progress && (
                  <div className="mb-4 p-4 bg-stone-50 dark:bg-stone-800 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-stone-900 dark:text-stone-100">
                        {progress.status === 'analyzing' ? `Analizando: ${progress.currentFile}` : 
                         progress.status === 'completed' ? '✅ Análisis completado' : 
                         'Preparando análisis...'}
                      </span>
                      <span className="text-sm text-stone-600 dark:text-stone-400">
                        {progress.current}/{progress.total} ({progress.percentage.toFixed(0)}%)
                      </span>
                    </div>
                    <div className="w-full bg-stone-200 dark:bg-stone-700 rounded-full h-2">
                      <div 
                        className="bg-purple-600 h-2 rounded-full transition-all duration-300"
                        style={{ width: `${progress.percentage}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Image Grid */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {images.map((image) => {
                    const result = results.find(r => r.id === image.id);
                    return (
                      <div key={image.id} className="relative group">
                        <div className="aspect-square bg-stone-200 dark:bg-stone-700 rounded-lg overflow-hidden">
                          <img
                            src={image.preview}
                            alt={image.filename}
                            className="w-full h-full object-cover"
                          />
                        </div>
                        
                        {/* Status Overlay */}
                        <div className="absolute top-2 left-2">
                          {result?.status === 'completed' && (
                            <div className="bg-green-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs">
                              ✓
                            </div>
                          )}
                          {result?.status === 'error' && (
                            <div className="bg-red-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs">
                              ✗
                            </div>
                          )}
                          {result?.status === 'analyzing' && (
                            <div className="bg-yellow-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs">
                              <div className="animate-spin w-3 h-3 border border-white border-t-transparent rounded-full"></div>
                            </div>
                          )}
                        </div>

                        {/* Remove Button */}
                        <button
                          onClick={() => handleRemoveImage(image.id)}
                          className="absolute top-2 right-2 bg-red-500 hover:bg-red-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                        >
                          ×
                        </button>

                        {/* Filename */}
                        <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-75 text-white text-xs p-2 rounded-b-lg">
                          {image.filename}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Results Table */}
        <div className="mt-8">
          <AnalysisResultsTable
            results={results}
            onDownloadCSV={handleDownloadCSV}
            onDownloadJSON={handleDownloadJSON}
          />
        </div>
      </div>
    </div>
  );
}