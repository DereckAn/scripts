import type { Metadata } from 'next';
import Dashboard from '@/components/dashboard/Dashboard';

export const metadata: Metadata = {
  title: 'Panel de Utilidades | My Scripts UI',
  description: 'Tu caja de herramientas para medios, automatización, extracción y análisis local.',
};

export default function Home() {
  return <Dashboard />;
}
