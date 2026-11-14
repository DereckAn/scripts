import { Apple, Braces, Code2, Cpu, Globe, Layers3, Monitor, Package, PanelsTopLeft, Server, Terminal } from 'lucide-react';
import type { OperatingSystem, ScriptConfig, ScriptOptions } from '@/types/script-generator';
import { getAvailableApps } from '@/utils/script-generator';

export const SYSTEMS = [
  { id: 'macos', name: 'macOS', manager: 'Homebrew / Cask', detail: 'Aplicaciones y herramientas', icon: Apple },
  { id: 'ubuntu', name: 'Ubuntu / Debian', manager: 'APT / Snap', detail: 'Paquetes y repositorios', icon: Server },
  { id: 'fedora', name: 'Fedora', manager: 'DNF / Flatpak', detail: 'Paquetes y comandos', icon: Cpu },
  { id: 'arch', name: 'Arch Linux', manager: 'Pacman / AUR', detail: 'Paquetes y helper yay', icon: Monitor },
] satisfies { id: OperatingSystem; name: string; manager: string; detail: string; icon: typeof Apple }[];
export const CATEGORIES = [
  { id: 'code-editors', name: 'Editores', icon: Code2 },
  { id: 'terminals', name: 'Terminales', icon: Terminal },
  { id: 'development-tools', name: 'Herramientas dev', icon: Package },
  { id: 'programming-languages', name: 'Lenguajes', icon: Braces },
  { id: 'browsers', name: 'Navegadores', icon: Globe },
  { id: 'productivity', name: 'Productividad', icon: PanelsTopLeft },
  { id: 'frameworks', name: 'Frameworks', icon: Layers3 },
];
export const DEFAULT_OPTIONS: ScriptOptions = { updateSystem: true, createBackup: false,
  showProgress: true, configureDotfiles: false, installOhMyZsh: false };
export const OPTIONS: { key: keyof ScriptOptions; title: string; description: string }[] = [
  { key: 'updateSystem', title: 'Actualizar el sistema antes de instalar', description: 'Incluye los comandos de actualización del gestor de paquetes del sistema elegido.' },
  { key: 'createBackup', title: 'Crear una copia de las configuraciones existentes', description: 'Respalda .bashrc, .zshrc, .gitconfig y .ssh en una carpeta con fecha dentro de tu directorio personal.' },
  { key: 'installOhMyZsh', title: 'Instalar Oh My Zsh con tema y plugins', description: 'Añade Oh My Zsh, Powerlevel10k, autosuggestions y syntax-highlighting al script.' },
  { key: 'configureDotfiles', title: 'Configurar aliases en los dotfiles', description: 'Añade atajos como ll, la y .. a los archivos .bashrc y .zshrc que ya existan.' },
  { key: 'showProgress', title: 'Mostrar el avance por paquetes', description: 'Incluye un contador en los mensajes de instalación: [1/3], [2/3], [3/3]…' },
];
export const HISTORY_KEY = 'my-scripts-ui.script-history.v1';
export type Artifact = { id: string; createdAt: string; config: ScriptConfig; script: string; readme: string };
export const configKey = (config: ScriptConfig) => JSON.stringify({ os: config.os,
  selectedApps: [...config.selectedApps].sort(), options: Object.fromEntries(Object.keys(DEFAULT_OPTIONS).map(key => [key, config.options[key as keyof ScriptOptions]])) });
export function readHistory(value: string | null): Artifact[] {
  try {
    const entries: unknown = JSON.parse(value || '[]');
    if (!Array.isArray(entries)) return [];
    return entries.filter((item): item is Artifact => {
      if (!item || typeof item !== 'object') return false;
      const entry = item as Artifact;
      if (typeof entry.id !== 'string' || typeof entry.createdAt !== 'string' || !Number.isFinite(Date.parse(entry.createdAt)) ||
          typeof entry.script !== 'string' || typeof entry.readme !== 'string' || !entry.config ||
          !SYSTEMS.some(system => system.id === entry.config.os) || !Array.isArray(entry.config.selectedApps) || !entry.config.options) return false;
      const available = new Set(getAvailableApps(entry.config.os).map(app => app.id));
      return entry.config.selectedApps.length > 0 && entry.config.selectedApps.every(id => typeof id === 'string' && available.has(id)) &&
        Object.keys(DEFAULT_OPTIONS).every(key => typeof entry.config.options[key as keyof ScriptOptions] === 'boolean');
    }).slice(0, 5);
  } catch { return []; }
}
