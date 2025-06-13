import React from 'react';

interface ProgressBarProps {
  currentStep: number;
  platform: 'windows' | 'macos' | 'linux' | '';
}

export function ProgressBar({ currentStep, platform }: ProgressBarProps) {
  const steps = [
    { number: 1, title: 'Platform', icon: '💻' },
    { number: 2, title: 'Distribution', icon: '🐧', onlyLinux: true },
    { number: 3, title: 'Applications', icon: '📦' },
    { number: 4, title: 'Preview', icon: '👀' }
  ];

  const visibleSteps = steps.filter(step =>
    !step.onlyLinux || platform === 'linux'
  );

  return (
    <div className="flex items-center justify-center">
      {visibleSteps.map((step, index) => (
        <React.Fragment key={step.number}>
          <div className="flex items-center">
            <div className={`
              flex items-center justify-center w-12 h-12 rounded-full border-2
              ${currentStep >= step.number
                ? 'bg-blue-600 border-blue-600 text-white'
                : 'bg-white border-gray-300 text-gray-500'
              }
            `}>
              <span className="text-sm font-semibold">
                {currentStep > step.number ? '✓' : step.icon}
              </span>
            </div>
            <div className="ml-3 text-sm">
              <p className={`font-medium ${
                currentStep >= step.number ? 'text-blue-600' : 'text-gray-500'
              }`}>
                Step {index + 1}
              </p>
              <p className="text-gray-500">{step.title}</p>
            </div>
          </div>

          {index < visibleSteps.length - 1 && (
            <div className={`
              flex-1 h-0.5 mx-8
              ${currentStep > step.number ? 'bg-blue-600' : 'bg-gray-300'}
            `} />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}
