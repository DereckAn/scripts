'use client';

import { useState } from 'react';
import { Check, CheckCircle2, Clock3, Download, Eye, ImageOff, LoaderCircle, Pencil, RotateCcw, Trash2, X } from 'lucide-react';
import type { ImageFile } from '@/types/image-converter';
import { formatFileSize } from '@/utils/image-converter';
import styles from '@/app/convert-images/converter.module.css';

export default function ImagePreview({ image, filename, running, onRemove, onDownload, onRename, onPreview, onRetry }: {
  image: ImageFile; filename: string; running: boolean;
  onRemove: (id: string) => void; onDownload: (id: string) => void; onRename: (id: string, name: string) => void;
  onPreview: (id: string) => void; onRetry: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false), [draft, setDraft] = useState('');
  const [broken, setBroken] = useState(false);
  const status = { pending: 'En cola', converting: 'Convirtiendo…', completed: 'Completado', error: 'Error' }[image.status];
  const Status = { pending: Clock3, converting: LoaderCircle, completed: CheckCircle2, error: ImageOff }[image.status];
  const save = () => { if (draft.trim()) { onRename(image.id, draft.trim()); setEditing(false); } };
  const saving = image.convertedBlob && image.size ? Math.round((1 - image.convertedBlob.size / image.size) * 100) : null;
  return (
    <article className={`${styles.queueItem} ${image.status === 'error' ? styles.errorItem : ''}`} data-state={image.status}>
      <div className={styles.fileIdentity}>
        <button type="button" className={styles.thumbnail} onClick={() => onPreview(image.id)} aria-label={`Vista previa de ${image.name}`}>
          {broken ? <ImageOff size={22} aria-hidden="true" /> : <img src={image.preview} alt="" onError={() => setBroken(true)} />}
          <span>{image.originalFormat.replace('+xml', '').toUpperCase()}</span>
        </button>
        <div className={styles.fileDetails}>
          <h3 title={image.name}>{image.name}</h3>
          <div className={styles.fileMeta}><span>{formatFileSize(image.size)}</span><span>→</span><span>{image.convertedBlob ? `${formatFileSize(image.convertedBlob.size)} ${image.convertedFormat?.toUpperCase()}` : filename}</span>{saving !== null && <small>{saving >= 0 ? `−${saving}%` : `+${-saving}%`}</small>}</div>
          {editing ? <div className={styles.renameField}><input aria-label={`Nuevo nombre de ${image.name}`} value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false); }} autoFocus /><button type="button" onClick={save} title="Guardar nombre" aria-label="Guardar nombre"><Check size={15} /></button><button type="button" onClick={() => setEditing(false)} title="Cancelar nombre" aria-label="Cancelar nombre"><X size={15} /></button></div> : image.convertedBlob && <p className={styles.outputName} title={filename}>{filename}</p>}
          {image.error && <p className={styles.fileError}>{image.error}</p>}
        </div>
      </div>
      <div className={styles.fileActions}>
        <span className={`${styles.status} ${image.status === 'completed' ? styles.completedStatus : ''}`}><Status size={13} className={image.status === 'converting' ? styles.spinning : undefined} aria-hidden="true" />{status}</span>
        <div className={styles.rowButtons}>
          {image.status === 'error' && <button type="button" className={styles.retry} disabled={running} onClick={() => onRetry(image.id)} aria-label={`Reintentar ${image.name}`}><RotateCcw size={14} />Reintentar</button>}
          <button type="button" onClick={() => onPreview(image.id)} title="Ver previo" aria-label={`Ver previo de ${image.name}`}><Eye size={16} /></button>
          <button type="button" disabled={running} onClick={() => { setDraft(filename.replace(/\.[^.]+$/, '')); setEditing(true); }} title="Renombrar" aria-label={`Renombrar ${image.name}`}><Pencil size={15} /></button>
          {image.convertedBlob && <button type="button" onClick={() => onDownload(image.id)} title="Descargar" aria-label={`Descargar ${filename}`}><Download size={16} /></button>}
          <button type="button" onClick={() => onRemove(image.id)} title={image.status === 'converting' ? 'Cancelar tarea' : 'Quitar de cola'} aria-label={`Quitar ${image.name}`}><Trash2 size={15} /></button>
        </div>
      </div>
    </article>
  );
}
