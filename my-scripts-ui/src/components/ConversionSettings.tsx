'use client';

import { ConversionSettings, ImageFormat, OUTPUT_FORMATS } from '@/types/image-converter';

interface ConversionSettingsProps {
  settings: ConversionSettings;
  onChange: (settings: ConversionSettings) => void;
  totalImages: number;
}

export default function ConversionSettingsComponent({ 
  settings, 
  onChange, 
  totalImages 
}: ConversionSettingsProps) {
  const handleFormatChange = (format: ImageFormat) => {
    onChange({ ...settings, format });
  };

  const handleQualityChange = (quality: number) => {
    onChange({ ...settings, quality });
  };

  const handleDimensionChange = (field: 'width' | 'height', value: string) => {
    const numValue = value === '' ? undefined : parseInt(value);
    onChange({ ...settings, [field]: numValue });
  };

  const handleCheckboxChange = (field: keyof ConversionSettings, value: boolean) => {
    onChange({ ...settings, [field]: value });
  };

  const selectedFormat = OUTPUT_FORMATS.find(f => f.value === settings.format);
  const supportsTransparency = selectedFormat?.supportsTransparency ?? false;

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-6 border border-gray-200 dark:border-gray-700">
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6">
        ⚙️ Configuración de Conversión
      </h2>

      <div className="space-y-6">
        {/* Format Selection */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-3">
            Formato de salida
          </label>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {OUTPUT_FORMATS.map((format) => (
              <button
                key={format.value}
                onClick={() => handleFormatChange(format.value)}
                className={`p-3 border rounded-lg text-center transition-all duration-200 ${
                  settings.format === format.value
                    ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 dark:border-blue-400'
                    : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
                }`}
              >
                <div className="font-medium text-gray-900 dark:text-white">
                  {format.label}
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                  {format.description}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Quality Settings */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-3">
            Calidad: {settings.quality}%
          </label>
          <div className="space-y-2">
            <input
              type="range"
              min="1"
              max="100"
              value={settings.quality}
              onChange={(e) => handleQualityChange(parseInt(e.target.value))}
              className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer"
            />
            <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
              <span>Menor tamaño</span>
              <span>Mayor calidad</span>
            </div>
          </div>
        </div>

        {/* Dimension Settings */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-3">
            Redimensionar (opcional)
          </label>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                Ancho (px)
              </label>
              <input
                type="number"
                placeholder="Auto"
                value={settings.width || ''}
                onChange={(e) => handleDimensionChange('width', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                Alto (px)
              </label>
              <input
                type="number"
                placeholder="Auto"
                value={settings.height || ''}
                onChange={(e) => handleDimensionChange('height', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </div>
          
          <label className="flex items-center space-x-2 mt-3">
            <input
              type="checkbox"
              checked={settings.maintainAspectRatio}
              onChange={(e) => handleCheckboxChange('maintainAspectRatio', e.target.checked)}
              className="text-blue-600 rounded focus:ring-blue-500"
            />
            <span className="text-sm text-gray-700 dark:text-gray-300">
              Mantener proporción de aspecto
            </span>
          </label>
        </div>

        {/* Background Color (for non-transparent formats) */}
        {!supportsTransparency && (
          <div>
            <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-3">
              Color de fondo
            </label>
            <div className="flex items-center space-x-3">
              <input
                type="color"
                value={settings.backgroundColor || '#ffffff'}
                onChange={(e) => onChange({ ...settings, backgroundColor: e.target.value })}
                className="w-12 h-10 border border-gray-300 dark:border-gray-600 rounded-lg cursor-pointer"
              />
              <input
                type="text"
                value={settings.backgroundColor || '#ffffff'}
                onChange={(e) => onChange({ ...settings, backgroundColor: e.target.value })}
                placeholder="#ffffff"
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              El formato {selectedFormat?.label} no soporta transparencia
            </p>
          </div>
        )}

        {/* Other Settings */}
        <div className="space-y-3">
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={settings.removeMetadata}
              onChange={(e) => handleCheckboxChange('removeMetadata', e.target.checked)}
              className="text-blue-600 rounded focus:ring-blue-500"
            />
            <span className="text-sm text-gray-700 dark:text-gray-300">
              Eliminar metadatos (EXIF, ubicación, etc.)
            </span>
          </label>
        </div>

        {/* Summary */}
        {totalImages > 0 && (
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-800">
            <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-2">
              📋 Resumen
            </h4>
            <ul className="text-sm text-blue-800 dark:text-blue-200 space-y-1">
              <li>• {totalImages} imagen{totalImages === 1 ? '' : 'es'} será{totalImages === 1 ? '' : 'n'} convertida{totalImages === 1 ? '' : 's'} a {selectedFormat?.label}</li>
              <li>• Calidad: {settings.quality}%</li>
              {(settings.width || settings.height) && (
                <li>• Redimensionado: {settings.width || 'auto'} × {settings.height || 'auto'} px</li>
              )}
              {settings.removeMetadata && (
                <li>• Se eliminarán los metadatos</li>
              )}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}