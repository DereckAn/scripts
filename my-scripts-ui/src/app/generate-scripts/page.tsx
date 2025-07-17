'use client';

import { useState, useMemo } from 'react';
import { OperatingSystem, ScriptOptions, ScriptConfig } from '@/types/script-generator';
import { APPS } from '@/data/apps';
import CategorySection from '@/components/CategorySection';
import { generateInstallScript, generateReadme } from '@/utils/script-generator';

const OS_OPTIONS = [
  { id: 'macos' as OperatingSystem, name: 'macOS', icon: '🍎', desc: 'Homebrew, Cask' },
  { id: 'ubuntu' as OperatingSystem, name: 'Ubuntu/Debian', icon: '🐧', desc: 'APT, Snap' },
  { id: 'fedora' as OperatingSystem, name: 'Fedora', icon: '🎩', desc: 'DNF, Flatpak' },
  { id: 'arch' as OperatingSystem, name: 'Arch Linux', icon: '🏔️', desc: 'Pacman, AUR' }
];

const CATEGORIES = [
  { id: 'productivity', name: 'Herramientas de Productividad', icon: '📊' },
  { id: 'code-editors', name: 'Editores de Código', icon: '💻' },
  { id: 'terminals', name: 'Terminales', icon: '💻' },
  { id: 'browsers', name: 'Navegadores', icon: '🌐' },
  { id: 'development-tools', name: 'Herramientas de Desarrollo', icon: '🔧' },
  { id: 'programming-languages', name: 'Lenguajes de Programación', icon: '📝' },
  { id: 'frameworks', name: 'Frameworks', icon: '🏗️' }
];

