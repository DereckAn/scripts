'use client';

import { useState, useEffect } from 'react';

export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme) {
      setIsDark(savedTheme === 'dark');
    } else {
      setIsDark(prefersDark);
    }
  }, []);

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [isDark]);

  const toggleTheme = () => {
    setIsDark(!isDark);
  };

  return (
    <button
      onClick={toggleTheme}
      className="p-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-all duration-300 hover:scale-110"
      aria-label="Toggle theme"
    >
      <div className="relative w-6 h-6 overflow-hidden">
        <div className={`absolute inset-0 transition-transform duration-500 ${isDark ? 'translate-y-0' : '-translate-y-8'}`}>
          <div className="text-lg">🌙</div>
        </div>
        <div className={`absolute inset-0 transition-transform duration-500 ${isDark ? 'translate-y-8' : 'translate-y-0'}`}>
          <div className="text-lg">☀️</div>
        </div>
      </div>
    </button>
  );
}