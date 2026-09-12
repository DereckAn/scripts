import JSZip from 'jszip';
import { jsPDF } from 'jspdf';
import 'svg2pdf.js';
import {
  MAX_SVG_SIZE,
  PAGE_SIZES_MM,
  PdfProgress,
  PdfSettings,
  SvgFile,
} from '@/types/svg-to-pdf';

/** CSS pixels to PostScript points (96dpi -> 72dpi). */
const PX_TO_PT = 72 / 96;

export function validateSvgFile(file: File): { valid: boolean; error?: string } {
  const isSvg = file.type === 'image/svg+xml' || file.name.toLowerCase().endsWith('.svg');
  if (!isSvg) {
    return { valid: false, error: 'El archivo no es un SVG' };
  }
  if (file.size > MAX_SVG_SIZE) {
    return { valid: false, error: 'Archivo demasiado grande (máximo 25MB)' };
  }
  return { valid: true };
}

/**
 * Compares file names the way a person would: the numbers inside them are
 * compared as numbers, so `score_2` comes before `score_10`.
 */
export function naturalCompare(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
}

export function sortSvgFilesByName(files: SvgFile[]): SvgFile[] {
  return [...files].sort((a, b) => naturalCompare(a.name, b.name));
}

export function moveSvgFile(files: SvgFile[], from: number, to: number): SvgFile[] {
  if (to < 0 || to >= files.length || from === to) return files;
  const reordered = [...files];
  const [moved] = reordered.splice(from, 1);
  reordered.splice(to, 0, moved);
  return reordered;
}

/**
 * Reads the intrinsic size of an SVG from its width/height attributes, falling
 * back to the viewBox. Returns A4 at 96dpi when nothing usable is found.
 */
export function parseSvgDimensions(content: string): { width: number; height: number } {
  const fallback = { width: 794, height: 1123 };
  const doc = new DOMParser().parseFromString(content, 'image/svg+xml');
  const svg = doc.documentElement;

  if (!svg || svg.nodeName !== 'svg' || doc.querySelector('parsererror')) {
    return fallback;
  }

  const width = parseLength(svg.getAttribute('width'));
  const height = parseLength(svg.getAttribute('height'));
  if (width && height) {
    return { width, height };
  }

  const viewBox = svg.getAttribute('viewBox');
  if (viewBox) {
    const parts = viewBox.split(/[\s,]+/).map(Number);
    if (parts.length === 4 && parts[2] > 0 && parts[3] > 0) {
      return { width: parts[2], height: parts[3] };
    }
  }

  return fallback;
}

/** Parses an SVG length such as "2976.38", "210mm" or "8.5in" into pixels. */
function parseLength(value: string | null): number | null {
  if (!value) return null;
  const match = value.trim().match(/^(-?[\d.]+)\s*([a-z%]*)$/i);
  if (!match) return null;

  const amount = parseFloat(match[1]);
  if (!Number.isFinite(amount) || amount <= 0) return null;

  const unitsPerPx: Record<string, number> = {
    '': 1,
    px: 1,
    pt: 96 / 72,
    pc: 16,
    mm: 96 / 25.4,
    cm: 96 / 2.54,
    in: 96,
  };

  const factor = unitsPerPx[match[2].toLowerCase()];
  return factor ? amount * factor : null;
}

export async function createSvgFile(file: File): Promise<SvgFile> {
  const content = await file.text();
  const { width, height } = parseSvgDimensions(content);

  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
    file,
    name: file.name,
    size: file.size,
    preview: URL.createObjectURL(file),
    content,
    width,
    height,
  };
}

/**
 * Builds a detached SVG element that svg2pdf can measure. A viewBox is added
 * when the source lacks one so the drawing scales to the requested size
 * instead of being cropped.
 */
function toSvgElement(svgFile: SvgFile): SVGSVGElement {
  const doc = new DOMParser().parseFromString(svgFile.content, 'image/svg+xml');
  if (doc.querySelector('parsererror') || doc.documentElement.nodeName !== 'svg') {
    throw new Error('El SVG no se pudo leer (formato inválido)');
  }

  const element = doc.documentElement as unknown as SVGSVGElement;
  if (!element.getAttribute('viewBox')) {
    element.setAttribute('viewBox', `0 0 ${svgFile.width} ${svgFile.height}`);
  }
  element.setAttribute('width', String(svgFile.width));
  element.setAttribute('height', String(svgFile.height));

  return element;
}

/** svg2pdf needs the element laid out by the browser, so it renders off-screen. */
function createOffscreenHost(): HTMLDivElement {
  const host = document.createElement('div');
  host.setAttribute('aria-hidden', 'true');
  host.style.cssText = 'position:fixed;left:-99999px;top:0;width:0;height:0;overflow:hidden;';
  document.body.appendChild(host);
  return host;
}

