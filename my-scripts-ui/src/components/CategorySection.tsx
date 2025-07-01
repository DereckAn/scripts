'use client';

import { App, OperatingSystem } from '@/types/script-generator';
import AppSelector from './AppSelector';

interface CategorySectionProps {
  title: string;
  icon: string;
  apps: App[];
  selectedOS: OperatingSystem | null;
  selectedApps: string[];
  onToggleApp: (appId: string) => void;
}

const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  'productivity': 'Herramientas para mejorar tu productividad',
  'code-editors': 'Editores de código e IDEs',
  'terminals': 'Emuladores de terminal',
  'browsers': 'Navegadores web',
  'development-tools': 'Herramientas de desarrollo',
  'programming-languages': 'Lenguajes de programación',
  'frameworks': 'Frameworks y herramientas de orquestación'
};

export default function CategorySection({ 
  title, 
  icon, 
  apps, 
  selectedOS, 
  selectedApps, 
  onToggleApp 
}: CategorySectionProps) {
  const availableApps = apps.filter(app => {
    if (selectedOS === 'macos') return !app.linuxOnly;
    if (selectedOS && selectedOS !== null) return !app.macosOnly;
    return true;
  });

  const selectedCount = availableApps.filter(app => selectedApps.includes(app.id)).length;

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700">
      <div className="p-6 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <span className="text-2xl mr-3">{icon}</span>
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {CATEGORY_DESCRIPTIONS[apps[0]?.category] || ''}
              </p>
            </div>
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">
            {selectedCount > 0 && (
              <span className="bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 px-2 py-1 rounded-full">
                {selectedCount} seleccionad{selectedCount === 1 ? 'a' : 'as'}
              </span>
            )}
            <span className="ml-2">{availableApps.length} disponible{availableApps.length === 1 ? '' : 's'}</span>
          </div>
        </div>
      </div>
      
      <div className="p-6">
        <div className="space-y-3">
          {availableApps.map(app => (
            <AppSelector
              key={app.id}
              app={app}
              selectedOS={selectedOS}
              isSelected={selectedApps.includes(app.id)}
              onToggle={onToggleApp}
            />
          ))}
        </div>
      </div>
    </div>
  );
}