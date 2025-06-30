export default function GenerateScriptsPage() {
  return (
    <div className="min-h-screen p-8 pt-20">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
            ⚡ Generar Scripts
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-400">
            Crea scripts personalizados para instalar aplicaciones en Mac y Linux
          </p>
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-8 border border-gray-200 dark:border-gray-700">
          <div className="space-y-8">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                  🖥️ Sistema Operativo
                </h3>
                <div className="space-y-3">
                  {[
                    { name: 'macOS', icon: '🍎', desc: 'Homebrew, MacPorts' },
                    { name: 'Ubuntu/Debian', icon: '🐧', desc: 'apt, snap' },
                    { name: 'Arch Linux', icon: '🏔️', desc: 'pacman, yay' },
                    { name: 'CentOS/RHEL', icon: '🎩', desc: 'yum, dnf' }
                  ].map((os) => (
                    <label key={os.name} className="flex items-center p-4 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:border-blue-500 dark:hover:border-blue-400 transition-all duration-200 cursor-pointer">
                      <input type="radio" name="os" className="mr-4" />
                      <span className="text-2xl mr-3">{os.icon}</span>
                      <div>
                        <div className="font-medium text-gray-900 dark:text-white">{os.name}</div>
                        <div className="text-sm text-gray-600 dark:text-gray-400">{os.desc}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                  📦 Categorías de Aplicaciones
                </h3>
                <div className="space-y-3">
                  {[
                    { name: 'Desarrollo', icon: '💻', count: '25+ apps' },
                    { name: 'Productividad', icon: '📊', count: '15+ apps' },
                    { name: 'Multimedia', icon: '🎨', count: '20+ apps' },
                    { name: 'Navegadores', icon: '🌐', count: '8+ apps' },
                    { name: 'Utilidades', icon: '🔧', count: '30+ apps' }
                  ].map((category) => (
                    <label key={category.name} className="flex items-center justify-between p-4 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-green-50 dark:hover:bg-green-900/20 hover:border-green-500 dark:hover:border-green-400 transition-all duration-200 cursor-pointer">
                      <div className="flex items-center">
                        <input type="checkbox" className="mr-4 text-green-600" />
                        <span className="text-2xl mr-3">{category.icon}</span>
                        <span className="font-medium text-gray-900 dark:text-white">{category.name}</span>
                      </div>
                      <span className="text-sm text-gray-500 dark:text-gray-400">{category.count}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                🎯 Aplicaciones Seleccionadas
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  'Visual Studio Code', 'Docker', 'Node.js', 'Python',
                  'Git', 'Chrome', 'Firefox', 'Slack'
                ].map((app) => (
                  <div key={app} className="flex items-center justify-between bg-white dark:bg-gray-900 p-3 rounded-lg border border-gray-200 dark:border-gray-700">
                    <span className="text-sm text-gray-700 dark:text-gray-300">{app}</span>
                    <button className="text-red-500 hover:text-red-700 text-sm">✕</button>
                  </div>
                ))}
              </div>
              <div className="mt-4 text-center">
                <button className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 text-sm font-medium">
                  + Agregar aplicación personalizada
                </button>
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                ⚙️ Opciones del Script
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <label className="flex items-center space-x-3 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors duration-200">
                  <input type="checkbox" className="rounded text-blue-600" defaultChecked />
                  <span className="text-gray-700 dark:text-gray-300">Actualizar sistema antes de instalar</span>
                </label>
                <label className="flex items-center space-x-3 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors duration-200">
                  <input type="checkbox" className="rounded text-blue-600" />
                  <span className="text-gray-700 dark:text-gray-300">Crear backup antes de instalar</span>
                </label>
                <label className="flex items-center space-x-3 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors duration-200">
                  <input type="checkbox" className="rounded text-blue-600" defaultChecked />
                  <span className="text-gray-700 dark:text-gray-300">Mostrar progreso detallado</span>
                </label>
                <label className="flex items-center space-x-3 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors duration-200">
                  <input type="checkbox" className="rounded text-blue-600" />
                  <span className="text-gray-700 dark:text-gray-300">Configurar dotfiles automáticamente</span>
                </label>
              </div>
            </div>

            <div className="bg-gray-900 dark:bg-gray-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold text-white">
                  📄 Vista previa del script
                </h4>
                <button className="text-blue-400 hover:text-blue-300 text-sm">
                  Copiar
                </button>
              </div>
              <pre className="text-sm text-green-400 font-mono overflow-x-auto">
{`#!/bin/bash
# Script de instalación automatizada
# Generado por My Scripts UI

echo "🚀 Iniciando instalación..."
# Actualizar sistema
brew update && brew upgrade

# Instalar aplicaciones
brew install --cask visual-studio-code
brew install node
brew install python
...`}
              </pre>
            </div>

            <div className="flex gap-3">
              <button className="flex-1 bg-purple-600 hover:bg-purple-700 text-white py-3 px-6 rounded-lg font-semibold transition-colors duration-200">
                🎯 Generar Script
              </button>
              <button className="bg-green-600 hover:bg-green-700 text-white py-3 px-6 rounded-lg font-medium transition-colors duration-200">
                💾 Descargar
              </button>
              <button className="bg-blue-600 hover:bg-blue-700 text-white py-3 px-6 rounded-lg font-medium transition-colors duration-200">
                ▶️ Ejecutar
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}