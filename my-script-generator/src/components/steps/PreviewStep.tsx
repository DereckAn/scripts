import React, { useState } from 'react';
import type { StepProps } from '../../lib/types';

interface PreviewStepProps extends StepProps {
  onReset: () => void;
}

export function PreviewStep({ formState, onPrevious, onReset }: PreviewStepProps) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(formState.generatedScript);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  const downloadScript = () => {
    const element = document.createElement('a');
    const file = new Blob([formState.generatedScript], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);

    const extension = formState.platform === 'windows' ? 'ps1' : 'sh';
    const filename = `install-script.${extension}`;
    element.download = filename;

    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const getFileExtension = () => {
    return formState.platform === 'windows' ? 'ps1' : 'sh';
  };

  const getLanguage = () => {
    return formState.platform === 'windows' ? 'powershell' : 'bash';
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">
        Your Installation Script
      </h2>
      <p className="text-gray-600 mb-6">
        Your custom installation script is ready! Copy it or download as a .{getFileExtension()} file.
      </p>

      {/* Script Info */}
      <div className="bg-gray-50 rounded-lg p-4 mb-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div>
            <span className="font-medium text-gray-700">Platform:</span>
            <div className="mt-1">
              {formState.platform === 'windows' && '🪟 Windows'}
              {formState.platform === 'macos' && '🍎 macOS'}
              {formState.platform === 'linux' && `🐧 Linux (${formState.distribution})`}
            </div>
          </div>
          <div>
            <span className="font-medium text-gray-700">Applications:</span>
            <div className="mt-1">{formState.selectedApps.length} selected</div>
          </div>
          <div>
            <span className="font-medium text-gray-700">File Type:</span>
            <div className="mt-1">.{getFileExtension()} ({getLanguage()})</div>
          </div>
        </div>
      </div>

      {/* Script Preview */}
      <div className="relative">
        <div className="absolute top-4 right-4 flex space-x-2 z-10">
          <button
            onClick={copyToClipboard}
            className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
              copied
                ? 'bg-green-600 text-white'
                : 'bg-gray-600 text-white hover:bg-gray-700'
            }`}
          >
            {copied ? '✓ Copied!' : '📋 Copy'}
          </button>
          <button
            onClick={downloadScript}
            className="px-3 py-1 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            💾 Download
          </button>
        </div>

        <pre className="bg-gray-900 text-gray-100 p-6 rounded-lg overflow-x-auto text-sm">
          <code>{formState.generatedScript}</code>
        </pre>
      </div>

      {/* Usage Instructions */}
      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 className="font-medium text-blue-900 mb-2">📋 Usage Instructions</h3>
        <div className="text-sm text-blue-800 space-y-2">
          {formState.platform === 'windows' && (
            <>
              <p>1. Save the script as <code>install-script.ps1</code></p>
              <p>2. Right-click on the file and select "Run with PowerShell"</p>
              <p>3. Or run from PowerShell as Administrator: <code>.\install-script.ps1</code></p>
            </>
          )}
          {(formState.platform === 'macos' || formState.platform === 'linux') && (
            <>
              <p>1. Save the script as <code>install-script.sh</code></p>
              <p>2. Make it executable: <code>chmod +x install-script.sh</code></p>
              <p>3. Run the script: <code>./install-script.sh</code></p>
            </>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-between mt-8">
        <button
          onClick={onPrevious}
          className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
        >
          ← Edit Selection
        </button>
        <button
          onClick={onReset}
          className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
        >
          🎉 Create Another Script
        </button>
      </div>
    </div>
  );
}
