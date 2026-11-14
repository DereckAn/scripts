import { Brain, Camera, Globe, Image, Music, Share2, Terminal } from 'lucide-react';

export const tools = [
  { href: '/convert-images', title: 'Convertir imágenes', nav: 'Convertidor Imágenes', category: 'Medios', icon: Image,
    description: 'Convierte y redimensiona imágenes por lotes. Ajusta el formato, la calidad y las dimensiones antes de descargar.',
    features: ['JPEG, PNG, WebP y AVIF', 'Tamaño y calidad configurables'], detail: 'Procesamiento en el navegador', action: 'Abrir convertidor', badge: 'Lotes' },
  { href: '/web-scraping', title: 'Web Scraping', nav: 'Web Scraping', category: 'Extracción', icon: Globe,
    description: 'Extrae contenido web y prepara documentos Markdown o MDX con selectores, filtros y opciones de exportación.',
    features: ['Exportación Markdown / MDX', 'Selectores y seguimiento de enlaces'], detail: 'Contenido y documentos', action: 'Iniciar extracción', badge: 'MDX' },
  { href: '/generate-scripts', title: 'Generar scripts de instalación', nav: 'Generador Scripts', category: 'Sistema', icon: Terminal,
    description: 'Prepara scripts personalizados para instalar tus aplicaciones y configurar tu entorno en macOS o Linux.',
    features: ['Selección de aplicaciones', 'Scripts para macOS y Linux'], detail: 'Instalación y configuración', action: 'Configurar script', badge: 'Bash' },
  { href: '/instagram-photos', title: 'Fotos de Instagram', nav: 'Fotos Instagram', category: 'Social', icon: Camera,
    description: 'Consulta perfiles y publicaciones de Instagram. Explora las fotografías y las opciones de descarga disponibles.',
    features: ['Exploración de perfiles', 'Vista de publicaciones y fotografías'], detail: 'Perfiles y publicaciones', action: 'Buscar perfil', badge: '' },
  { href: '/twitter-photos', title: 'Fotos de Twitter / X', nav: 'Fotos Twitter/X', category: 'Social', icon: Share2,
    description: 'Explora el contenido multimedia de perfiles de Twitter/X y encuentra las imágenes que quieres descargar.',
    features: ['Galería de imágenes', 'Enlaces a las publicaciones originales'], detail: 'Contenido multimedia', action: 'Buscar usuario', badge: '' },
  { href: '/image-analysis', title: 'Análisis visual con IA', nav: 'Análisis Visual IA', category: 'IA local', icon: Brain,
    description: 'Conecta un proveedor local como Ollama o LM Studio para analizar imágenes y exportar los resultados.',
    features: ['Ollama y LM Studio', 'Exportación JSON / CSV'], detail: 'Proveedor local configurable', action: 'Abrir laboratorio IA', badge: 'Local AI' },
  { href: '/svg-to-pdf', title: 'SVG a PDF / Partituras musicales', nav: 'SVG a PDF', category: 'Música', icon: Music,
    description: 'Reúne tus partituras SVG en un PDF vectorial. Conserva el orden de las páginas y elige tamaño original, A4 o Carta.',
    features: ['Orden natural por nombre', 'PDF único o archivos individuales en ZIP', 'Tamaños original, A4 y Carta'], detail: 'jsPDF + svg2pdf', action: 'Compilar partituras', badge: 'Música' },
];

export const navigationGroups = [
  { name: 'Medios & archivos', paths: ['/convert-images', '/svg-to-pdf', '/image-analysis'] },
  { name: 'Extracción & social', paths: ['/web-scraping', '/instagram-photos', '/twitter-photos'] },
  { name: 'Automatización', paths: ['/generate-scripts'] },
];
