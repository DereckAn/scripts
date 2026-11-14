'use client';

import { LockKeyhole, Settings2, ShieldCheck, Type } from 'lucide-react';
import type { ConversionSettings, ImageFormat } from '@/types/image-converter';
import { OUTPUT_FORMATS } from '@/types/image-converter';
import styles from '@/app/convert-images/converter.module.css';

export default function ConversionSettingsComponent({ settings, onChange, supported, disabled,
  pattern, onPatternChange }: {
  settings: ConversionSettings; onChange: (settings: ConversionSettings) => void;
  supported: ImageFormat[]; disabled: boolean; pattern: string; onPatternChange: (pattern: string) => void;
}) {
  const formats = ['webp', 'jpg', 'png', 'avif', 'tiff', 'bmp', 'gif', 'ico'] as ImageFormat[];
  const transparent = OUTPUT_FORMATS.find(item => item.value === settings.format)?.supportsTransparency ?? false;
  const qualityEnabled = ['jpg', 'jpeg', 'webp', 'avif'].includes(settings.format);
  const background = !transparent || !!settings.flattenTransparency;
  return (
    <fieldset disabled={disabled} className={`${styles.panel} ${styles.settings}`}>
      <legend className={styles.srOnly}>Configuración de salida</legend>
      <div className={styles.panelHeading}><Settings2 size={19} aria-hidden="true" /><h2>Configuración de salida</h2><span>{settings.format.toUpperCase()}</span></div>
      <div className={styles.settingGroup}>
        <span className={styles.fieldTitle}>Formato destino</span>
        <div className={styles.formats} role="group" aria-label="Formato destino">
          {formats.map(format => <button key={format} type="button" aria-pressed={settings.format === format}
            disabled={!supported.includes(format)} onClick={() => onChange({ ...settings, format })}
            title={supported.includes(format) ? `Exportar ${format.toUpperCase()}` : `${format.toUpperCase()}: no disponible en este navegador`}
            className={settings.format === format ? styles.selectedFormat : undefined}>{format === 'jpg' ? 'JPEG' : format.toUpperCase()}</button>)}
        </div>
        <p className={styles.hint}>Los formatos disponibles dependen de la capacidad de exportación de tu navegador.</p>
      </div>
      <div className={styles.qualityBox}>
        <label htmlFor="image-quality">Calidad de compresión <strong>{qualityEnabled ? `${settings.quality}%` : 'Sin pérdida'}</strong></label>
        <input id="image-quality" type="range" min="1" max="100" value={settings.quality} disabled={!qualityEnabled}
          onChange={e => onChange({ ...settings, quality: Number(e.target.value) })} />
        <div className={styles.rangeLabels}><span>Menor tamaño</span><span>Mayor calidad</span></div>
      </div>
      <div className={styles.settingGroup}>
        <div className={styles.settingLabel}><span className={styles.fieldTitle}>Dimensiones de salida</span><LockKeyhole size={14} aria-hidden="true" /></div>
        <div className={styles.dimensions}>
          <label htmlFor="image-width">Ancho máx. (px)<input id="image-width" type="number" min="1" max="16384" placeholder="Original" value={settings.width ?? ''} onChange={e => onChange({ ...settings, width: e.target.value === '' ? undefined : Number(e.target.value) })} /></label>
          <label htmlFor="image-height">Alto máx. (px)<input id="image-height" type="number" min="1" max="16384" placeholder="Original" value={settings.height ?? ''} onChange={e => onChange({ ...settings, height: e.target.value === '' ? undefined : Number(e.target.value) })} /></label>
        </div>
        <label className={styles.checkLabel}><input type="checkbox" checked={settings.maintainAspectRatio} onChange={e => onChange({ ...settings, maintainAspectRatio: e.target.checked })} /><span>Mantener relación de aspecto</span></label>
      </div>
      <div className={styles.settingGroup}>
        <span className={styles.fieldTitle}>Optimización y privacidad</span>
        <div className={styles.privacy}><ShieldCheck size={18} aria-hidden="true" /><div><strong>Sin metadatos EXIF / GPS</strong><p>La conversión vuelve a codificar la imagen y no transfiere los metadatos originales.</p></div></div>
        <div className={styles.backgroundBox}>
          <label className={styles.checkLabel}><input type="checkbox" checked={background} disabled={!transparent} onChange={e => onChange({ ...settings, flattenTransparency: e.target.checked })} /><span>Rellenar fondo transparente</span></label>
          {background && <label className={styles.colorField}><input aria-label="Color de fondo" type="color" value={settings.backgroundColor || '#ffffff'} onChange={e => onChange({ ...settings, backgroundColor: e.target.value })} /><span>{settings.backgroundColor?.toUpperCase()}</span></label>}
          {!transparent && <p className={styles.hint}>El formato seleccionado necesita un fondo sólido.</p>}
        </div>
      </div>
      <div className={styles.settingGroup}>
        <label htmlFor="filename-pattern" className={styles.fieldTitle}>Máscara de archivo</label>
        <div className={styles.patternInput}><Type size={15} aria-hidden="true" /><input id="filename-pattern" value={pattern} maxLength={160} onChange={e => onPatternChange(e.target.value)} spellCheck={false} /></div>
        <p className={styles.hint}>Tokens: {'{name}'} o {'{filename}'}, {'{ext}'}. También puedes renombrar cada archivo.</p>
      </div>
    </fieldset>
  );
}
