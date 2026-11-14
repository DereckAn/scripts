'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import JSZip from 'jszip';
import { Archive, ArrowRight, Check, CheckCircle2, Clipboard, Code2, Download, FileText,
  History, Layers3, Search, Settings2, Terminal, X } from 'lucide-react';
import WorkspaceShell from '@/components/dashboard/WorkspaceShell';
import AppSelector from '@/components/AppSelector';
import { CATEGORIES, DEFAULT_OPTIONS, HISTORY_KEY, OPTIONS, SYSTEMS, configKey, readHistory, type Artifact } from '@/components/script-generator/config';
import type { OperatingSystem, ScriptConfig } from '@/types/script-generator';
import { generateInstallScript, generateReadme, getAvailableApps, getInstallCommand } from '@/utils/script-generator';
import { downloadBlob, formatFileSize } from '@/utils/image-converter';
import styles from './generator.module.css';

const normalize = (text: string) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

export default function GenerateScriptsPage() {
  const [os, setOS] = useState<OperatingSystem>('ubuntu');
  const [selected, setSelected] = useState<string[]>([]);
  const [options, setOptions] = useState({ ...DEFAULT_OPTIONS });
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [tab, setTab] = useState<'script' | 'readme'>('script');
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [history, setHistory] = useState<Artifact[]>([]);
  const [copied, setCopied] = useState('');
  const [error, setError] = useState('');
  const [packing, setPacking] = useState(false);
  const historyDialog = useRef<HTMLDialogElement>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    try { setHistory(readHistory(localStorage.getItem(HISTORY_KEY))); } catch { /* History is optional. */ }
    return () => { if (copyTimer.current) clearTimeout(copyTimer.current); };
  }, []);

  const available = useMemo(() => getAvailableApps(os), [os]);
  const filtered = useMemo(() => available.filter(app => (category === 'all' || category === app.category) &&
    normalize(`${app.name} ${app.description} ${getInstallCommand(app, os)}`).includes(normalize(query.trim()))), [available, category, query, os]);
  const config: ScriptConfig = useMemo(() => ({ os, selectedApps: selected, options }), [os, selected, options]);
  const signature = configKey(config);
  const compiled = !!artifact && configKey(artifact.config) === signature;
  const draft = useMemo(() => selected.length ? { script: generateInstallScript(config), readme: generateReadme(config) } : null, [config, selected.length]);
  const preview = compiled ? artifact : draft;
  const code = preview ? preview[tab] : '';
  const system = SYSTEMS.find(item => item.id === os)!;
  const scriptName = `install-script-${os}.sh`, readmeName = `README-${os}.md`;
  const quickCommand = `chmod +x ${scriptName} && ./${scriptName}`;
  const bytes = preview ? new TextEncoder().encode(preview.script).length : 0;
  const lineCount = preview ? preview.script.trimEnd().split('\n').length : 0;

  const changeOS = (next: OperatingSystem) => {
    const compatible = new Set(getAvailableApps(next).map(app => app.id));
    setOS(next); setSelected(prev => prev.filter(id => compatible.has(id))); setError('');
  };
  const toggleApp = (id: string) => setSelected(prev => prev.includes(id) ? prev.filter(value => value !== id) : [...prev, id]);
  const generate = () => {
    if (!selected.length) return;
    const result: Artifact = { id: crypto.randomUUID(), createdAt: new Date().toISOString(),
      config: { os, selectedApps: [...selected], options: { ...options } },
      script: generateInstallScript(config), readme: generateReadme(config) };
    setArtifact(result); setError('');
    const next = [result, ...history.filter(item => configKey(item.config) !== signature)].slice(0, 5);
    setHistory(next);
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(next)); } catch { /* Keep this session's history. */ }
  };
  const copy = async (text: string, which: string) => {
    try {
      await navigator.clipboard.writeText(text); setCopied(which); setError('');
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(''), 1800);
    } catch { setError('No se pudo copiar al portapapeles. Puedes seleccionar el texto o descargar el archivo.'); }
  };
  const download = (kind: 'script' | 'readme') => {
    if (!compiled || !artifact) return;
    downloadBlob(new Blob([artifact[kind]], { type: kind === 'script' ? 'text/x-shellscript;charset=utf-8' : 'text/markdown;charset=utf-8' }), kind === 'script' ? scriptName : readmeName);
  };
  const bundle = async () => {
    if (!compiled || !artifact || packing) return;
    const snapshot = artifact, target = snapshot.config.os;
    setPacking(true);
    try {
      const zip = new JSZip();
      zip.file(`install-script-${target}.sh`, snapshot.script);
      zip.file(`README-${target}.md`, snapshot.readme);
      downloadBlob(await zip.generateAsync({ type: 'blob' }), `setup-${target}.zip`);
    } catch { setError('No se pudo preparar el paquete ZIP. Inténtalo de nuevo.'); }
    finally { setPacking(false); }
  };
  const restore = (item: Artifact) => {
    setOS(item.config.os); setSelected([...item.config.selectedApps]); setOptions({ ...item.config.options });
    setArtifact(item); setError(''); historyDialog.current?.close();
  };
  const steps = [
    { target: 'target-system', title: 'Sistema operativo', ready: true },
    { target: 'package-picker', title: 'Selección de paquetes', ready: selected.length > 0 },
    { target: 'system-options', title: 'Opciones y dotfiles', ready: selected.length > 0 },
    { target: 'script-output', title: 'Generación de script', ready: compiled },
  ];

  return (
    <WorkspaceShell title="Scripts" mainId="generator-main" sectionHref="#script-output" sectionLabel="Vista previa">
      <div className={styles.generator}>
        <section className={`${styles.panel} ${styles.hero}`} aria-labelledby="generator-title">
          <div className={styles.heroTop}><div><div className={styles.eyebrow}><span>Automatización personal</span><span><CheckCircle2 size={12} />{selected.length ? 'Configuración lista' : 'Selecciona tus paquetes'}</span></div><h1 id="generator-title">Generador de Scripts de Instalación &amp; Dotfiles</h1><p>Elige tu sistema, selecciona las aplicaciones y prepara tu entorno. Revisa el script antes de descargarlo para ejecutarlo en el equipo de destino.</p></div>
            <div className={styles.heroActions}><button type="button" className={styles.secondaryButton} onClick={() => historyDialog.current?.showModal()}><History size={15} />Historial ({history.length})</button><button type="button" className={styles.primaryButton} disabled={!selected.length} onClick={generate}><Terminal size={16} />Compilar script</button></div></div>
          <nav className={styles.steps} aria-label="Pasos de configuración">{steps.map((step, index) => <a href={`#${step.target}`} key={step.target} className={step.ready ? styles.stepReady : undefined}><span className={styles.stepNumber}>{index + 1}</span><span><small>Paso {index + 1}</small><strong>{step.title}</strong></span>{step.ready && <CheckCircle2 size={16} aria-hidden="true" />}</a>)}</nav>
        </section>
        {error && <p role="alert" className={styles.alert}>{error}</p>}
        <div className={styles.workspaceGrid}>
          <div className={styles.configuration}>
            <section id="target-system" className={styles.panel} aria-labelledby="system-heading">
              <div className={styles.sectionHeading}><span className={styles.sectionNumber}>01</span><div><h2 id="system-heading">Sistema operativo destino</h2><p>Selecciona el sistema y su gestor de paquetes.</p></div></div>
              <div className={styles.osGrid} role="radiogroup" aria-label="Sistema operativo destino">{SYSTEMS.map(item => <label key={item.id} className={`${styles.osCard} ${os === item.id ? styles.osSelected : ''}`}><input type="radio" name="target-os" value={item.id} checked={os === item.id} onChange={() => changeOS(item.id)} aria-label={item.name} /><item.icon size={24} aria-hidden="true" /><strong>{item.name}</strong><code>{item.manager}</code><small>{item.detail}</small></label>)}</div>
            </section>
            <section id="package-picker" className={styles.panel} aria-labelledby="packages-heading">
              <div className={styles.packageHeader}><div className={styles.sectionHeading}><span className={styles.sectionNumber}>02</span><div><h2 id="packages-heading">Selección de paquetes y software</h2><p aria-live="polite">{selected.length} seleccionados · {available.length} disponibles para {system.name}</p></div></div><div className={styles.bulkActions}><button type="button" onClick={() => setSelected(prev => [...new Set([...prev, ...filtered.map(app => app.id)])])} disabled={!filtered.length}>Marcar visibles</button><button type="button" disabled={!selected.length} onClick={() => setSelected([])}>Desmarcar todo</button></div></div>
              <div className={styles.searchField}><Search size={16} aria-hidden="true" /><input type="search" aria-label="Buscar paquetes" placeholder="Buscar paquetes, aplicaciones o comandos…" value={query} onChange={event => setQuery(event.target.value)} /></div>
              <div className={styles.categories} role="group" aria-label="Categorías de paquetes"><button type="button" aria-pressed={category === 'all'} onClick={() => setCategory('all')}>Todos ({selected.length})</button>{CATEGORIES.map(item => <button type="button" aria-pressed={category === item.id} onClick={() => setCategory(item.id)} key={item.id}>{item.name}</button>)}</div>
              <div className={styles.packageGrid} aria-label="Aplicaciones disponibles">{filtered.map(app => <AppSelector key={app.id} app={app} selectedOS={os} isSelected={selected.includes(app.id)} onToggle={toggleApp} />)}{!filtered.length && <div className={styles.emptyPackages}><Search size={24} aria-hidden="true" /><strong>No encontramos paquetes con ese filtro.</strong><button type="button" onClick={() => { setQuery(''); setCategory('all'); }}>Mostrar todos</button></div>}</div>
            </section>
            <section id="system-options" className={styles.panel} aria-labelledby="options-heading"><div className={styles.sectionHeading}><span className={styles.sectionNumber}>03</span><div><h2 id="options-heading">Opciones del sistema y automatización</h2><p>Elige qué instrucciones incluir en tu script.</p></div></div><div className={styles.optionList}>{OPTIONS.map(option => <label key={option.key} className={styles.optionCard}><input type="checkbox" checked={options[option.key]} onChange={event => setOptions(prev => ({ ...prev, [option.key]: event.target.checked }))} /><span><strong>{option.title}</strong><span>{option.description}</span></span></label>)}</div></section>
          </div>
          <aside id="script-output" className={`${styles.panel} ${styles.output}`} aria-labelledby="output-heading">
            <div className={styles.sectionHeading}><span className={styles.sectionNumber}>04</span><div><h2 id="output-heading">Generación y salida de script</h2><p>Revisa, genera y descarga tu configuración.</p></div></div>
            <div className={styles.summary}><div className={styles.summaryHeading}><span><CheckCircle2 size={15} />{compiled ? 'Script generado' : selected.length ? 'Vista previa actualizada' : 'Configura tu script'}</span><small>{system.name}</small></div><div className={styles.metrics}><div><small>Paquetes</small><strong>{selected.length}</strong></div><div><small>Líneas Bash</small><strong>{lineCount}</strong></div><div><small>Tamaño</small><strong>{formatFileSize(bytes)}</strong></div></div></div>
            <div className={styles.quickRun}><span>Comando de ejecución local</span><div><code>{quickCommand}</code><button type="button" disabled={!compiled} onClick={() => void copy(quickCommand, 'command')} title="Copiar comando" aria-label="Copiar comando">{copied === 'command' ? <Check size={16} /> : <Clipboard size={16} />}</button></div></div>
            <div className={styles.inspectorHeader}><div className={styles.tabs} role="tablist" aria-label="Archivo a inspeccionar" onKeyDown={event => { if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const next = event.key === 'Home' ? 'script' : event.key === 'End' ? 'readme' : tab === 'script' ? 'readme' : 'script'; setTab(next); document.getElementById(`${next}-tab`)?.focus(); } }}><button type="button" id="script-tab" role="tab" aria-selected={tab === 'script'} aria-controls="code-panel" tabIndex={tab === 'script' ? 0 : -1} onClick={() => setTab('script')}>install.sh</button><button type="button" id="readme-tab" role="tab" aria-selected={tab === 'readme'} aria-controls="code-panel" tabIndex={tab === 'readme' ? 0 : -1} onClick={() => setTab('readme')}>README.md</button></div><div className={styles.inspectorActions}><button type="button" disabled={!preview} onClick={() => void copy(code, 'code')} aria-label="Copiar código" title="Copiar código">{copied === 'code' ? <Check size={17} /> : <Clipboard size={17} />}</button><button type="button" disabled={!compiled} onClick={() => download(tab)} aria-label="Descargar archivo de la vista previa" title="Descargar archivo"><Download size={17} /></button></div></div>
            <div className={styles.codeWindow}><div className={styles.codeTitle}><span className={styles.windowDots} aria-hidden="true"><i /><i /><i /></span><span>{tab === 'script' ? 'Bash' : 'Markdown'} · UTF-8</span><span>{compiled ? 'Generado' : 'Borrador'}</span></div><pre id="code-panel" role="tabpanel" aria-labelledby={`${tab}-tab`} tabIndex={0} className={styles.codePanel}><code>{code ? code.split('\n').map((line, i) => <span className={`${styles.codeLine} ${line.trim().startsWith('#') ? styles.commentLine : ''}`} key={i}><span className={styles.lineNumber} aria-hidden="true">{i + 1}</span><span>{line || ' '}</span></span>) : <span className={styles.previewPlaceholder}>Selecciona al menos una aplicación para ver el script y su documentación.</span>}</code></pre></div>
            {artifact && !compiled && <p className={styles.staleNotice}>La configuración cambió. Genera de nuevo para actualizar las descargas.</p>}
            <div className={styles.outputActions}><button type="button" className={styles.primaryButton} disabled={!selected.length} onClick={generate}><Terminal size={17} />Generar script y documentación</button><div><button type="button" className={styles.secondaryButton} disabled={!compiled} onClick={() => download('script')}><Download size={15} />install.sh</button><button type="button" className={styles.secondaryButton} disabled={!compiled || packing} onClick={() => void bundle()}><Archive size={15} />{packing ? 'Preparando…' : 'Paquete (.ZIP)'}</button></div><button type="button" className={styles.readmeDownload} disabled={!compiled} onClick={() => download('readme')}><FileText size={13} />Descargar README.md</button></div>
            <p className={styles.outputHint} role="status">{copied ? 'Copiado al portapapeles.' : compiled ? 'Archivos listos. La generación no ejecuta comandos en tu equipo.' : 'La vista previa refleja tus opciones. Genera los archivos cuando estén listos.'}</p>
          </aside>
        </div>
        <section className={styles.bento} aria-label="Acerca del generador">{[{ icon: Code2, title: 'Vista previa al instante', text: 'Comprueba los comandos reales del catálogo mientras ajustas tu selección.' }, { icon: Settings2, title: 'Configuración a tu medida', text: 'Elige aplicaciones, actualizaciones, backups, aliases y opciones de Oh My Zsh.' }, { icon: Layers3, title: 'Cuatro sistemas, un flujo', text: 'Conserva la misma forma de trabajo con Homebrew, APT, DNF y Pacman.' }].map(item => <div key={item.title}><item.icon size={20} aria-hidden="true" /><h3>{item.title}</h3><p>{item.text}</p></div>)}</section>
        <dialog ref={historyDialog} className={styles.historyDialog} aria-labelledby="history-title" onClick={event => { if (event.target === event.currentTarget) historyDialog.current?.close(); }}><div className={styles.historyContent}><div className={styles.historyHeading}><h2 id="history-title">Configuraciones generadas</h2><button type="button" onClick={() => historyDialog.current?.close()} aria-label="Cerrar historial"><X size={20} /></button></div><p>Últimas cinco configuraciones guardadas en este navegador.</p>{history.length ? history.map(item => <button className={styles.historyItem} type="button" key={item.id} onClick={() => restore(item)}><Terminal size={18} aria-hidden="true" /><span><strong>{SYSTEMS.find(system => system.id === item.config.os)?.name} · {item.config.selectedApps.length} aplicaciones</strong><small>{new Date(item.createdAt).toLocaleString('es-MX')}</small></span><ArrowRight size={16} aria-hidden="true" /></button>) : <div className={styles.emptyHistory}><History size={27} aria-hidden="true" /><strong>Todavía no hay configuraciones guardadas.</strong><p>Genera tu primer script para añadirlo al historial.</p></div>}</div></dialog>
      </div>
    </WorkspaceShell>
  );
}
