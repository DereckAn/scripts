'use client';

import { useState } from 'react';
import { CloudUpload, HardDrive, ShieldCheck } from 'lucide-react';
import styles from '@/app/convert-images/converter.module.css';

export default function ImageUploader({ onFilesAdded, disabled = false, count = 0 }: {
  onFilesAdded: (files: File[]) => void; disabled?: boolean; count?: number;
}) {
  const [dragging, setDragging] = useState(false);
  return (
    <label className={`${styles.dropzone} ${dragging ? styles.dragging : ''} ${disabled ? styles.dropDisabled : ''}`}
      onDragOver={event => { event.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
      onDrop={event => { event.preventDefault(); setDragging(false); if (!disabled) onFilesAdded(Array.from(event.dataTransfer.files)); }}>
      <input className={styles.srOnly} aria-label="Añadir imágenes" type="file" multiple disabled={disabled || count >= 50}
        accept="image/jpeg,image/png,image/webp,image/avif,image/bmp,image/tiff,image/gif,image/svg+xml"
        onChange={event => { onFilesAdded(Array.from(event.target.files || [])); event.target.value = ''; }} />
      <span className={styles.uploadIcon}><CloudUpload size={27} aria-hidden="true" /></span>
      <strong>{dragging ? 'Suelta las imágenes para añadirlas' : 'Arrastra tus archivos aquí o '} {!dragging && <span>haz clic para examinar</span>}</strong>
      <p>PNG, JPEG, WebP, AVIF, TIFF, BMP, GIF, SVG · Hasta 50 archivos, 50 MB por archivo</p>
      <div className={styles.dropBadges}><span><HardDrive size={13} aria-hidden="true" />{50 - count} espacios disponibles</span><span><ShieldCheck size={13} aria-hidden="true" />Conversión en tu navegador</span></div>
    </label>
  );
}
