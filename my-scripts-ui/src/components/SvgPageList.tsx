'use client';

import { useState } from 'react';
import Image from 'next/image';
import { ArrowDownAZ, ChevronDown, ChevronUp, GripVertical, Trash2 } from 'lucide-react';
import { SvgFile } from '@/types/svg-to-pdf';
import { formatFileSize } from '@/utils/svg-to-pdf';

interface SvgPageListProps {
  files: SvgFile[];
  onReorder: (from: number, to: number) => void;
  onRemove: (id: string) => void;
  onSortByName: () => void;
  onClear: () => void;
}

export default function SvgPageList({
  files,
  onReorder,
  onRemove,
  onSortByName,
  onClear,
}: SvgPageListProps) {
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);

  const handleDrop = (index: number) => {
    if (draggedIndex !== null) {
      onReorder(draggedIndex, index);
    }
    setDraggedIndex(null);
    setDropTarget(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
          Páginas del PDF{' '}
          <span className="text-stone-500 dark:text-stone-400 font-normal">({files.length})</span>
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={onSortByName}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
          >
            <ArrowDownAZ className="w-4 h-4" />
            Ordenar por nombre
          </button>
          <button
            onClick={onClear}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg border border-red-200 dark:border-red-900 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            Quitar todo
          </button>
        </div>
      </div>

      <p className="text-sm text-stone-500 dark:text-stone-400">
        Arrastra las tarjetas o usa las flechas para cambiar el orden de las páginas.
      </p>

      <ul className="space-y-2">
        {files.map((file, index) => (
          <li
            key={file.id}
            draggable
            onDragStart={() => setDraggedIndex(index)}
            onDragEnd={() => {
              setDraggedIndex(null);
              setDropTarget(null);
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDropTarget(index);
            }}
            onDrop={(e) => {
              e.preventDefault();
              handleDrop(index);
            }}
            className={`flex items-center gap-4 p-3 rounded-xl border bg-white dark:bg-stone-900 transition-all duration-200 ${
              draggedIndex === index
                ? 'opacity-40 border-indigo-400'
                : dropTarget === index
                ? 'border-indigo-500 ring-2 ring-indigo-500/20'
                : 'border-stone-200 dark:border-stone-800'
            }`}
          >
            <GripVertical className="w-5 h-5 shrink-0 text-stone-400 cursor-grab active:cursor-grabbing" />

            <span className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-100 dark:bg-indigo-950/40 text-sm font-semibold text-indigo-700 dark:text-indigo-300">
              {index + 1}
            </span>

            <div className="shrink-0 w-12 h-16 rounded-md border border-stone-200 dark:border-stone-700 bg-white overflow-hidden relative">
              <Image
                src={file.preview}
                alt={file.name}
                fill
                unoptimized
                className="object-contain"
              />
            </div>

            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-stone-900 dark:text-stone-100">{file.name}</p>
              <p className="text-sm text-stone-500 dark:text-stone-400">
                {formatFileSize(file.size)} · {Math.round(file.width)} × {Math.round(file.height)} px
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-1">
              <button
                onClick={() => onReorder(index, index - 1)}
                disabled={index === 0}
                aria-label={`Mover ${file.name} hacia arriba`}
                className="p-2 rounded-lg text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronUp className="w-4 h-4" />
              </button>
              <button
                onClick={() => onReorder(index, index + 1)}
                disabled={index === files.length - 1}
                aria-label={`Mover ${file.name} hacia abajo`}
                className="p-2 rounded-lg text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronDown className="w-4 h-4" />
              </button>
              <button
                onClick={() => onRemove(file.id)}
                aria-label={`Quitar ${file.name}`}
                className="p-2 rounded-lg text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
