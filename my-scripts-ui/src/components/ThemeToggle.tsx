'use client';

import { useSyncExternalStore } from 'react';
import { Moon, Sun } from 'lucide-react';

const getTheme = () => document.documentElement.classList.contains('dark');
const serverTheme = () => false;

function subscribeTheme(onChange: () => void) {
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  const sync = () => {
    try {
      const saved = localStorage.getItem('theme');
      document.documentElement.classList.toggle('dark', saved === 'dark' || (saved !== 'light' && system.matches));
    } catch {
      document.documentElement.classList.toggle('dark', system.matches);
    }
    onChange();
  };
  const onStorage = (event: StorageEvent) => { if (event.key === 'theme' || event.key === null) sync(); };
  window.addEventListener('theme-change', onChange);
  window.addEventListener('storage', onStorage);
  system.addEventListener('change', sync);
  return () => {
    window.removeEventListener('theme-change', onChange);
    window.removeEventListener('storage', onStorage);
    system.removeEventListener('change', sync);
  };
}

export default function ThemeToggle({ className, showLabel = false }: { className?: string; showLabel?: boolean }) {
  const isDark = useSyncExternalStore(subscribeTheme, getTheme, serverTheme);
  const toggleTheme = () => {
    const dark = !getTheme();
    document.documentElement.classList.toggle('dark', dark);
    try { localStorage.setItem('theme', dark ? 'dark' : 'light'); } catch { /* Theme still works without storage. */ }
    window.dispatchEvent(new Event('theme-change'));
  };
  const Icon = isDark ? Moon : Sun;

  return (
    <button type="button" onClick={toggleTheme}
      className={className ?? 'p-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors'}
      aria-label={isDark ? 'Activar tema claro' : 'Activar tema oscuro'}
      title={isDark ? 'Activar tema claro' : 'Activar tema oscuro'}>
      {className ? <Icon aria-hidden="true" /> : <span className="text-lg">{isDark ? '🌙' : '☀️'}</span>}
      {showLabel && <span>{isDark ? 'Oscuro' : 'Claro'}</span>}
    </button>
  );
}
