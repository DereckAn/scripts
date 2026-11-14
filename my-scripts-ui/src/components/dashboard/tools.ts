import { Image, Music, Terminal } from 'lucide-react';

export const tools = [
  { href: '/convert-images', title: 'Convertir imágenes', nav: 'Convertidor Imágenes', category: 'Medios', icon: Image,
    description: 'Convierte y redimensiona imágenes por lotes. Ajusta el formato, la calidad y las dimensiones antes de descargar.',
    features: ['JPEG, PNG, WebP y AVIF', 'Tamaño y calidad configurables'], detail: 'Procesamiento en el navegador', action: 'Abrir convertidor', badge: 'Lotes' },
  { href: '/generate-scripts', title: 'Generar scripts de instalación', nav: 'Generador Scripts', category: 'Sistema', icon: Terminal,
    description: 'Prepara scripts personalizados para instalar tus aplicaciones y configurar tu entorno en macOS o Linux.',
    features: ['Selección de aplicaciones', 'Scripts para macOS y Linux'], detail: 'Instalación y configuración', action: 'Configurar script', badge: 'Bash' },
  { href: '/svg-to-pdf', title: 'SVG a PDF / Partituras musicales', nav: 'SVG a PDF', category: 'Música', icon: Music,
    description: 'Reúne tus partituras SVG en un PDF vectorial. Conserva el orden de las páginas y elige tamaño original, A4 o Carta.',
    features: ['Orden natural por nombre', 'PDF único o archivos individuales en ZIP', 'Tamaños original, A4 y Carta'], detail: 'jsPDF + svg2pdf', action: 'Compilar partituras', badge: 'Música' },
];

export const navigationGroups = [
  { name: 'Medios & archivos', paths: ['/convert-images', '/svg-to-pdf'] },
  { name: 'Automatización', paths: ['/generate-scripts'] },
];
