'use client';

import { useEffect, useRef, useState } from 'react';
import { Archive, ArrowRight, CheckCircle2, CircleAlert, Download, Image as ImageIcon,
  LoaderCircle, Play, ShieldCheck, Square, Terminal, Trash2, X } from 'lucide-react';
import WorkspaceShell from '@/components/dashboard/WorkspaceShell';
import ImageUploader from '@/components/ImageUploader';
import ImagePreview from '@/components/ImagePreview';
import ConversionSettingsComponent from '@/components/ConversionSettings';
import useImageBatch, { outputName } from '@/hooks/use-image-batch';
import { formatFileSize } from '@/utils/image-converter';
import styles from './converter.module.css';

export default function ConvertImagesPage() {
  const batch = useImageBatch();
  const { images, settings, running, progress } = batch;
  const completed = images.filter(image => image.status === 'completed');
  const pending = images.filter(image => image.status === 'pending');
  const failed = images.filter(image => image.status === 'error');
  const processing = images.filter(image => image.status === 'converting');
  const totalBytes = images.reduce((sum, image) => sum + image.size, 0);
  const outputBytes = completed.reduce((sum, image) => sum + (image.convertedBlob?.size || 0), 0);
  const completedBytes = completed.reduce((sum, image) => sum + image.size, 0);
  const saved = completedBytes ? Math.round((1 - outputBytes / completedBytes) * 100) : 0;
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [showResult, setShowResult] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const preview = images.find(image => image.id === previewId);
  useEffect(() => {
    if (previewId && preview && !dialog.current?.open) { setShowResult(!!preview.convertedBlob); dialog.current?.showModal(); }
    else if (!preview && dialog.current?.open) dialog.current.close();
  }, [previewId, preview]);
  const zipDisabled = !completed.length || batch.exporting || running;
  const canProcess = pending.length > 0 && !running && !batch.settingsError;
  const processLabel = running ? (batch.cancelling ? 'Deteniendo…' : 'Procesando…') : `Procesar ${pending.length} pendientes`;

  return (
    <WorkspaceShell title="Imágenes" mainId="converter-main" sectionHref="#cola" sectionLabel="Cola de procesamiento">
      <div className={styles.converter}>
        <section className={`${styles.panel} ${styles.ribbon}`} aria-labelledby="converter-title">
          <div className={styles.titleBlock}>
            <div className={styles.eyebrow}><span><ShieldCheck size={12} aria-hidden="true" />Procesamiento en tu navegador</span><span>Hasta 50 imágenes por lote</span></div>
            <h1 id="converter-title">Convertidor de Imágenes por Lotes</h1>
            <p>Convierte, redimensiona y optimiza tus imágenes. Ajusta el formato y la calidad, revisa los resultados y descarga todo en un ZIP.</p>
          </div>
          <div className={styles.ribbonActions}>
            <button type="button" className={styles.secondaryButton} disabled={!images.length || running || batch.exporting} onClick={batch.clear}><Trash2 size={15} />Limpiar cola</button>
            <button type="button" className={styles.secondaryButton} disabled={zipDisabled} onClick={() => void batch.zip()}><Archive size={15} />Exportar lote (.ZIP)</button>
            <button type="button" className={styles.primaryButton} disabled={!canProcess} onClick={() => void batch.process()}>{running ? <LoaderCircle size={16} className={styles.spinning} /> : <Play size={16} />}{processLabel}</button>
          </div>
        </section>
        <div className={styles.workspaceGrid}>
          <aside className={styles.configuration} aria-label="Ajustes de conversión">
            <ConversionSettingsComponent settings={settings} onChange={batch.setSettings} supported={batch.supported}
              disabled={running} pattern={batch.pattern} onPatternChange={batch.setPattern} />
          </aside>
          <div className={styles.queueWorkspace}>
            <ImageUploader onFilesAdded={batch.addFiles} disabled={running} count={images.length} />
            {(batch.errors.length > 0 || batch.settingsError) && <div role="alert" className={styles.alert}><CircleAlert size={18} aria-hidden="true" /><div>{batch.settingsError && <p>{batch.settingsError}</p>}{batch.errors.map((error, i) => <p key={i}>{error}</p>)}</div></div>}
            <section id="cola" className={`${styles.panel} ${styles.queueOverview}`} aria-labelledby="queue-title">
              <div className={styles.overviewTop}><div className={styles.panelHeading}><h2 id="queue-title">Cola de procesamiento</h2><span>{images.length} elementos</span></div>
                <div className={styles.queueCounts}><span><CheckCircle2 size={12} />{completed.length} listos</span><span><LoaderCircle size={12} className={running ? styles.spinning : undefined} />{processing.length} en proceso</span><span><CircleAlert size={12} />{failed.length} con error</span></div></div>
              <div className={styles.progressLabels}><span>Progreso del lote</span><strong>{progress ? `${progress.percentage}% · ${progress.current} / ${progress.total} archivos` : `${pending.length} pendientes`}</strong></div>
              <div role="progressbar" aria-label="Progreso global del lote" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress?.percentage ?? 0} className={styles.progressTrack}><span style={{ width: `${progress?.percentage ?? 0}%` }} /></div>
              <p className={styles.progressDetail}>{running ? (batch.cancelling ? 'Deteniendo el lote al terminar la operación actual…' : progress?.currentFile) : completed.length ? 'Los archivos procesados están listos para descargar.' : 'Añade tus imágenes y elige cómo quieres convertirlas.'}</p>
            </section>
            <div className={styles.queueList} aria-label="Archivos del lote">
              {images.map(image => <ImagePreview key={image.id} image={image} filename={outputName(image, settings.format, batch.pattern)} running={running}
                onRemove={batch.remove} onDownload={batch.download} onRename={batch.rename} onPreview={setPreviewId} onRetry={id => void batch.process(id)} />)}
              {!images.length && <div className={styles.emptyQueue}><ImageIcon size={31} aria-hidden="true" /><h3>Tu cola está lista para empezar</h3><p>Los archivos que añadas aparecerán aquí, junto con su estado y sus opciones de descarga.</p></div>}
            </div>
            <section className={styles.processLog} aria-labelledby="log-heading">
              <div className={styles.logHeader}><Terminal size={14} aria-hidden="true" /><h2 id="log-heading">Registro de conversión</h2><span>{running ? 'En curso' : 'En espera'}</span></div>
              <div className={styles.logLines} role="log" aria-live="polite" aria-label="Eventos de conversión">
                {batch.logs.length ? batch.logs.map((line, i) => <p key={i}><time>[{line.time}]</time><strong>{line.kind}:</strong><span>{line.message}</span></p>) : <p>Sin eventos. Añade imágenes para preparar tu próximo lote.</p>}
              </div>
            </section>
          </div>
        </div>
        <div className={styles.batchBar} aria-label="Resumen del lote">
          <div className={styles.batchSummary}><strong><CheckCircle2 size={16} aria-hidden="true" />Resumen del lote</strong><span>Original: <b>{formatFileSize(totalBytes)}</b></span><ArrowRight size={14} aria-hidden="true" /><span>Resultados: <b>{formatFileSize(outputBytes)}</b>{completed.length > 0 && <small>({saved >= 0 ? `−${saved}%` : `+${-saved}%`} sobre convertidas)</small>}</span></div>
          <div className={styles.batchActions}><button type="button" className={styles.secondaryButton} disabled={!running || batch.cancelling} onClick={batch.cancel}><Square size={13} />{batch.cancelling ? 'Deteniendo…' : 'Cancelar todo'}</button><button type="button" className={styles.primaryButton} disabled={zipDisabled} onClick={() => void batch.zip()}>{batch.exporting ? <LoaderCircle size={16} className={styles.spinning} /> : <Download size={16} />}{batch.exporting ? 'Preparando ZIP…' : `Descargar todo (.ZIP)`}</button></div>
        </div>
        <dialog ref={dialog} className={styles.previewDialog} onClose={() => setPreviewId(null)} onClick={event => { if (event.target === event.currentTarget) dialog.current?.close(); }} aria-labelledby="preview-title">
          {preview && <div className={styles.dialogContent}>
            <div className={styles.dialogHeader}><div><h2 id="preview-title">Vista previa</h2><p>{preview.name}</p></div><button type="button" onClick={() => dialog.current?.close()} aria-label="Cerrar vista previa"><X size={20} /></button></div>
            <div className={styles.previewTabs}><button type="button" aria-pressed={!showResult} onClick={() => setShowResult(false)}>Original · {formatFileSize(preview.size)}</button><button type="button" aria-pressed={showResult} disabled={!preview.convertedUrl} onClick={() => setShowResult(true)}>Resultado{preview.convertedBlob ? ` · ${formatFileSize(preview.convertedBlob.size)}` : ''}</button></div>
            <div className={styles.previewCanvas}><img src={showResult && preview.convertedUrl ? preview.convertedUrl : preview.preview} alt={`${showResult ? 'Resultado' : 'Original'}: ${preview.name}`} /></div>
            {preview.convertedBlob && <button type="button" className={styles.primaryButton} onClick={() => batch.download(preview.id)}><Download size={16} />Descargar resultado</button>}
          </div>}
        </dialog>
      </div>
    </WorkspaceShell>
  );
}
