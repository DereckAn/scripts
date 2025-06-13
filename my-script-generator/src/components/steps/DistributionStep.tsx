import React from 'react';
import type { StepProps } from '../../lib/types';
import { ScriptGenerator } from '../../lib/scriptGenerator';

const generator = new ScriptGenerator();

export function DistributionStep({ formState, onUpdate, onNext, onPrevious }: StepProps) {
  const distributions = generator.getDistributions();

  const handleDistributionSelect = (distribution: string) => {
    onUpdate({ distribution });
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">
        Choose Linux Distribution
      </h2>
      <p className="text-gray-600 mb-6">
        Select your Linux distribution to use the appropriate package manager.
      </p>

      <div className="grid md:grid-cols-2 gap-4 mb-8">
        {Object.entries(distributions).map(([id, dist]) => (
          <button
            key={id}
            onClick={() => handleDistributionSelect(id)}
            className={`
              p-4 rounded-lg border-2 transition-all duration-200 text-left
              ${formState.distribution === id
                ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200'
                : 'bg-white border-gray-200 hover:bg-gray-50'
              }
            `}
          >
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              {dist.name}
            </h3>
            <p className="text-sm text-gray-600">
              Package Manager: <code className="bg-gray-100 px-2 py-1 rounded text-xs">
                {dist.packageManager}
              </code>
            </p>
          </button>
        ))}
      </div>

      <div className="flex justify-between">
        <button
          onClick={onPrevious}
          className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
        >
          ← Previous
        </button>
        <button
          onClick={onNext}
          disabled={!formState.distribution}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
        >
          Next Step →
        </button>
      </div>
    </div>
  );
}
