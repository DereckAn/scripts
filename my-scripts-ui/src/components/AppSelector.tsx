'use client';

import { useState } from 'react';
import { App, OperatingSystem } from '@/types/script-generator';

interface AppSelectorProps {
  app: App;
  selectedOS: OperatingSystem | null;
  isSelected: boolean;
  onToggle: (appId: string) => void;
}

export default function AppSelector({ app, selectedOS, isSelected, onToggle }: AppSelectorProps) {
  const isDisabled = (selectedOS === 'macos' && app.linuxOnly) || 
                    (selectedOS !== 'macos' && app.macosOnly);

  return (
    <label 
      className={`flex items-center p-4 border rounded-lg transition-all duration-200 cursor-pointer ${
        isDisabled 
          ? 'bg-stone-50 dark:bg-stone-800 border-stone-200 dark:border-stone-700 opacity-50 cursor-not-allowed' 
          : isSelected
          ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 dark:border-blue-400'
          : 'bg-white/80 dark:bg-stone-900/80 border-stone-300 dark:border-stone-600 hover:bg-stone-50 dark:hover:bg-stone-800 hover:border-stone-400 dark:hover:border-stone-500'
      }`}
    >
      <input
        type="checkbox"
        checked={isSelected && !isDisabled}
        disabled={isDisabled}
        onChange={() => !isDisabled && onToggle(app.id)}
        className="mr-4 text-blue-600 rounded focus:ring-blue-500"
      />
      <span className="text-2xl mr-3">{app.icon}</span>
      <div className="flex-1">
        <div className="font-medium text-stone-900 dark:text-stone-100">
          {app.name}
          {app.macosOnly && <span className="ml-2 text-xs bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 px-2 py-1 rounded">macOS</span>}
          {app.linuxOnly && <span className="ml-2 text-xs bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 px-2 py-1 rounded">Linux</span>}
        </div>
        <div className="text-sm text-stone-600 dark:text-stone-400">{app.description}</div>
      </div>
    </label>
  );
}