export default function WebScrapingPage() {
  return (
    <div className="min-h-screen p-8 pt-20">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
            🕷️ Web Scraping
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-400">
            Extrae datos de cualquier sitio web de forma rápida y eficiente
          </p>
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-8 border border-gray-200 dark:border-gray-700">
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-3">
                URL del sitio web
              </label>
              <div className="flex gap-3">
                <input
                  type="url"
                  placeholder="https://ejemplo.com"
                  className="flex-1 p-4 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
                <button className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-4 rounded-lg font-medium transition-colors duration-200">
                  🔍 Analizar
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Opciones de extracción
                </h3>
                <div className="space-y-3">
                  {[
                    { label: 'Texto completo', icon: '📄' },
                    { label: 'Enlaces (URLs)', icon: '🔗' },
                    { label: 'Imágenes', icon: '🖼️' },
                    { label: 'Tablas', icon: '📊' },
                    { label: 'Metadatos', icon: '🏷️' }
                  ].map((option) => (
                    <label key={option.label} className="flex items-center space-x-3 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors duration-200">
                      <input type="checkbox" className="rounded text-blue-600" defaultChecked />
                      <span className="text-xl">{option.icon}</span>
                      <span className="text-gray-700 dark:text-gray-300">{option.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Configuración avanzada
                </h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Selector CSS (opcional)
                    </label>
                    <input
                      type="text"
                      placeholder=".article-content, #main"
                      className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Formato de salida
                    </label>
                    <select className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white">
                      <option>JSON</option>
                      <option>CSV</option>
                      <option>XML</option>
                      <option>TXT</option>
                    </select>
                  </div>
                  <div>
                    <label className="flex items-center space-x-2">
                      <input type="checkbox" className="rounded" />
                      <span className="text-sm text-gray-700 dark:text-gray-300">
                        Seguir enlaces internos
                      </span>
                    </label>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                💡 Vista previa del resultado
              </h4>
              <div className="text-sm text-gray-600 dark:text-gray-400 font-mono bg-white dark:bg-gray-900 p-3 rounded border">
                Los datos extraídos aparecerán aquí...
              </div>
            </div>

            <div className="flex gap-3">
              <button className="flex-1 bg-green-600 hover:bg-green-700 text-white py-3 px-6 rounded-lg font-semibold transition-colors duration-200">
                🚀 Iniciar Scraping
              </button>
              <button className="bg-gray-600 hover:bg-gray-700 text-white py-3 px-6 rounded-lg font-medium transition-colors duration-200">
                💾 Descargar
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}