export default function GenerateScriptsPage() {
  const [selectedOS, setSelectedOS] = useState<OperatingSystem | null>(null);
  const [selectedApps, setSelectedApps] = useState<string[]>([]);
  const [options, setOptions] = useState<ScriptOptions>({
    updateSystem: true,
    createBackup: false,
    showProgress: true,
    configureDotfiles: false,
    installOhMyZsh: false
  });
  const [generatedScript, setGeneratedScript] = useState<string>('');
  const [generatedReadme, setGeneratedReadme] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'script' | 'readme'>('script');

  // Group apps by category
  const appsByCategory = useMemo(() => {
    const grouped: Record<string, typeof APPS> = {};
    APPS.forEach(app => {
      if (!grouped[app.category]) {
        grouped[app.category] = [];
      }
      grouped[app.category].push(app);
    });
    return grouped;
  }, []);

  // Get available apps for selected OS
  const availableApps = useMemo(() => {
    if (!selectedOS) return APPS;
    return APPS.filter(app => {
      if (selectedOS === 'macos') return !app.linuxOnly;
      return !app.macosOnly;
    });
  }, [selectedOS]);

  const handleOSChange = (os: OperatingSystem) => {
    setSelectedOS(os);
    // Remove apps that are not compatible with the new OS
    setSelectedApps(prev => prev.filter(appId => {
      const app = APPS.find(a => a.id === appId);
      if (!app) return false;
      if (os === 'macos') return !app.linuxOnly;
      return !app.macosOnly;
    }));
  };

  const handleToggleApp = (appId: string) => {
    setSelectedApps(prev => 
      prev.includes(appId) 
        ? prev.filter(id => id !== appId)
        : [...prev, appId]
    );
  };

  const handleOptionChange = (option: keyof ScriptOptions, value: boolean) => {
    setOptions(prev => ({ ...prev, [option]: value }));
  };

  const handleGenerateScript = () => {
    if (!selectedOS || selectedApps.length === 0) return;

    const config: ScriptConfig = {
      os: selectedOS,
      selectedApps,
      options
    };

    const script = generateInstallScript(config);
    const readme = generateReadme(config);
    
    setGeneratedScript(script);
    setGeneratedReadme(readme);
  };

  const handleDownloadScript = () => {
    if (!generatedScript) return;
    
    const blob = new Blob([generatedScript], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `install-script-${selectedOS}.sh`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDownloadReadme = () => {
    if (!generatedReadme) return;
    
    const blob = new Blob([generatedReadme], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `README-${selectedOS}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCopyToClipboard = async (content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      // You could add a toast notification here
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-50 via-stone-100 to-stone-200 dark:from-stone-950 dark:via-stone-900 dark:to-stone-800">
      {/* Background Pattern */}
      <div className="absolute inset-0 bg-grid-stone-900/[0.04] dark:bg-grid-stone-100/[0.02]" />
      
      <div className="relative p-8 pt-20">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-12">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-r from-stone-900 to-stone-700 dark:from-stone-100 dark:to-stone-300 rounded-xl mb-8 shadow-lg">
            <span className="text-2xl">⚡</span>
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-stone-900 dark:text-stone-100 mb-6">
            Generar Scripts de Instalación
          </h1>
          <p className="text-lg text-stone-600 dark:text-stone-400 max-w-2xl mx-auto leading-relaxed">
            Crea scripts personalizados para instalar aplicaciones automáticamente en Mac y Linux
          </p>
        </div>

        <div className="space-y-8">
          {/* OS Selection */}
          <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-8 border border-stone-200/60 dark:border-stone-800/60">
            <h2 className="text-2xl font-semibold text-stone-900 dark:text-stone-100 mb-6">
              🖥️ Selecciona tu Sistema Operativo
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {OS_OPTIONS.map(os => (
                <label
                  key={os.id}
                  className={`flex items-center p-4 border rounded-lg cursor-pointer transition-all duration-200 ${
                    selectedOS === os.id
                      ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 dark:border-blue-400'
                      : 'bg-white dark:bg-stone-800 border-stone-300 dark:border-stone-600 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}
                >
                  <input
                    type="radio"
                    name="os"
                    value={os.id}
                    checked={selectedOS === os.id}
                    onChange={() => handleOSChange(os.id)}
                    className="mr-4 text-blue-600"
                  />
                  <span className="text-2xl mr-3">{os.icon}</span>
                  <div>
                    <div className="font-medium text-stone-900 dark:text-stone-100">{os.name}</div>
                    <div className="text-sm text-stone-600 dark:text-stone-400">{os.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* App Selection */}
          {selectedOS && (
            <div className="space-y-6">
              <div className="text-center">
                <h2 className="text-2xl font-semibold text-stone-900 dark:text-stone-100 mb-2">
                  📦 Selecciona las Aplicaciones
                </h2>
                <p className="text-stone-600 dark:text-stone-400">
                  {selectedApps.length} aplicación{selectedApps.length === 1 ? '' : 'es'} seleccionada{selectedApps.length === 1 ? '' : 's'} de {availableApps.length} disponible{availableApps.length === 1 ? '' : 's'}
                </p>
              </div>

              {CATEGORIES.map(category => {
                const categoryApps = appsByCategory[category.id] || [];
                const availableCategoryApps = categoryApps.filter(app => {
                  if (selectedOS === 'macos') return !app.linuxOnly;
                  return !app.macosOnly;
                });
                
                if (availableCategoryApps.length === 0) return null;

                return (
                  <CategorySection
                    key={category.id}
                    title={category.name}
                    icon={category.icon}
                    apps={availableCategoryApps}
                    selectedOS={selectedOS}
                    selectedApps={selectedApps}
                    onToggleApp={handleToggleApp}
                  />
                );
              })}
            </div>
          )}

          {/* Script Options */}
          {selectedOS && (
            <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl p-8 border border-stone-200/60 dark:border-stone-800/60">
              <h2 className="text-2xl font-semibold text-stone-900 dark:text-stone-100 mb-6">
                ⚙️ Opciones del Script
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <label className="flex items-center space-x-3 p-4 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors duration-200">
                  <input
                    type="checkbox"
                    checked={options.updateSystem}
                    onChange={(e) => handleOptionChange('updateSystem', e.target.checked)}
                    className="text-blue-600 rounded focus:ring-blue-500"
                  />
                  <div>
                    <span className="text-stone-900 dark:text-stone-100 font-medium">Actualizar sistema</span>
                    <p className="text-sm text-stone-600 dark:text-stone-400">Actualizar paquetes del sistema antes de instalar</p>
                  </div>
                </label>

                <label className="flex items-center space-x-3 p-4 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors duration-200">
                  <input
                    type="checkbox"
                    checked={options.createBackup}
                    onChange={(e) => handleOptionChange('createBackup', e.target.checked)}
                    className="text-blue-600 rounded focus:ring-blue-500"
                  />
                  <div>
                    <span className="text-stone-900 dark:text-stone-100 font-medium">Crear backup</span>
                    <p className="text-sm text-stone-600 dark:text-stone-400">Respaldar archivos de configuración</p>
                  </div>
                </label>

                <label className="flex items-center space-x-3 p-4 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors duration-200">
                  <input
                    type="checkbox"
                    checked={options.showProgress}
                    onChange={(e) => handleOptionChange('showProgress', e.target.checked)}
                    className="text-blue-600 rounded focus:ring-blue-500"
                  />
                  <div>
                    <span className="text-stone-900 dark:text-stone-100 font-medium">Mostrar progreso</span>
                    <p className="text-sm text-stone-600 dark:text-stone-400">Mostrar salida detallada durante la instalación</p>
                  </div>
                </label>

                <label className="flex items-center space-x-3 p-4 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors duration-200">
                  <input
                    type="checkbox"
                    checked={options.configureDotfiles}
                    onChange={(e) => handleOptionChange('configureDotfiles', e.target.checked)}
                    className="text-blue-600 rounded focus:ring-blue-500"
                  />
                  <div>
                    <span className="text-stone-900 dark:text-stone-100 font-medium">Configurar dotfiles</span>
                    <p className="text-sm text-stone-600 dark:text-stone-400">Añadir aliases y configuraciones útiles</p>
                  </div>
                </label>

                <label className="flex items-center space-x-3 p-4 rounded-lg hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors duration-200 md:col-span-2">
                  <input
                    type="checkbox"
                    checked={options.installOhMyZsh}
                    onChange={(e) => handleOptionChange('installOhMyZsh', e.target.checked)}
                    className="text-blue-600 rounded focus:ring-blue-500"
                  />
                  <div>
                    <span className="text-stone-900 dark:text-stone-100 font-medium">Instalar Oh My Zsh</span>
                    <p className="text-sm text-stone-600 dark:text-stone-400">
                      Instalar Oh My Zsh con tema Powerlevel10k y plugins útiles (zsh-autosuggestions, zsh-syntax-highlighting, etc.)
                    </p>
                  </div>
                </label>
              </div>
            </div>
          )}

          {/* Generate Button */}
          {selectedOS && selectedApps.length > 0 && (
            <div className="text-center">
              <button
                onClick={handleGenerateScript}
                className="bg-purple-600 hover:bg-purple-700 text-white px-8 py-4 rounded-lg font-semibold text-lg transition-colors duration-200 shadow-lg hover:shadow-xl"
              >
                🎯 Generar Script de Instalación
              </button>
            </div>
          )}

          {/* Generated Script Output */}
          {generatedScript && (
            <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl shadow-xl border border-stone-200/60 dark:border-stone-800/60">
              <div className="p-6 border-b border-stone-200/60 dark:border-stone-800/60">
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-semibold text-stone-900 dark:text-stone-100">
                    📄 Script Generado
                  </h2>
                  <div className="flex space-x-2">
                    <button
                      onClick={() => setActiveTab('script')}
                      className={`px-4 py-2 rounded-lg font-medium transition-colors duration-200 ${
                        activeTab === 'script'
                          ? 'bg-blue-600 text-white'
                          : 'bg-stone-200 dark:bg-stone-700 text-stone-700 dark:text-stone-300'
                      }`}
                    >
                      Script
                    </button>
                    <button
                      onClick={() => setActiveTab('readme')}
                      className={`px-4 py-2 rounded-lg font-medium transition-colors duration-200 ${
                        activeTab === 'readme'
                          ? 'bg-blue-600 text-white'
                          : 'bg-stone-200 dark:bg-stone-700 text-stone-700 dark:text-stone-300'
                      }`}
                    >
                      README
                    </button>
                  </div>
                </div>
              </div>
              
              <div className="p-6">
                <div className="bg-stone-900 dark:bg-stone-800 rounded-lg p-4 mb-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-white">
                      {activeTab === 'script' ? '📄 install-script.sh' : '📖 README.md'}
                    </h3>
                    <div className="flex space-x-2">
                      <button
                        onClick={() => handleCopyToClipboard(activeTab === 'script' ? generatedScript : generatedReadme)}
                        className="text-blue-400 hover:text-blue-300 text-sm font-medium transition-colors duration-200"
                      >
                        📋 Copiar
                      </button>
                      <button
                        onClick={activeTab === 'script' ? handleDownloadScript : handleDownloadReadme}
                        className="text-green-400 hover:text-green-300 text-sm font-medium transition-colors duration-200"
                      >
                        💾 Descargar
                      </button>
                    </div>
                  </div>
                  <pre className="text-sm text-green-400 font-mono overflow-x-auto max-h-96">
                    {activeTab === 'script' ? generatedScript : generatedReadme}
                  </pre>
                </div>

                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-800">
                  <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-2">
                    📋 Instrucciones de uso
                  </h4>
                  <ol className="text-sm text-blue-800 dark:text-blue-200 space-y-1">
                    <li>1. Descarga el script y hazlo ejecutable: <code className="bg-blue-200 dark:bg-blue-800 px-1 rounded">chmod +x install-script.sh</code></li>
                    <li>2. Ejecuta el script: <code className="bg-blue-200 dark:bg-blue-800 px-1 rounded">./install-script.sh</code></li>
                    <li>3. Sigue las instrucciones en pantalla</li>
                    <li>4. Reinicia tu terminal cuando termine la instalación</li>
                  </ol>
                </div>
              </div>
            </div>
          )}
        </div>
        </div>
      </div>
    </div>
  );
}