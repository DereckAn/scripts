'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ConversionProgress, ConversionSettings, ImageFile, ImageFormat } from '@/types/image-converter';
import { OUTPUT_FORMATS } from '@/types/image-converter';
import { convertImage, createImageFile, downloadAsZip, downloadBlob, formatFileSize,
  generateFileName, getMimeType, validateImageFile } from '@/utils/image-converter';

export type BatchLog = { time: string; kind: 'INFO' | 'OK' | 'ERROR'; message: string };
export function outputName(image: ImageFile, format: ImageFormat, pattern: string): string {
  if (image.convertedBlob) return generateFileName(image.name, image.convertedFormat ?? format, image.customName ?? image.convertedName);
  const base = image.name.replace(/\.[^/.]+$/, '');
  const rendered = (pattern.trim() || '{name}.{ext}').replace(/\{(?:name|filename)\}/g, () => base).replace(/\{ext\}/g, format);
  return generateFileName(image.name, format, image.customName || rendered.replace(new RegExp(`\\.${format}$`, 'i'), ''));
}

export default function useImageBatch() {
  const [images, setImages] = useState<ImageFile[]>([]);
  const [settings, setSettings] = useState<ConversionSettings>({ format: 'webp', quality: 85,
    maintainAspectRatio: true, removeMetadata: true, backgroundColor: '#ffffff', flattenTransparency: false });
  const [pattern, setPattern] = useState('{name}_opt.{ext}');
  const [supported, setSupported] = useState<ImageFormat[]>(['jpg', 'png', 'webp']);
  const [running, setRunning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState<ConversionProgress | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [logs, setLogs] = useState<BatchLog[]>([]);
  const current = useRef<ImageFile[]>([]);
  const active = useRef(false);
  const stop = useRef(false);
  const mounted = useRef(true);
  const update = useCallback((change: (items: ImageFile[]) => ImageFile[]) => {
    current.current = change(current.current);
    if (mounted.current) setImages(current.current);
  }, []);
  const log = useCallback((kind: BatchLog['kind'], message: string) => {
    if (mounted.current) setLogs(prev => [...prev.slice(-49), {
      time: new Date().toLocaleTimeString('es-MX', { hour12: false }), kind, message,
    }]);
  }, []);
  useEffect(() => {
    mounted.current = true;
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
    const available = OUTPUT_FORMATS.filter(f => canvas.toDataURL(getMimeType(f.value)).startsWith(`data:${getMimeType(f.value)};`)).map(f => f.value);
    setSupported(available);
    setSettings(prev => available.includes(prev.format) ? prev : { ...prev, format: 'jpg' });
    return () => {
      mounted.current = false; stop.current = true;
      current.current.forEach(image => { URL.revokeObjectURL(image.preview); if (image.convertedUrl) URL.revokeObjectURL(image.convertedUrl); });
    };
  }, []);

  const settingsError = [settings.width, settings.height].some(n => n !== undefined && (!Number.isInteger(n) || n < 1 || n > 16384))
    ? 'Las dimensiones deben ser números enteros entre 1 y 16384 px.'
    : !/^#[0-9a-f]{6}$/i.test(settings.backgroundColor || '') ? 'Elige un color de fondo válido.'
    : /\{[^}]*\}/.test(pattern.replace(/\{(?:name|filename|ext)\}/g, '')) ? 'Usa los tokens {name}, {filename} y {ext} para el nombre.' : '';

  const addFiles = useCallback((files: File[]) => {
    if (active.current) return;
    const failures: string[] = [], additions: ImageFile[] = [];
    for (const file of files) {
      const check = validateImageFile(file);
      if (!check.valid) failures.push(`${file.name}: ${check.error}`);
      else if (current.current.length + additions.length >= 50) failures.push(`${file.name}: el lote admite hasta 50 imágenes.`);
      else additions.push(createImageFile(file));
    }
    setErrors(failures); update(items => [...items, ...additions]);
    if (additions.length) { setProgress(null); log('INFO', `${additions.length} imágenes añadidas a la cola.`); }
  }, [update, log]);

  const remove = useCallback((id: string) => {
    const item = current.current.find(image => image.id === id);
    if (!item) return;
    URL.revokeObjectURL(item.preview); if (item.convertedUrl) URL.revokeObjectURL(item.convertedUrl);
    update(items => items.filter(image => image.id !== id)); log('INFO', `${item.name}: retirado de la cola.`);
  }, [update, log]);
  const clear = useCallback(() => {
    if (active.current) return;
    current.current.forEach(item => { URL.revokeObjectURL(item.preview); if (item.convertedUrl) URL.revokeObjectURL(item.convertedUrl); });
    update(() => []); setProgress(null); setErrors([]); setLogs([]);
  }, [update]);
  const rename = useCallback((id: string, name: string) => {
    update(items => items.map(item => item.id === id ? { ...item, customName: name.trim() || undefined } : item));
  }, [update]);

  const process = useCallback(async (only?: string) => {
    if (active.current || settingsError) return;
    const pending = current.current.filter(image => only ? image.id === only : image.status === 'pending');
    if (!pending.length) return;
    active.current = true; stop.current = false; setRunning(true); setCancelling(false); setErrors([]);
    const options = { ...settings }, mask = pattern;
    let done = 0;
    const quality = ['jpg', 'jpeg', 'webp', 'avif'].includes(options.format) ? `${options.quality}%` : 'sin pérdida';
    log('INFO', `Lote iniciado: ${pending.length} archivos → ${options.format.toUpperCase()} (${quality}).`);
    try {
      for (const image of pending) {
        if (stop.current || !mounted.current) break;
        if (!current.current.some(item => item.id === image.id)) { done++; continue; }
        setProgress({ current: done, total: pending.length, percentage: Math.round(done / pending.length * 100), currentFile: image.name });
        update(items => items.map(item => item.id === image.id ? { ...item, status: 'converting', error: undefined } : item));
        try {
          const result = await convertImage(image, options);
          if (stop.current || !mounted.current) break;
          if (current.current.some(item => item.id === image.id)) {
            const url = URL.createObjectURL(result);
            const name = outputName({ ...image, convertedBlob: undefined }, options.format, mask).replace(/\.[^.]+$/, '');
            update(items => items.map(item => {
              if (item.id !== image.id) return item;
              if (item.convertedUrl) URL.revokeObjectURL(item.convertedUrl);
              return { ...item, status: 'completed', convertedBlob: result, convertedUrl: url, convertedFormat: options.format, convertedName: name };
            }));
            log('OK', `${image.name} → ${name}.${options.format} (${formatFileSize(result.size)}).`);
          }
        } catch (error) {
          if (stop.current || !mounted.current) break;
          const message = error instanceof Error ? error.message : 'No se pudo convertir la imagen.';
          update(items => items.map(item => item.id === image.id ? { ...item, status: 'error', error: message } : item));
          log('ERROR', `${image.name}: ${message}`);
        }
        done++;
        if (mounted.current) setProgress({ current: done, total: pending.length, percentage: Math.round(done / pending.length * 100), currentFile: image.name });
        await new Promise(resolve => setTimeout(resolve, 0));
      }
      if (mounted.current) log('INFO', stop.current ? 'Lote detenido. Los archivos pendientes se conservan.' : 'Lote finalizado. Los resultados están listos para descargar.');
    } finally {
      active.current = false;
      if (mounted.current) {
        update(items => items.map(item => item.status === 'converting' ? { ...item, status: 'pending' } : item));
        setRunning(false); setCancelling(false);
      }
    }
  }, [settings, pattern, settingsError, update, log]);

  const cancel = () => { if (active.current) { stop.current = true; setCancelling(true); } };
  const download = (id: string) => {
    const image = current.current.find(item => item.id === id);
    if (image?.convertedBlob) downloadBlob(image.convertedBlob, outputName(image, settings.format, pattern));
  };
  const zip = async () => {
    const completed = current.current.filter(image => image.convertedBlob);
    if (!completed.length || exporting) return;
    setExporting(true);
    try { await downloadAsZip(completed, settings.format); log('OK', `ZIP preparado con ${completed.length} imágenes.`); }
    catch { setErrors(['No se pudo crear el ZIP. Inténtalo de nuevo.']); }
    finally { if (mounted.current) setExporting(false); }
  };
  return { images, settings, setSettings, pattern, setPattern, supported, running, cancelling, exporting,
    progress, errors, logs, settingsError, addFiles, remove, clear, rename, process, cancel, download, zip };
}
