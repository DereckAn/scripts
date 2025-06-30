import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen p-8 pt-20">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <h1 className="text-6xl font-bold text-gray-900 dark:text-white mb-6">
            My Scripts UI
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-400 max-w-2xl mx-auto">
            Una colección de herramientas útiles para desarrolladores. 
            Convierte imágenes, haz web scraping y genera scripts de instalación automática.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16">
          <Link href="/convert-images" className="group">
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-8 border border-gray-200 dark:border-gray-700 hover:shadow-2xl hover:scale-105 transition-all duration-300">
              <div className="text-center">
                <div className="text-6xl mb-4 group-hover:scale-110 transition-transform duration-300">🖼️</div>
                <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
                  Convertir Imágenes
                </h3>
                <p className="text-gray-600 dark:text-gray-400 mb-4">
                  Convierte tus imágenes a diferentes formatos como JPEG, PNG, WEBP y AVIF de manera rápida y sencilla.
                </p>
                <div className="inline-flex items-center text-blue-600 dark:text-blue-400 font-medium group-hover:text-blue-700 dark:group-hover:text-blue-300">
                  Comenzar →
                </div>
              </div>
            </div>
          </Link>

          <Link href="/web-scraping" className="group">
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-8 border border-gray-200 dark:border-gray-700 hover:shadow-2xl hover:scale-105 transition-all duration-300">
              <div className="text-center">
                <div className="text-6xl mb-4 group-hover:scale-110 transition-transform duration-300">🕷️</div>
                <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
                  Web Scraping
                </h3>
                <p className="text-gray-600 dark:text-gray-400 mb-4">
                  Extrae datos de cualquier sitio web de forma automatizada. Obtén texto, enlaces, imágenes y más.
                </p>
                <div className="inline-flex items-center text-blue-600 dark:text-blue-400 font-medium group-hover:text-blue-700 dark:group-hover:text-blue-300">
                  Comenzar →
                </div>
              </div>
            </div>
          </Link>

          <Link href="/generate-scripts" className="group">
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-8 border border-gray-200 dark:border-gray-700 hover:shadow-2xl hover:scale-105 transition-all duration-300">
              <div className="text-center">
                <div className="text-6xl mb-4 group-hover:scale-110 transition-transform duration-300">⚡</div>
                <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">
                  Generar Scripts
                </h3>
                <p className="text-gray-600 dark:text-gray-400 mb-4">
                  Crea scripts personalizados para instalar aplicaciones automáticamente en Mac y Linux.
                </p>
                <div className="inline-flex items-center text-blue-600 dark:text-blue-400 font-medium group-hover:text-blue-700 dark:group-hover:text-blue-300">
                  Comenzar →
                </div>
              </div>
            </div>
          </Link>
        </div>

        <div className="text-center">
          <div className="bg-gradient-to-r from-blue-600 to-purple-600 rounded-2xl p-8 text-white">
            <h2 className="text-3xl font-bold mb-4">
              ¿Listo para ser más productivo?
            </h2>
            <p className="text-xl opacity-90 mb-6">
              Todas las herramientas que necesitas en un solo lugar
            </p>
            <div className="flex justify-center space-x-4 text-4xl">
              <span>🚀</span>
              <span>⚡</span>
              <span>🎯</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
