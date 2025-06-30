export default function ConvertImagesPage() {
  return (
    <div className="min-h-screen p-8 pt-20">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
            🖼️ Convertir Imágenes
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-400">
            Convierte tus imágenes a diferentes formatos de manera rápida y sencilla
          </p>
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-8 border border-gray-200 dark:border-gray-700">
          <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl p-12 text-center hover:border-blue-500 dark:hover:border-blue-400 transition-colors duration-300">
            <div className="text-6xl mb-4">📁</div>
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Arrastra y suelta tus imágenes aquí
            </h3>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              O haz clic para seleccionar archivos
            </p>
            <button className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium transition-colors duration-200">
              Seleccionar Archivos
            </button>
          </div>

          <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">
                Formato de salida
              </h4>
              <div className="grid grid-cols-2 gap-3">
                {['JPEG', 'PNG', 'WEBP', 'AVIF'].map((format) => (
                  <button
                    key={format}
                    className="p-3 border border-gray-300 dark:border-gray-600 rounded-lg text-center hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:border-blue-500 dark:hover:border-blue-400 transition-all duration-200"
                  >
                    {format}
                  </button>
                ))}
              </div>
            </div>
            
            <div className="space-y-4">
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">
                Configuración
              </h4>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Calidad (1-100)
                  </label>
                  <input
                    type="range"
                    min="1"
                    max="100"
                    defaultValue="80"
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="flex items-center space-x-2">
                    <input type="checkbox" className="rounded" />
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      Mantener metadatos
                    </span>
                  </label>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-8 pt-6 border-t border-gray-200 dark:border-gray-700">
            <button className="w-full bg-green-600 hover:bg-green-700 text-white py-3 px-6 rounded-lg font-semibold text-lg transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed">
              Convertir Imágenes
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}