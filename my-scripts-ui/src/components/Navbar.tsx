"use client";

import { Globe, Image, Menu, Palette, X, Zap } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import ThemeToggle from "./ThemeToggle";

export default function Navbar() {
  const [isOpen, setIsOpen] = useState(false);
  const pathname = usePathname();

  const navItems = [
    {
      name: "Convertir Imágenes",
      href: "/convert-images",
      icon: Image,
      color: "emerald",
    },
    {
      name: "Web Scraping",
      href: "/web-scraping",
      icon: Globe,
      color: "violet",
    },
    {
      name: "Generar Scripts",
      href: "/generate-scripts",
      icon: Zap,
      color: "amber",
    },
  ];

  const toggleNavbar = () => {
    setIsOpen(!isOpen);
  };

  const getColorClasses = (color: string, isActive: boolean) => {
    if (isActive) {
      return {
        emerald: "bg-emerald-600 text-white shadow-lg shadow-emerald-600/25",
        violet: "bg-violet-600 text-white shadow-lg shadow-violet-600/25",
        amber: "bg-amber-600 text-white shadow-lg shadow-amber-600/25",
      }[color];
    }
    return {
      emerald:
        "hover:bg-emerald-50 dark:hover:bg-emerald-950/30 hover:text-emerald-700 dark:hover:text-emerald-300",
      violet:
        "hover:bg-violet-50 dark:hover:bg-violet-950/30 hover:text-violet-700 dark:hover:text-violet-300",
      amber:
        "hover:bg-amber-50 dark:hover:bg-amber-950/30 hover:text-amber-700 dark:hover:text-amber-300",
    }[color];
  };

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-stone-900/20 backdrop-blur-sm z-40 transition-opacity duration-300"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Hamburger Button */}
      <button
        onClick={toggleNavbar}
        className="fixed top-6 left-6 z-50 p-3 rounded-xl bg-white/90 dark:bg-stone-900/90 backdrop-blur-sm border border-stone-200/50 dark:border-stone-800/50 text-stone-900 dark:text-stone-100 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-105"
      >
        {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Sidebar */}
      <div
        className={`fixed top-0 left-0 h-full w-80 bg-white/95 dark:bg-stone-900/95 backdrop-blur-xl border-r border-stone-200/50 dark:border-stone-800/50 shadow-2xl z-50 transform transition-transform duration-500 ease-in-out ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="p-8 border-b border-stone-200/50 dark:border-stone-800/50">
            <div className="flex items-center mb-3">
              <div className="inline-flex items-center justify-center w-10 h-10 bg-gradient-to-r from-stone-900 to-stone-700 dark:from-stone-100 dark:to-stone-300 rounded-lg mr-3">
                <Zap className="w-5 h-5 text-white dark:text-stone-900" />
              </div>
              <h2 className="text-xl font-bold text-stone-900 dark:text-stone-100">
                My Scripts UI
              </h2>
            </div>
            <p className="text-sm text-stone-600 dark:text-stone-400">
              Herramientas útiles para desarrolladores
            </p>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-6">
            <div className="space-y-2">
              {navItems.map((item, index) => {
                const IconComponent = item.icon;
                const isActive = pathname === item.href;

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setIsOpen(false)}
                    className={`flex items-center p-4 rounded-xl transition-all duration-300 group hover:-translate-y-0.5 ${
                      isActive
                        ? getColorClasses(item.color, true)
                        : `text-stone-700 dark:text-stone-300 ${getColorClasses(
                            item.color,
                            false
                          )}`
                    }`}
                    style={{
                      animationDelay: `${index * 100}ms`,
                    }}
                  >
                    <div
                      className={`inline-flex items-center justify-center w-10 h-10 rounded-lg mr-4 transition-all duration-300 group-hover:scale-110 ${
                        isActive
                          ? "bg-white/20"
                          : `bg-${item.color}-100 dark:bg-${item.color}-950/30`
                      }`}
                    >
                      <IconComponent
                        className={`w-5 h-5 ${
                          isActive
                            ? "text-white"
                            : `text-${item.color}-600 dark:text-${item.color}-400`
                        }`}
                      />
                    </div>
                    <span className="font-medium">{item.name}</span>
                  </Link>
                );
              })}
            </div>
          </nav>

          {/* Footer */}
          <div className="p-6 border-t border-stone-200/50 dark:border-stone-800/50">
            <div className="flex items-center justify-between p-4 rounded-xl bg-stone-50/50 dark:bg-stone-800/50">
              <div className="flex items-center">
                <div className="inline-flex items-center justify-center w-8 h-8 bg-stone-200 dark:bg-stone-700 rounded-lg mr-3">
                  <Palette className="w-4 h-4 text-stone-600 dark:text-stone-400" />
                </div>
                <span className="text-sm font-medium text-stone-700 dark:text-stone-300">
                  Tema
                </span>
              </div>
              <ThemeToggle />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
