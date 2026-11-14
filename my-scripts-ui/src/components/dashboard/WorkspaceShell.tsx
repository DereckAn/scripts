'use client';

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ArrowDown, Home, LayoutDashboard, Menu, Monitor, Search, Terminal, X } from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';
import styles from '@/app/dashboard-theme.module.css';
import { navigationGroups, tools } from './tools';

export default function WorkspaceShell({ children, title, mainId = 'workspace-main', onSearch,
  sectionHref = '/#herramientas', sectionLabel = 'Herramientas' }: {
  children: ReactNode; title?: string; mainId?: string; onSearch?: () => void;
  sectionHref?: string; sectionLabel?: string;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const sidebar = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const focusSearch = useCallback(() => {
    setMenuOpen(false);
    if (onSearch) requestAnimationFrame(onSearch);
    else router.push('/#dashboard-search');
  }, [onSearch, router]);
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); focusSearch();
      }
      if (event.key === 'Escape') setMenuOpen(false);
    };
    const desktop = window.matchMedia('(min-width: 1024px)');
    const closeOnDesktop = () => { if (desktop.matches) setMenuOpen(false); };
    window.addEventListener('keydown', keydown);
    desktop.addEventListener('change', closeOnDesktop);
    return () => {
      window.removeEventListener('keydown', keydown);
      desktop.removeEventListener('change', closeOnDesktop);
    };
  }, [focusSearch]);

  useEffect(() => {
    if (!menuOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    sidebar.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const trapFocus = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;
      const items = sidebar.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled)');
      if (!items?.length) return;
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', trapFocus);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', trapFocus);
      menuButton.current?.focus();
    };
  }, [menuOpen]);

  return (
    <div className={styles.dashboard}>
      <a className={styles.skipLink} href={`#${mainId}`}>Ir al contenido</a>
      {menuOpen && <button type="button" className={styles.backdrop} onClick={() => setMenuOpen(false)} aria-label="Cerrar navegación" />}
      <aside ref={sidebar} id="dashboard-sidebar" className={`${styles.sidebar} ${menuOpen ? styles.sidebarOpen : ''}`} aria-label="Navegación del workspace">
        <div className={styles.brand}>
          <span className={styles.brandIcon}><Terminal size={23} aria-hidden="true" /></span>
          <div><strong>My Scripts UI</strong><small>Caja de utilidades personales</small></div>
          <button type="button" className={styles.closeMenu} onClick={() => setMenuOpen(false)} aria-label="Cerrar menú"><X size={18} /></button>
        </div>
        <button type="button" className={styles.sidebarSearch} onClick={focusSearch}>
          <Search size={16} aria-hidden="true" /><span>Buscar una herramienta…</span><kbd>⌘K</kbd>
        </button>
        <nav className={styles.navigation} aria-label="Herramientas">
          <div className={styles.navGroup}><p>Principal</p><Link className={pathname === "/" ? styles.activeNav : undefined} href="/" aria-current={pathname === "/" ? "page" : undefined} onClick={() => setMenuOpen(false)}><LayoutDashboard size={17} aria-hidden="true" />Panel de Control</Link></div>
          {navigationGroups.map(group => <div key={group.name} className={styles.navGroup}>
            <p>{group.name}</p>
            {group.paths.map(path => {
              const tool = tools.find(item => item.href === path)!; const Icon = tool.icon;
              return <Link href={tool.href} key={tool.href} className={pathname === tool.href ? styles.activeNav : undefined} aria-current={pathname === tool.href ? "page" : undefined} onClick={() => setMenuOpen(false)}><Icon size={17} aria-hidden="true" /><span>{tool.nav}</span>{tool.badge && <small>{tool.badge}</small>}</Link>;
            })}
          </div>)}
        </nav>
        <div className={styles.sidebarFooter}>
          <div className={styles.workspaceBadge}><span className={styles.statusDot} /><span>Tu workspace personal</span><Monitor size={15} aria-hidden="true" /></div>
          <div className={styles.appearance}><span>Apariencia</span><ThemeToggle className={styles.themeToggle} showLabel /></div>
          <div className={styles.paletteCaption}><span aria-hidden="true"><i /><i /><i /><i /></span>Azul petróleo · Arena</div>
        </div>
      </aside>
      <div className={styles.workspace} inert={menuOpen}>
        <header className={styles.header}>
          <div className={styles.breadcrumb}>
            <button ref={menuButton} type="button" className={styles.menuButton} onClick={() => setMenuOpen(true)} aria-label="Abrir menú" aria-expanded={menuOpen} aria-controls="dashboard-sidebar"><Menu size={21} /></button>
            <Home size={16} aria-hidden="true" /><span>/</span><Link href="/">Workspace</Link>{title && <><span>/</span><strong>{title}</strong></>}<span className={styles.headerBadge}><span className={styles.statusDot} />Personal</span>
          </div>
          <div className={styles.headerActions}><a href={sectionHref}>{sectionLabel} <ArrowDown size={13} aria-hidden="true" /></a><ThemeToggle className={styles.themeToggle} /></div>
        </header>
        <main id={mainId} className={styles.main}>
          {children}
        </main>
      </div>
    </div>
  );

}
