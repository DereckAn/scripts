import React, { useState } from 'react';
import type { FormState } from '../lib/types';
import { ScriptGenerator as Generator } from '../lib/scriptGenerator';
import { PlatformStep } from './steps/PlatformStep';
import { DistributionStep } from './steps/DistributionStep';
import { ApplicationStep } from './steps/ApplicationStep';
import { PreviewStep } from './steps/PreviewStep';
import { ProgressBar } from './ProgressBar';

const generator = new Generator();

export function ScriptGenerator() {
  const [formState, setFormState] = useState<FormState>({
    step: 1,
    platform: '',
    distribution: '',
    selectedApps: [],
    generatedScript: ''
  });

  const updateFormState = (updates: Partial<FormState>) => {
    setFormState(prev => ({ ...prev, ...updates }));
  };

  const nextStep = () => {
    if (formState.step < 4) {
      let nextStepNum = formState.step + 1;

      // Skip distribution step for non-Linux platforms
      if (nextStepNum === 2 && formState.platform !== 'linux') {
        nextStepNum = 3;
      }

      setFormState(prev => ({ ...prev, step: nextStepNum }));
    }
  };

  const previousStep = () => {
    if (formState.step > 1) {
      let prevStepNum = formState.step - 1;

      // Skip distribution step for non-Linux platforms when going back
      if (prevStepNum === 2 && formState.platform !== 'linux') {
        prevStepNum = 1;
      }

      setFormState(prev => ({ ...prev, step: prevStepNum }));
    }
  };

  const generateScript = () => {
    try {
      const script = generator.generateScript({
        platform: formState.platform as 'windows' | 'macos' | 'linux',
        distribution: formState.distribution,
        selectedApps: formState.selectedApps
      });

      updateFormState({ generatedScript: script, step: 4 });
    } catch (error) {
      console.error('Error generating script:', error);
    }
  };

  const resetForm = () => {
    setFormState({
      step: 1,
      platform: '',
      distribution: '',
      selectedApps: [],
      generatedScript: ''
    });
  };

  const stepProps = {
    formState,
    onUpdate: updateFormState,
    onNext: nextStep,
    onPrevious: previousStep
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">
          Script Installer Generator
        </h1>
        <p className="text-xl text-gray-600">
          Generate custom installation scripts for Windows, macOS, and Linux
        </p>
      </div>

      <ProgressBar
        currentStep={formState.step}
        platform={formState.platform as 'windows' | 'macos' | 'linux'}
      />

      <div className="bg-white rounded-lg shadow-lg p-8 mt-8">
        {formState.step === 1 && <PlatformStep {...stepProps} />}
        {formState.step === 2 && <DistributionStep {...stepProps} />}
        {formState.step === 3 && (
          <ApplicationStep
            {...stepProps}
            onGenerate={generateScript}
          />
        )}
        {formState.step === 4 && (
          <PreviewStep
            {...stepProps}
            onReset={resetForm}
          />
        )}
      </div>
    </div>
  );
}
