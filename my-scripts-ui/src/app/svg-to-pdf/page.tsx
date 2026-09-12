'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, FileArchive, FileDown, Loader2 } from 'lucide-react';
import SvgPageList from '@/components/SvgPageList';
import SvgUploader from '@/components/SvgUploader';
import {
  PAGE_SIZE_OPTIONS,
  PageSizeMode,
  PdfProgress,
  PdfSettings,
  SvgFile,
} from '@/types/svg-to-pdf';
import {
  buildIndividualPdfs,
  buildMergedPdf,
  createPdfZip,
  downloadBlob,
  formatFileSize,
  moveSvgFile,
  sanitizeFileName,
  sortSvgFilesByName,
} from '@/utils/svg-to-pdf';

export default function SvgToPdfPage() {
  const [files, setFiles] = useState<SvgFile[]>([]);
  const [settings, setSettings] = useState<PdfSettings>({
    pageSize: 'a4',
    margin: 10,
    fileName: 'partitura',
  });
  const [isWorking, setIsWorking] = useState(false);
  const [progress, setProgress] = useState<PdfProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Blob URLs for the thumbnails must outlive renders but be released on unmount.
  const filesRef = useRef<SvgFile[]>([]);
  filesRef.current = files;
  useEffect(() => {
    return () => {
      filesRef.current.forEach((file) => URL.revokeObjectURL(file.preview));
    };
  }, []);

  const handleFilesAdded = useCallback((newFiles: SvgFile[]) => {
    // Keep the whole list sorted so the page order matches the file names.
    setFiles((prev) => sortSvgFilesByName([...prev, ...newFiles]));
    setError(null);
  }, []);

  const handleReorder = useCallback((from: number, to: number) => {
    setFiles((prev) => moveSvgFile(prev, from, to));
  }, []);

  const handleRemove = useCallback((id: string) => {
    setFiles((prev) => {
      const target = prev.find((file) => file.id === id);
      if (target) URL.revokeObjectURL(target.preview);
      return prev.filter((file) => file.id !== id);
    });
  }, []);

  const handleClear = useCallback(() => {
    setFiles((prev) => {
      prev.forEach((file) => URL.revokeObjectURL(file.preview));
      return [];
    });
  }, []);

  const handleSortByName = useCallback(() => {
    setFiles((prev) => sortSvgFilesByName(prev));
  }, []);

  const runJob = useCallback(
    async (job: (onProgress: (value: PdfProgress) => void) => Promise<void>) => {
      if (files.length === 0 || isWorking) return;

      setIsWorking(true);
      setError(null);
      try {
        await job(setProgress);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'No se pudo generar el PDF');
      } finally {
        setIsWorking(false);
        setTimeout(() => setProgress(null), 1500);
      }
    },
    [files.length, isWorking]
  );

  const handleMerge = useCallback(() => {
    return runJob(async (onProgress) => {
      const blob = await buildMergedPdf(files, settings, onProgress);
      downloadBlob(blob, `${sanitizeFileName(settings.fileName)}.pdf`);
    });
  }, [files, runJob, settings]);

  const handleIndividual = useCallback(() => {
    return runJob(async (onProgress) => {
      const pdfs = await buildIndividualPdfs(files, settings, onProgress);
      const zip = await createPdfZip(pdfs);
      downloadBlob(zip, `${sanitizeFileName(settings.fileName)}-paginas.zip`);
    });
  }, [files, runJob, settings]);

  const totalSize = files.reduce((sum, file) => sum + file.size, 0);

  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-50 via-stone-100 to-stone-200 dark:from-stone-950 dark:via-stone-900 dark:to-stone-800">
      <div className="absolute inset-0 bg-grid-stone-900/[0.04] dark:bg-grid-stone-100/[0.02]" />

      <div className="relative p-8 pt-20">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-r from-stone-900 to-stone-700 dark:from-stone-100 dark:to-stone-300 rounded-xl mb-8 shadow-lg">
              <span className="text-2xl">🎼</span>
            </div>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-stone-900 dark:text-stone-100 mb-6">
              Partituras SVG a PDF
            </h1>
            <p className="text-lg text-stone-600 dark:text-stone-400 max-w-2xl mx-auto leading-relaxed">
              Sube tus partituras en SVG, se ordenan solas por nombre y las unes en un único PDF
              vectorial listo para imprimir.
            </p>
          </div>

          <div className="space-y-8">
            <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-8 border border-stone-200/60 dark:border-stone-800/60">
              <SvgUploader onFilesAdded={handleFilesAdded} />
            </div>

            {files.length > 0 && (
              <>
                <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-8 border border-stone-200/60 dark:border-stone-800/60">
                  <SvgPageList
                    files={files}
                    onReorder={handleReorder}
                    onRemove={handleRemove}
                    onSortByName={handleSortByName}
                    onClear={handleClear}
                  />
                </div>

                <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-8 border border-stone-200/60 dark:border-stone-800/60 space-y-6">
                  <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                    Opciones del PDF
                  </h3>

                  <div>
                    <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-3">
                      Tamaño de página
                    </label>
                    <div className="grid gap-3 sm:grid-cols-3">
                      {PAGE_SIZE_OPTIONS.map((option) => (
                        <button
                          key={option.value}
                          onClick={() =>
                            setSettings((prev) => ({
                              ...prev,
                              pageSize: option.value as PageSizeMode,
                            }))
                          }
                          className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                            settings.pageSize === option.value
                              ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30 ring-2 ring-indigo-500/20'
                              : 'border-stone-200 dark:border-stone-700 hover:border-stone-300 dark:hover:border-stone-600'
                          }`}
                        >
                          <span className="block font-medium text-stone-900 dark:text-stone-100">
                            {option.label}
                          </span>
                          <span className="block text-sm text-stone-500 dark:text-stone-400 mt-1">
                            {option.description}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid gap-6 sm:grid-cols-2">
                    <div>
                      <label
                        htmlFor="pdf-name"
                        className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2"
                      >
                        Nombre del archivo
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          id="pdf-name"
                          type="text"
                          value={settings.fileName}
                          onChange={(e) =>
                            setSettings((prev) => ({ ...prev, fileName: e.target.value }))
                          }
                          className="flex-1 px-4 py-2 rounded-lg border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                        />
                        <span className="text-stone-500 dark:text-stone-400">.pdf</span>
                      </div>
                    </div>

                    <div>
                      <label
                        htmlFor="pdf-margin"
                        className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2"
                      >
                        Margen: {settings.margin} mm
                      </label>
                      <input
                        id="pdf-margin"
                        type="range"
                        min={0}
                        max={30}
                        step={1}
                        value={settings.margin}
                        disabled={settings.pageSize === 'auto'}
                        onChange={(e) =>
                          setSettings((prev) => ({ ...prev, margin: Number(e.target.value) }))
                        }
                        className="w-full accent-indigo-600 disabled:opacity-40"
                      />
                      <p className="text-sm text-stone-500 dark:text-stone-400 mt-1">
                        {settings.pageSize === 'auto'
                          ? 'Sin margen: la página usa el tamaño original del SVG.'
                          : 'Espacio en blanco alrededor de la partitura.'}
                      </p>
                    </div>
                  </div>
                </div>

                {progress && (
                  <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 border border-stone-200/60 dark:border-stone-800/60">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                        🔄 Generando PDF...
                      </h3>
                      <span className="text-sm text-stone-600 dark:text-stone-400">
                        {progress.current} de {progress.total} ({progress.percentage}%)
                      </span>
                    </div>

                    <div className="w-full bg-stone-200 dark:bg-stone-700 rounded-full h-3 mb-2">
                      <div
                        className="bg-indigo-600 h-3 rounded-full transition-all duration-300"
                        style={{ width: `${progress.percentage}%` }}
                      />
                    </div>

                    <p className="text-sm text-stone-600 dark:text-stone-400">
                      {progress.currentFile}
                    </p>
                  </div>
                )}

                {error && (
                  <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-2xl p-6">
                    <p className="text-sm text-red-800 dark:text-red-200">⚠️ {error}</p>
                  </div>
                )}

                <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-6 border border-stone-200/60 dark:border-stone-800/60">
                  <div className="flex flex-wrap gap-4 items-center justify-between">
                    <div className="flex flex-wrap gap-4">
                      <button
                        onClick={handleMerge}
                        disabled={isWorking}
                        className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-stone-400 disabled:cursor-not-allowed text-white px-6 py-3 rounded-lg font-semibold transition-colors duration-200 flex items-center gap-2"
                      >
                        {isWorking ? (
                          <Loader2 className="w-5 h-5 animate-spin" />
                        ) : (
                          <FileDown className="w-5 h-5" />
                        )}
                        <span>Unir en un PDF ({files.length} páginas)</span>
                      </button>

                      <button
                        onClick={handleIndividual}
                        disabled={isWorking}
                        className="border border-stone-300 dark:border-stone-700 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 disabled:opacity-50 disabled:cursor-not-allowed px-6 py-3 rounded-lg font-semibold transition-colors duration-200 flex items-center gap-2"
                      >
                        <FileArchive className="w-5 h-5" />
                        <span>PDF por página (.zip)</span>
                      </button>
                    </div>

                    <div className="text-sm text-stone-600 dark:text-stone-400 flex items-center gap-2">
                      <Download className="w-4 h-4" />
                      {files.length} archivos · {formatFileSize(totalSize)}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
