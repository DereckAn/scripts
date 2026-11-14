'use client';

import { Check } from 'lucide-react';
import type { App, OperatingSystem } from '@/types/script-generator';
import { getInstallCommand } from '@/utils/script-generator';
import { CATEGORIES } from '@/components/script-generator/config';
import styles from '@/app/generate-scripts/generator.module.css';

export default function AppSelector({ app, selectedOS, isSelected, onToggle }: {
  app: App; selectedOS: OperatingSystem | null; isSelected: boolean; onToggle: (id: string) => void;
}) {
  const category = CATEGORIES.find(item => item.id === app.category);
  const Icon = category?.icon || CATEGORIES[0].icon;
  const command = selectedOS ? getInstallCommand(app, selectedOS) : '';
  return (
    <label className={`${styles.packageCard} ${isSelected ? styles.packageSelected : ''}`}>
      <input type="checkbox" checked={isSelected} disabled={!command} onChange={() => onToggle(app.id)} aria-label={`Seleccionar ${app.name}`} />
      <div className={styles.packageDetails}>
        <div className={styles.packageTitle}><Icon size={16} aria-hidden="true" /><strong>{app.name}</strong><span>{category?.name}</span></div>
        <p>{app.description}</p>
        <div className={styles.packageCommand}><code title={command}>{command}</code>{isSelected && <Check size={14} aria-hidden="true" />}</div>
      </div>
    </label>
  );
}
