'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, FileArchive, FileDown, FileMusic, Layers, Loader2, Monitor, RectangleHorizontal, RectangleVertical, Terminal } from 'lucide-react';
import WorkspaceShell from '@/components/dashboard/WorkspaceShell';
import SvgPageList from '@/components/SvgPageList';
import SvgUploader from '@/components/SvgUploader';
import type { PageSizeMode, PdfProgress, PdfSettings, SvgFile } from '@/types/svg-to-pdf';
import { buildIndividualPdfs, buildMergedPdf, createPdfZip, downloadBlob, formatFileSize, moveSvgFile, sanitizeFileName, sortSvgFilesByName } from '@/utils/svg-to-pdf';
import styles from './converter.module.css';

const FORMATS: { value: PageSizeMode; label: string; dimensions: string; detail: string }[] = [
  { value: 'a4', label: 'A4', dimensions: '210 × 297 mm', detail: 'Estándar europeo' },
  { value: 'letter', label: 'Carta', dimensions: '215.9 × 279.4 mm', detail: 'Estándar US' },
  { value: 'auto', label: 'Original', dimensions: 'Dimensiones del SVG', detail: 'Tamaño de cada página' },
];

export default function SvgToPdfPage() {
  const [files, setFiles] = useState<SvgFile[]>([]);
  const [settings, setSettings] = useState<PdfSettings>({ pageSize: 'a4', margin: 10, fileName: 'partitura', orientation: 'portrait' });
  const [merged, setMerged] = useState(true);
  const [individual, setIndividual] = useState(true);
  const [working, setWorking] = useState<'merged' | 'zip' | null>(null);
  const [reading, setReading] = useState(false);
  const [progress, setProgress] = useState<PdfProgress | null>(null);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('Añade tus páginas SVG para preparar el documento.');
  const filesRef = useRef<SvgFile[]>([]);
  const mounted = useRef(true);
  const jobLock = useRef(false);
  filesRef.current = files;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; filesRef.current.forEach(file => URL.revokeObjectURL(file.preview)); }; }, []);
  const busy = !!working || reading;

  const addFiles = useCallback((incoming: SvgFile[]) => {
    if (!mounted.current) { incoming.forEach(file => URL.revokeObjectURL(file.preview)); return; }
    // New batches are naturally ordered without undoing the user's existing page order.
    setFiles(prev => [...prev, ...sortSvgFilesByName(incoming)]);
    setError(''); setStatus(`${incoming.length} páginas añadidas. Revisa el orden antes de compilar.`);
  }, []);
  const remove = (id: string) => {
    const file = files.find(item => item.id === id);
    if (file) URL.revokeObjectURL(file.preview);
    setFiles(prev => prev.filter(file => file.id !== id)); setProgress(null); setStatus('Página eliminada de la compilación.');
  };
  const clear = () => {
    files.forEach(file => URL.revokeObjectURL(file.preview)); setFiles([]); setProgress(null); setError(''); setStatus('Cola vacía. Añade tus páginas SVG para comenzar.');
  };
  const runJob = async (kind: 'merged' | 'zip') => {
    if (!files.length || jobLock.current || reading || (kind === 'merged' ? !merged : !individual)) return;
    jobLock.current = true; setWorking(kind); setError(''); setProgress(null);
    setStatus(kind === 'merged' ? 'Preparando el PDF multipágina…' : 'Preparando los PDFs individuales…');
    const started = performance.now(), snapshot = [...files], config = { ...settings };
    const onProgress = (value: PdfProgress) => { if (mounted.current) setProgress(value); };
    try {
      const output = kind === 'merged' ? await buildMergedPdf(snapshot, config, onProgress)
        : await createPdfZip(await buildIndividualPdfs(snapshot, config, onProgress));
      if (!mounted.current) return;
      const name = `${sanitizeFileName(config.fileName)}${kind === 'merged' ? '.pdf' : '-paginas.zip'}`;
      downloadBlob(output, name);
      setStatus(`${name} generado · ${snapshot.length} páginas · ${formatFileSize(output.size)} · ${((performance.now() - started) / 1000).toFixed(1)} s`);
    } catch (error) {
      if (mounted.current) { setError(error instanceof Error ? error.message : 'No se pudo generar el PDF.'); setStatus('La compilación no se completó. Revisa los archivos e inténtalo de nuevo.'); setProgress(null); }
    } finally { jobLock.current = false; if (mounted.current) setWorking(null); }
  };
  const outputName = `${sanitizeFileName(settings.fileName)}.pdf`;
  const format = FORMATS.find(format => format.value === settings.pageSize)!;
  const orientation = settings.pageSize === 'auto' ? 'Orientación original' : settings.orientation === 'landscape' ? 'Horizontal' : 'Vertical';

  return <WorkspaceShell title="SVG a PDF" mainId="svg-main" sectionHref="#pdf-export" sectionLabel="Compilar documento">
    <div className={styles.converter}>
      <header className={styles.titleBlock}><div><div className={styles.eyebrow}><span><FileMusic size={17} />Música y documentos</span><code>SVG → PDF</code></div><h1>Compilador de SVG a PDF / Partituras Musicales</h1><p>Convierte y ensambla tus páginas SVG en un PDF vectorial. Ajusta el formato, revisa el orden y descarga tu partitura lista para imprimir.</p></div><span className={styles.localBadge}><Monitor size={15} />Procesamiento local</span></header>
      <section className={`${styles.panel} ${styles.settings}`} aria-label="Configuración del documento">
        <fieldset disabled={busy} className={styles.formatField}><legend>Formato y dimensiones</legend><div className={styles.formats}>{FORMATS.map(format => <label key={format.value} className={`${styles.formatCard} ${settings.pageSize === format.value ? styles.selectedFormat : ''}`}><span><strong>{format.label}</strong><input type="radio" name="pageSize" aria-label={format.label} checked={settings.pageSize === format.value} onChange={() => setSettings(prev => ({ ...prev, pageSize: format.value }))} /></span><code>{format.dimensions}</code><small>{format.detail}</small></label>)}</div></fieldset>
        <fieldset disabled={busy} className={styles.layoutField}><legend className={styles.srOnly}>Diseño de página</legend><div className={styles.layoutControls}><div><span className={styles.controlLabel}>Orientación</span><div className={styles.orientation} role="group" aria-label="Orientación"><button type="button" disabled={settings.pageSize === 'auto'} aria-pressed={settings.orientation === 'portrait'} onClick={() => setSettings(prev => ({ ...prev, orientation: 'portrait' }))}><RectangleVertical size={15} />Vertical</button><button type="button" disabled={settings.pageSize === 'auto'} aria-pressed={settings.orientation === 'landscape'} onClick={() => setSettings(prev => ({ ...prev, orientation: 'landscape' }))}><RectangleHorizontal size={15} />Horizontal</button></div></div><div><label className={styles.controlLabel} htmlFor="pdf-margin">Márgenes: {settings.pageSize === 'auto' ? 0 : settings.margin} mm</label><input id="pdf-margin" type="range" min={0} max={30} step={1} value={settings.margin} disabled={settings.pageSize === 'auto'} onChange={event => setSettings(prev => ({ ...prev, margin: Number(event.target.value) }))} /><small>{settings.pageSize === 'auto' ? 'El tamaño original no añade márgenes.' : 'Espacio alrededor de cada página.'}</small></div></div><label className={styles.controlLabel} htmlFor="pdf-name">Nombre de salida</label><div className={styles.nameField}><FileDown size={16} /><input id="pdf-name" value={settings.fileName} onChange={event => setSettings(prev => ({ ...prev, fileName: event.target.value }))} /><span>.pdf</span></div></fieldset>
        <fieldset className={styles.modes} disabled={busy}><legend>Modos de generación</legend><label><span><strong>PDF único multipágina</strong><small>Consolida las páginas en el orden elegido</small></span><input type="checkbox" checked={merged} onChange={event => setMerged(event.target.checked)} /></label><label><span><strong>ZIP de PDFs individuales</strong><small>Un archivo PDF por cada página SVG</small></span><input type="checkbox" checked={individual} onChange={event => setIndividual(event.target.checked)} /></label><span className={styles.modeHint}><Layers size={13} />Conversión con jsPDF + svg2pdf.js</span></fieldset>
      </section>
      <SvgPageList files={files} disabled={busy} onReorder={(from, to) => { setFiles(prev => moveSvgFile(prev, from, to)); setProgress(null); setStatus('Orden de páginas actualizado.'); }} onRemove={remove} onSortByName={() => { setFiles(prev => sortSvgFilesByName(prev)); setProgress(null); setStatus('Páginas ordenadas por nombre.'); }} onReverse={() => { setFiles(prev => [...prev].reverse()); setProgress(null); setStatus('Orden de páginas invertido.'); }} onClear={clear}>
        <SvgUploader onFilesAdded={addFiles} maxFiles={Math.max(0, 100 - files.length)} disabled={!!working} onReadingChange={setReading} />
      </SvgPageList>
      <p className={styles.fontHint}>Para conservar símbolos musicales con mayor fidelidad, exporta el SVG con las fuentes convertidas en trazados. Las fuentes externas pueden variar al convertir.</p>
      <section id="pdf-export" className={`${styles.panel} ${styles.exportPanel}`} aria-labelledby="export-title" aria-busy={!!working}>
        <div className={styles.exportTop}><div><h2 id="export-title"><span className={styles.dot} />{working ? 'Compilando documento…' : `${files.length} páginas listas para compilar`}</h2><p>Documento destino: <strong>{outputName}</strong></p><code>{format.label} · {orientation} · Márgenes {settings.pageSize === 'auto' ? 0 : settings.margin} mm</code></div><div className={styles.exportButtons}><button type="button" className={styles.secondaryButton} disabled={!files.length || busy || !individual} onClick={() => void runJob('zip')}>{working === 'zip' ? <Loader2 size={17} className={styles.spin} /> : <FileArchive size={17} />}Descargar ZIP (PDFs individuales)</button><button type="button" className={styles.primaryButton} disabled={!files.length || busy || !merged} onClick={() => void runJob('merged')}>{working === 'merged' ? <Loader2 size={18} className={styles.spin} /> : <FileDown size={18} />}Compilar PDF multipágina ({files.length})</button></div></div>
        {!merged && !individual && <p className={styles.notice}>Activa al menos un modo de generación para descargar el documento.</p>}
        {progress && <div className={styles.progress}><div><span>{working ? progress.currentFile : 'Compilación completada'}</span><code>{progress.current} / {progress.total} · {progress.percentage}%</code></div><div role="progressbar" aria-label="Progreso de compilación" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress.percentage}><span style={{ width: `${progress.percentage}%` }} /></div></div>}
        {error && <p className={styles.notice} role="alert">{error}</p>}
        <div className={styles.console} role="status" aria-live="polite"><Terminal size={15} /><code>[SVG a PDF]</code><span>{status}</span>{!working && !!progress && !error && <Check size={15} />}</div>
      </section>
    </div>
  </WorkspaceShell>;
}
