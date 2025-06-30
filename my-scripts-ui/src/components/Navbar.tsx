'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import ThemeToggle from './ThemeToggle';

export default function Navbar() {
  const [isOpen, setIsOpen] = useState(false);
  const pathname = usePathname();

  const navItems = [
    { name: 'Convertir Imágenes', href: '/convert-images', icon: '🖼️' },
    { name: 'Web Scraping', href: '/web-scraping', icon: '🕷️' },
    { name: 'Generar Scripts', href: '/generate-scripts', icon: '⚡' },
  ];

  const toggleNavbar = () => {
    setIsOpen(!isOpen);
  };

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 transition-opacity duration-300"
          onClick={() => setIsOpen(false)}
        />
      )}
      
      {/* Hamburger Button */}
      <button
        onClick={toggleNavbar}
        className="fixed top-4 left-4 z-50 p-3 rounded-xl bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-105"
      >
        <div className="flex flex-col w-6 h-6 justify-center items-center">
          <span className={`block w-6 h-0.5 bg-current transition-all duration-300 ${isOpen ? 'rotate-45 translate-y-1' : ''}`} />
          <span className={`block w-6 h-0.5 bg-current transition-all duration-300 my-1 ${isOpen ? 'opacity-0' : ''}`} />
          <span className={`block w-6 h-0.5 bg-current transition-all duration-300 ${isOpen ? '-rotate-45 -translate-y-1' : ''}`} />
        </div>
      </button>

      {/* Sidebar */}
      <div className={`fixed top-0 left-0 h-full w-80 bg-white dark:bg-gray-900 shadow-2xl z-50 transform transition-transform duration-500 ease-in-out ${
        isOpen ? 'translate-x-0' : '-translate-x-full'
      }`}>
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
              My Scripts UI
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Herramientas útiles para desarrolladores
            </p>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-6">
            <ul className="space-y-3">
              {navItems.map((item, index) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={() => setIsOpen(false)}
                    className={`flex items-center p-4 rounded-xl transition-all duration-300 group hover:scale-105 ${
                      pathname === item.href
                        ? 'bg-blue-600 text-white shadow-lg'
                        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                    }`}
                    style={{
                      animationDelay: `${index * 100}ms`
                    }}
                  >
                    <span className="text-2xl mr-4 group-hover:scale-110 transition-transform duration-300">
                      {item.icon}
                    </span>
                    <span className="font-medium">{item.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          {/* Footer */}
          <div className="p-6 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                Tema
              </span>
              <ThemeToggle />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}