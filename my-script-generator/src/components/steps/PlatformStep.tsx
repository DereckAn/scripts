import React from 'react';
import type { StepProps } from '../../lib/types';

export function PlatformStep({ formState, onUpdate, onNext }: StepProps) {
  const platforms = [
    {
      id: 'windows',
      name: 'Windows',
      icon: '🪟',
      description: 'Windows 10/11 with winget package manager',
      color: 'bg-blue-50 border-blue-200 hover:bg-blue-100'
    },
    {
      id: 'macos',
      name: 'macOS',
      icon: '🍎',
      description: 'macOS with Homebrew package manager',
      color: 'bg-gray-50 border-gray-200 hover:bg-gray-100'
    },
    {
      id: 'linux',
      name: 'Linux',
      icon: '🐧',
      description: 'Various Linux distributions',
      color: 'bg-orange-50 border-orange-200 hover:bg-orange-100'
    }
  ];

  const handlePlatformSelect = (platform: string) => {
    onUpdate({ platform: platform as 'windows' | 'macos' | 'linux' });
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">
        Choose Your Platform
      </h2>
      <p className="text-gray-600 mb-6">
        Select the operating system for which you want to generate an installation script.
      </p>

      <div className="grid md:grid-cols-3 gap-4 mb-8">
        {platforms.map((platform) => (
          <button
            key={platform.id}
            onClick={() => handlePlatformSelect(platform.id)}
            className={`
              p-6 rounded-lg border-2 transition-all duration-200 text-left
              ${formState.platform === platform.id
                ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200'
                : platform.color
              }
            `}
          >
            <div className="text-3xl mb-3">{platform.icon}</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              {platform.name}
            </h3>
            <p className="text-sm text-gray-600">
              {platform.description}
            </p>
          </button>
        ))}
      </div>

      <div className="flex justify-end">
        <button
          onClick={onNext}
          disabled={!formState.platform}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
        >
          Next Step →
        </button>
      </div>
    </div>
  );
}
