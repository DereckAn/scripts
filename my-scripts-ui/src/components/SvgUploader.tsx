'use client';

import { useRef, useState } from 'react';
import { FilePlus2, Loader2 } from 'lucide-react';
import type { SvgFile } from '@/types/svg-to-pdf';
import { createSvgFile, validateSvgFile } from '@/utils/svg-to-pdf';
import styles from '@/app/svg-to-pdf/converter.module.css';

export default function SvgUploader({ onFilesAdded, maxFiles = 100, disabled = false, onReadingChange }: {
  onFilesAdded: (files: SvgFile[]) => void; maxFiles?: number; disabled?: boolean;
  onReadingChange?: (reading: boolean) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const [reading, setReading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const readingRef = useRef(false);

  const handleFiles = async (incoming: FileList | File[]) => {
    if (disabled || readingRef.current) return;
    const list = Array.from(incoming), next: SvgFile[] = [], problems: string[] = [];
    if (list.length > maxFiles) problems.push(`Solo puedes añadir ${maxFiles} páginas más (máximo 100 en total).`);
    readingRef.current = true; setReading(true); onReadingChange?.(true);
    try {
      for (const file of list.slice(0, maxFiles)) {
        const validation = validateSvgFile(file);
        if (!validation.valid) { problems.push(`${file.name}: ${validation.error}`); continue; }
        try { next.push(await createSvgFile(file)); }
        catch (error) { problems.push(`${file.name}: ${error instanceof Error ? error.message : 'No se pudo leer el archivo'}`); }
      }
      if (next.length) onFilesAdded(next);
      setErrors(problems);
    } finally { readingRef.current = false; setReading(false); onReadingChange?.(false); }
  };

  return <div className={styles.uploadWrapper}>
    <button type="button" className={`${styles.uploadCard} ${dragOver ? styles.dragOver : ''}`} disabled={disabled || reading}
      onClick={() => input.current?.click()}
      onDragOver={event => { event.preventDefault(); if (!disabled && !reading) setDragOver(true); }}
      onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragOver(false); }}
      onDrop={event => { event.preventDefault(); setDragOver(false); void handleFiles(event.dataTransfer.files); }}>
      <span className={styles.uploadIcon}>{reading ? <Loader2 className={styles.spin} size={25} /> : <FilePlus2 size={25} />}</span>
      <strong>{reading ? 'Leyendo páginas…' : dragOver ? 'Suelta tus páginas aquí' : 'Añadir páginas SVG'}</strong>
      <span>Arrastra tus partituras o haz clic para explorar</span>
      <code>.svg, .svgz · 25 MB por archivo</code><small>{Math.max(0, maxFiles)} espacios disponibles</small>
    </button>
    <input ref={input} type="file" multiple accept=".svg,.svgz,image/svg+xml" aria-label="Añadir archivos SVG" className={styles.hiddenInput} disabled={disabled || reading}
      onChange={event => { if (event.target.files) void handleFiles(event.target.files); event.target.value = ''; }} />
    {!!errors.length && <div className={styles.uploadErrors} role="alert"><strong>No se pudieron añadir todos los archivos</strong><ul>{errors.map((error, index) => <li key={index}>{error}</li>)}</ul><button type="button" onClick={() => setErrors([])}>Cerrar aviso</button></div>}
  </div>;
}
