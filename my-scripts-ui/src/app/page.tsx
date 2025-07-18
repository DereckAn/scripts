import { ArrowRight, Globe, Image, Zap, Camera, Brain } from "lucide-react";
import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-50 via-stone-100 to-stone-200 dark:from-stone-950 dark:via-stone-900 dark:to-stone-800">
      {/* Background Pattern */}
      <div className="absolute inset-0 bg-grid-stone-900/[0.04] dark:bg-grid-stone-100/[0.02]" />

      <div className="relative">
        <div className="container mx-auto px-4 py-16 sm:px-6 lg:px-8">
          {/* Header Section */}
          <div className="text-center mb-20">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-r from-stone-900 to-stone-700 dark:from-stone-100 dark:to-stone-300 rounded-xl mb-8 shadow-lg">
              <Zap className="w-8 h-8 text-white dark:text-stone-900" />
            </div>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-stone-900 dark:text-stone-100 mb-6">
              My Scripts UI
            </h1>
            <p className="text-lg text-stone-600 dark:text-stone-400 max-w-2xl mx-auto leading-relaxed">
              Una colección de herramientas útiles para desarrolladores.
              Convierte imágenes, haz web scraping y genera scripts de
              instalación automática.
            </p>
          </div>

          {/* Cards Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6 mb-20">
            <Link href="/convert-images" className="group">
              <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl p-8 border border-stone-200/60 dark:border-stone-800/60 hover:bg-white dark:hover:bg-stone-900 hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
                <div className="text-center">
                  <div className="inline-flex items-center justify-center w-14 h-14 bg-emerald-100 dark:bg-emerald-900/30 rounded-xl mb-6 group-hover:scale-110 transition-transform duration-300">
                    <Image className="w-7 h-7 text-emerald-600 dark:text-emerald-400" />
                  </div>
                  <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 mb-3">
                    Convertir Imágenes
                  </h3>
                  <p className="text-stone-600 dark:text-stone-400 mb-6 text-sm leading-relaxed">
                    Convierte tus imágenes a diferentes formatos como JPEG, PNG,
                    WEBP y AVIF de manera rápida y sencilla.
                  </p>
                  <div className="inline-flex items-center text-emerald-600 dark:text-emerald-400 font-medium text-sm group-hover:text-emerald-700 dark:group-hover:text-emerald-300">
                    Comenzar
                    <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </div>
            </Link>

            <Link href="/web-scraping" className="group">
              <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl p-8 border border-stone-200/60 dark:border-stone-800/60 hover:bg-white dark:hover:bg-stone-900 hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
                <div className="text-center">
                  <div className="inline-flex items-center justify-center w-14 h-14 bg-violet-100 dark:bg-violet-900/30 rounded-xl mb-6 group-hover:scale-110 transition-transform duration-300">
                    <Globe className="w-7 h-7 text-violet-600 dark:text-violet-400" />
                  </div>
                  <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 mb-3">
                    Web Scraping
                  </h3>
                  <p className="text-stone-600 dark:text-stone-400 mb-6 text-sm leading-relaxed">
                    Extrae datos de cualquier sitio web de forma automatizada.
                    Obtén texto, enlaces, imágenes y más.
                  </p>
                  <div className="inline-flex items-center text-violet-600 dark:text-violet-400 font-medium text-sm group-hover:text-violet-700 dark:group-hover:text-violet-300">
                    Comenzar
                    <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </div>
            </Link>

            <Link href="/generate-scripts" className="group">
              <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl p-8 border border-stone-200/60 dark:border-stone-800/60 hover:bg-white dark:hover:bg-stone-900 hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
                <div className="text-center">
                  <div className="inline-flex items-center justify-center w-14 h-14 bg-amber-100 dark:bg-amber-900/30 rounded-xl mb-6 group-hover:scale-110 transition-transform duration-300">
                    <Zap className="w-7 h-7 text-amber-600 dark:text-amber-400" />
                  </div>
                  <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 mb-3">
                    Generar Scripts
                  </h3>
                  <p className="text-stone-600 dark:text-stone-400 mb-6 text-sm leading-relaxed">
                    Crea scripts personalizados para instalar aplicaciones
                    automáticamente en Mac y Linux.
                  </p>
                  <div className="inline-flex items-center text-amber-600 dark:text-amber-400 font-medium text-sm group-hover:text-amber-700 dark:group-hover:text-amber-300">
                    Comenzar
                    <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </div>
            </Link>

            <Link href="/instagram-photos" className="group">
              <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl p-8 border border-stone-200/60 dark:border-stone-800/60 hover:bg-white dark:hover:bg-stone-900 hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
                <div className="text-center">
                  <div className="inline-flex items-center justify-center w-14 h-14 bg-pink-100 dark:bg-pink-900/30 rounded-xl mb-6 group-hover:scale-110 transition-transform duration-300">
                    <Camera className="w-7 h-7 text-pink-600 dark:text-pink-400" />
                  </div>
                  <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 mb-3">
                    Instagram Photos
                  </h3>
                  <p className="text-stone-600 dark:text-stone-400 mb-6 text-sm leading-relaxed">
                    Visualiza y descarga fotos de perfiles públicos de Instagram de manera fácil y rápida.
                  </p>
                  <div className="inline-flex items-center text-pink-600 dark:text-pink-400 font-medium text-sm group-hover:text-pink-700 dark:group-hover:text-pink-300">
                    Comenzar
                    <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </div>
            </Link>

            <Link href="/image-analysis" className="group">
              <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-2xl p-8 border border-stone-200/60 dark:border-stone-800/60 hover:bg-white dark:hover:bg-stone-900 hover:shadow-xl hover:-translate-y-1 transition-all duration-300">
                <div className="text-center">
                  <div className="inline-flex items-center justify-center w-14 h-14 bg-purple-100 dark:bg-purple-900/30 rounded-xl mb-6 group-hover:scale-110 transition-transform duration-300">
                    <Brain className="w-7 h-7 text-purple-600 dark:text-purple-400" />
                  </div>
                  <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 mb-3">
                    Análisis con IA
                  </h3>
                  <p className="text-stone-600 dark:text-stone-400 mb-6 text-sm leading-relaxed">
                    Analiza imágenes con IA local sin censura. Compatible con Ollama, LM Studio y más.
                  </p>
                  <div className="inline-flex items-center text-purple-600 dark:text-purple-400 font-medium text-sm group-hover:text-purple-700 dark:group-hover:text-purple-300">
                    Comenzar
                    <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </div>
            </Link>
          </div>

          {/* CTA Section */}
          <div className="text-center">
            <div className="bg-gradient-to-r from-stone-900 to-stone-800 dark:from-stone-100 dark:to-stone-200 rounded-2xl p-10 text-white dark:text-stone-900 shadow-2xl relative overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-r from-stone-900/90 to-stone-800/90 dark:from-stone-100/90 dark:to-stone-200/90" />
              <div className="relative z-10">
                <h2 className="text-2xl md:text-3xl font-bold mb-4">
                  ¿Listo para ser más productivo?
                </h2>
                <p className="text-lg opacity-90 mb-8 max-w-md mx-auto">
                  Todas las herramientas que necesitas en un solo lugar
                </p>
                <div className="flex justify-center space-x-6 text-3xl">
                  <div className="animate-bounce [animation-delay:0ms]">🚀</div>
                  <div className="animate-bounce [animation-delay:150ms]">
                    ⚡
                  </div>
                  <div className="animate-bounce [animation-delay:300ms]">
                    🎯
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
