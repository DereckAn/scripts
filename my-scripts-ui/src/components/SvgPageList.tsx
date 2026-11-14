'use client';

import { useRef, useState, type ReactNode } from 'react';
import Image from 'next/image';
import { ArrowDownAZ, ArrowDownUp, ChevronLeft, ChevronRight, CircleCheck, GripVertical, Trash2, X, ZoomIn } from 'lucide-react';
import type { SvgFile } from '@/types/svg-to-pdf';
import { formatFileSize } from '@/utils/svg-to-pdf';
import styles from '@/app/svg-to-pdf/converter.module.css';

export default function SvgPageList({ files, onReorder, onRemove, onSortByName, onReverse, onClear, disabled = false, children }: {
  files: SvgFile[]; onReorder: (from: number, to: number) => void; onRemove: (id: string) => void;
  onSortByName: () => void; onReverse: () => void; onClear: () => void; disabled?: boolean; children?: ReactNode;
}) {
  const [dragged, setDragged] = useState<number | null>(null);
  const [target, setTarget] = useState<number | null>(null);
  const [preview, setPreview] = useState<SvgFile | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const total = files.reduce((sum, file) => sum + file.size, 0);
  return <section className={styles.pageSection} aria-label="Páginas del documento">
    <div className={styles.listToolbar}><div className={styles.fileStats}><span className={styles.dot} /><strong>{files.length} páginas cargadas</strong><code>Total: {formatFileSize(total)}</code>{!!files.length && <span className={styles.validBadge}><CircleCheck size={13} />SVG leídos correctamente</span>}</div>
      <div className={styles.listActions}><button type="button" disabled={disabled || files.length < 2} onClick={onSortByName}><ArrowDownAZ size={15} />Ordenar por nombre</button><button type="button" disabled={disabled || files.length < 2} onClick={onReverse}><ArrowDownUp size={15} />Invertir orden</button><button type="button" disabled={disabled || !files.length} onClick={onClear}><Trash2 size={15} />Limpiar todo</button></div>
    </div>
    <p className={styles.reorderHint}>Arrastra las tarjetas o usa las flechas para cambiar el orden de las páginas.</p>
    <div className={styles.pageGrid}>{files.map((file, index) => <article key={file.id} aria-label={`Página ${index + 1}: ${file.name}`} draggable={!disabled}
      className={`${styles.pageCard} ${dragged === index ? styles.dragged : ''} ${target === index ? styles.dropTarget : ''}`}
      onDragStart={event => { if (disabled) { event.preventDefault(); return; } setDragged(index); event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', file.id); }}
      onDragEnd={() => { setDragged(null); setTarget(null); }} onDragOver={event => { if (!disabled && dragged !== null) { event.preventDefault(); setTarget(index); } }}
      onDrop={event => { event.preventDefault(); if (!disabled && dragged !== null) onReorder(dragged, index); setDragged(null); setTarget(null); }}>
      <div className={styles.cardHeader}><GripVertical size={17} aria-hidden="true" /><strong>Pág. {index + 1}</strong><span><CircleCheck size={12} />SVG válido</span></div>
      <button type="button" className={styles.thumbnail} onClick={() => { setPreview(file); dialog.current?.showModal(); }} aria-label={`Previsualizar ${file.name}`}>
        <Image src={file.preview} alt={`Vista previa de ${file.name}`} fill unoptimized draggable={false} sizes="(max-width: 600px) 90vw, 25vw" /><span className={styles.zoom}><ZoomIn size={23} /></span>
      </button>
      <div className={styles.fileName}><strong title={file.name}>{file.name}</strong><code>{formatFileSize(file.size)}</code></div>
      <code className={styles.dimensions}>{Math.round(file.width)} × {Math.round(file.height)} px</code>
      <div className={styles.cardActions}><div><button type="button" disabled={disabled || index === 0} onClick={() => onReorder(index, index - 1)} aria-label={`Mover ${file.name} a la izquierda`}><ChevronLeft size={17} /></button><button type="button" disabled={disabled || index === files.length - 1} onClick={() => onReorder(index, index + 1)} aria-label={`Mover ${file.name} a la derecha`}><ChevronRight size={17} /></button></div><button type="button" disabled={disabled} onClick={() => onRemove(file.id)} aria-label={`Quitar ${file.name}`}><Trash2 size={16} /></button></div>
    </article>)}{children}</div>
    <dialog ref={dialog} className={styles.previewDialog} aria-labelledby="svg-preview-title" onClick={event => { if (event.target === event.currentTarget) dialog.current?.close(); }}>
      <div className={styles.previewHeader}><h2 id="svg-preview-title">{preview?.name}</h2><button type="button" aria-label="Cerrar vista previa" onClick={() => dialog.current?.close()}><X size={22} /></button></div>
      {preview && <div className={styles.previewSheet}><Image src={preview.preview} alt={preview.name} width={preview.width} height={preview.height} unoptimized /></div>}
    </dialog>
  </section>;
}