interface PageLayout {
  pageWidth: number;
  pageHeight: number;
  orientation: 'portrait' | 'landscape';
}

function pageLayoutFor(svgFile: SvgFile, settings: PdfSettings): PageLayout {
  const orientation = svgFile.width > svgFile.height ? 'landscape' : 'portrait';

  if (settings.pageSize === 'auto') {
    return {
      pageWidth: svgFile.width * PX_TO_PT,
      pageHeight: svgFile.height * PX_TO_PT,
      orientation,
    };
  }

  const { width, height } = PAGE_SIZES_MM[settings.pageSize];
  return {
    pageWidth: orientation === 'landscape' ? height : width,
    pageHeight: orientation === 'landscape' ? width : height,
    orientation,
  };
}

/** Centers the drawing on the page, scaled down to fit inside the margins. */
function placementFor(svgFile: SvgFile, doc: jsPDF, settings: PdfSettings) {
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = settings.pageSize === 'auto' ? 0 : Math.max(0, settings.margin);

  const availableWidth = Math.max(1, pageWidth - margin * 2);
  const availableHeight = Math.max(1, pageHeight - margin * 2);

  const scale = Math.min(availableWidth / svgFile.width, availableHeight / svgFile.height);
  const width = svgFile.width * scale;
  const height = svgFile.height * scale;

  return {
    x: (pageWidth - width) / 2,
    y: (pageHeight - height) / 2,
    width,
    height,
  };
}

function createDocument(svgFile: SvgFile, settings: PdfSettings): jsPDF {
  const layout = pageLayoutFor(svgFile, settings);
  return new jsPDF({
    unit: settings.pageSize === 'auto' ? 'pt' : 'mm',
    format: [layout.pageWidth, layout.pageHeight],
    orientation: layout.orientation,
    compress: true,
  });
}

async function drawPage(doc: jsPDF, svgFile: SvgFile, settings: PdfSettings, host: HTMLElement) {
  const element = toSvgElement(svgFile);
  host.appendChild(element);
  try {
    await doc.svg(element, placementFor(svgFile, doc, settings));
  } finally {
    host.removeChild(element);
  }
}

/**
 * Renders every SVG, in the given order, as one page of a single PDF. The
 * paths stay vectors, so the result prints sharp at any size.
 */
export async function buildMergedPdf(
  files: SvgFile[],
  settings: PdfSettings,
  onProgress?: (progress: PdfProgress) => void
): Promise<Blob> {
  if (files.length === 0) {
    throw new Error('No hay archivos SVG para convertir');
  }

  const host = createOffscreenHost();
  try {
    const doc = createDocument(files[0], settings);

    for (let index = 0; index < files.length; index++) {
      const svgFile = files[index];

      onProgress?.({
        current: index + 1,
        total: files.length,
        percentage: Math.round(((index + 1) / files.length) * 100),
        currentFile: svgFile.name,
      });

      if (index > 0) {
        const layout = pageLayoutFor(svgFile, settings);
        doc.addPage([layout.pageWidth, layout.pageHeight], layout.orientation);
      }

      await drawPage(doc, svgFile, settings, host);
    }

    return doc.output('blob');
  } finally {
    host.remove();
  }
}

/** Renders each SVG as its own single-page PDF. */
export async function buildIndividualPdfs(
  files: SvgFile[],
  settings: PdfSettings,
  onProgress?: (progress: PdfProgress) => void
): Promise<Array<{ name: string; blob: Blob }>> {
  const host = createOffscreenHost();
  try {
    const results: Array<{ name: string; blob: Blob }> = [];

    for (let index = 0; index < files.length; index++) {
      const svgFile = files[index];

      onProgress?.({
        current: index + 1,
        total: files.length,
        percentage: Math.round(((index + 1) / files.length) * 100),
        currentFile: svgFile.name,
      });

      const doc = createDocument(svgFile, settings);
      await drawPage(doc, svgFile, settings, host);
      results.push({ name: toPdfName(svgFile.name), blob: doc.output('blob') });
    }

    return results;
  } finally {
    host.remove();
  }
}

export async function createPdfZip(pdfs: Array<{ name: string; blob: Blob }>): Promise<Blob> {
  const zip = new JSZip();
  pdfs.forEach((pdf, index) => {
    // Prefix with the position so the order survives outside this page.
    const prefix = String(index + 1).padStart(2, '0');
    zip.file(`${prefix}-${pdf.name}`, pdf.blob);
  });
  return zip.generateAsync({ type: 'blob' });
}

export function toPdfName(name: string): string {
  return `${name.replace(/\.svg$/i, '')}.pdf`;
}

export function sanitizeFileName(name: string): string {
  const cleaned = name.trim().replace(/\.pdf$/i, '').replace(/[\\/:*?"<>|]/g, '-');
  return cleaned.length > 0 ? cleaned : 'partitura';
}

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, exponent);
  return `${value.toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}
