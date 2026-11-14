'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, BookOpen, Check, ChevronRight, CircleHelp, FileDown, FolderOpen,
  Layers3, Monitor, Search, Settings2, Terminal } from 'lucide-react';
import WorkspaceShell from './WorkspaceShell';
import styles from '@/app/dashboard-theme.module.css';
import { tools } from './tools';

const normalized = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const categories = ['Todos', 'Medios', 'Extracción', 'Sistema', 'Social', 'IA local', 'Música'];

export default function Dashboard() {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('Todos');
  const search = useRef<HTMLInputElement>(null);
  const focusSearch = useCallback(() => search.current?.focus(), []);
  const visibleTools = useMemo(() => tools.filter(tool =>
    (category === 'Todos' || category === tool.category) &&
    normalized([tool.title, tool.description, tool.category, tool.href, ...tool.features].join(' ')).includes(normalized(query.trim()))
  ), [query, category]);

  return (
    <WorkspaceShell mainId="dashboard-main" onSearch={focusSearch}>
          <section className={styles.hero} aria-labelledby="dashboard-title">
            <div className={styles.heroRow}>
              <div className={styles.heroCopy}>
                <div className={styles.eyebrow}><span className={styles.pill}><span className={styles.statusDot} />Tu caja de herramientas</span><span>Medios · Código · Automatización</span></div>
                <h1 id="dashboard-title">Panel de Utilidades</h1>
                <p>Un espacio para convertir, extraer, crear y automatizar. Elige tu próxima tarea y encuentra aquí la herramienta para resolverla.</p>
              </div>
              <div className={styles.searchArea}>
                <label htmlFor="dashboard-search">Acceso rápido global</label>
                <div className={styles.searchField}><Search size={17} aria-hidden="true" /><input ref={search} id="dashboard-search" type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Buscar herramientas o formatos…" /><kbd>⌘K</kbd></div>
              </div>
            </div>
            <div className={styles.metrics}>
              <div className={styles.metric}><span className={styles.metricIcon}><Layers3 size={21} /></span><div><small>Utilidades</small><strong>{tools.length} herramientas disponibles</strong></div></div>
              <div className={styles.metric}><span className={styles.metricIcon}><Monitor size={21} /></span><div><small>IA local</small><strong>Ollama / LM Studio</strong></div></div>
              <div className={styles.metric}><span className={styles.metricIcon}><Terminal size={21} /></span><div><small>Automatización</small><strong>macOS y Linux</strong></div></div>
              <div className={styles.metric}><span className={styles.metricIcon}><FileDown size={21} /></span><div><small>Exportación</small><strong>PDF · ZIP · JSON · CSV</strong></div></div>
            </div>
          </section>
          <section id="herramientas" aria-labelledby="tools-heading" className={styles.toolsSection}>
            <div className={styles.sectionHeading}>
              <div><span className={styles.headingMark} /><h2 id="tools-heading">Herramientas</h2><span className={styles.available} aria-live="polite">{visibleTools.length} disponibles</span></div>
              <label className={styles.filter}><Settings2 size={14} aria-hidden="true" /><span>Mostrar:</span><select aria-label="Filtrar herramientas" value={category} onChange={e => setCategory(e.target.value)}>{categories.map(item => <option key={item}>{item}</option>)}</select></label>
            </div>
            <div className={styles.toolGrid}>
              {visibleTools.map(tool => {
                const Icon = tool.icon; const featured = tool.href === '/svg-to-pdf';
                return <article className={`${styles.toolCard} ${featured ? styles.featured : ''}`} key={tool.href}>
                  <div className={styles.cardContent}>
                    <div className={styles.cardTop}><span className={styles.toolIcon}><Icon size={25} aria-hidden="true" /></span><span className={styles.category}>{tool.category}</span></div>
                    <div><h3>{tool.title}</h3><span className={styles.route}>{tool.href}</span></div>
                    <p>{tool.description}</p>
                    <ul className={styles.features}>{tool.features.map(feature => <li key={feature}><Check size={12} aria-hidden="true" />{feature}</li>)}</ul>
                  </div>
                  <div className={styles.cardFooter}><span>{tool.detail}</span><Link href={tool.href}>{tool.action}<ArrowRight size={15} aria-hidden="true" /></Link></div>
                </article>;
              })}
              {!visibleTools.length && <div className={styles.emptyState}><Search size={26} aria-hidden="true" /><h3>No encontramos esa herramienta</h3><p>Prueba otro nombre, formato o categoría.</p><button type="button" onClick={() => { setQuery(''); setCategory('Todos'); search.current?.focus(); }}>Ver todas las herramientas</button></div>}
            </div>
          </section>
          <section className={styles.bottomGrid} aria-label="Accesos del workspace">
            <div className={styles.shortcuts}>
              <div className={styles.boxHeading}><FolderOpen size={19} aria-hidden="true" /><h2>Empieza por una tarea</h2><span>Accesos directos</span></div>
              {[
                { path: '/convert-images', title: 'Preparar imágenes para tu próximo proyecto', detail: 'Formatos, dimensiones y calidad', icon: tools[0].icon },
                { path: '/generate-scripts', title: 'Configurar un nuevo entorno de trabajo', detail: 'Aplicaciones y scripts de instalación', icon: Terminal },
                { path: '/svg-to-pdf', title: 'Reunir las páginas de una partitura', detail: 'Páginas SVG en un solo PDF', icon: tools[6].icon },
              ].map(item => <Link href={item.path} key={item.path} className={styles.shortcut}><span className={styles.shortcutIcon}><item.icon size={18} aria-hidden="true" /></span><span><strong>{item.title}</strong><small>{item.detail}</small></span><ChevronRight size={16} aria-hidden="true" /></Link>)}
            </div>
            <aside className={styles.workspaceNote}>
              <div className={styles.boxHeading}><BookOpen size={19} aria-hidden="true" /><h2>Tu espacio, a tu ritmo</h2></div>
              <p>Abre cada herramienta para configurar sus opciones, procesar tus archivos y descargar los resultados.</p>
              <div className={styles.noteInset}><CircleHelp size={18} aria-hidden="true" /><span>Los requisitos y ajustes de conexión se encuentran dentro de cada utilidad.</span></div>
              <span className={styles.noteFooter}>Todo empieza con una tarea.</span>
            </aside>
          </section>
          <footer className={styles.footer}><span>My Scripts UI</span><span>Una caja de herramientas. Muchas posibilidades.</span><span className={styles.footerSwatches} aria-label="Paleta azul petróleo, azul, arena y crema"><i /><i /><i /><i /></span></footer>
    </WorkspaceShell>
  );
}
