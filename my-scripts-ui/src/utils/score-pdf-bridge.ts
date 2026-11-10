/** Browser entry point for audio-to-score; shares this app's SVG-to-PDF converter.
 * Build from my-scripts-ui:
 * bun run build:score-pdf
 */
import { buildMergedPdf, createSvgFile, sortSvgFilesByName, validateSvgFile } from './svg-to-pdf';
import type { PdfProgress } from '@/types/svg-to-pdf';

function inertSvg(content: string): string {
  const document = new DOMParser().parseFromString(content, 'image/svg+xml');
  if (document.querySelector('parsererror') || document.documentElement.localName !== 'svg') {
    throw new Error('This SVG could not be read. Try exporting it again.');
  }
  // SVGs are inserted into the DOM by the shared converter. Keep drawing content
  // and local symbol references, without executing scripts or fetching assets.
  document.querySelectorAll('script, foreignObject, iframe, object, embed').forEach(el => el.remove());
  for (const element of Array.from(document.querySelectorAll('*'))) {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.localName.toLowerCase();
      if (name === 'href' && !attribute.value.trim().startsWith('#') &&
          !/^data:image\/(png|jpeg|webp);base64,/i.test(attribute.value)) {
        if (element.localName !== 'a') {
          throw new Error('This SVG uses external assets. Export a self-contained vector sheet and try again.');
        }
        element.removeAttributeNode(attribute);
      } else if (name.startsWith('on') || name === 'base') {
        element.removeAttributeNode(attribute);
      }
    }
    const css = element.localName === 'style' ? element.textContent || '' : '';
    const attributes = Array.from(element.attributes).map(a => a.value).join(' ');
    const styles = css + ' ' + attributes;
    const externalUrl = Array.from(styles.matchAll(/url\(\s*(['"]?)(.*?)\1\s*\)/gi))
      .some(match => !match[2].trim().startsWith('#'));
    if (/@import/i.test(styles) || externalUrl) {
      throw new Error('This SVG uses external assets. Export a self-contained vector sheet and try again.');
    }
  }
  return new XMLSerializer().serializeToString(document);
}

export async function svgSheetsToPdf(files: File[], onProgress?: (progress: PdfProgress) => void): Promise<Blob> {
  if (!files.length || files.length > 30) throw new Error('Choose 1–30 SVG pages.');
  if (files.reduce((sum, file) => sum + file.size, 0) > 50 * 1024 * 1024) {
    throw new Error('These SVG files are larger than 50 MB together.');
  }
  const pages = [];
  try {
    for (const file of files) {
      const check = validateSvgFile(file);
      if (!check.valid) throw new Error('Choose SVG files smaller than 25 MB each.');
      const svg = await createSvgFile(file);
      pages.push(svg);
      svg.content = inertSvg(svg.content);
    }
    // Natural filename ordering and intrinsic page sizes match the original SVGs.
    return await buildMergedPdf(sortSvgFilesByName(pages),
      { pageSize: 'auto', margin: 0, fileName: 'sheet' }, onProgress);
  } finally {
    pages.forEach(page => URL.revokeObjectURL(page.preview));
  }
}
