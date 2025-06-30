import React, { useState } from 'react';
import type { StepProps } from '../../lib/types';

interface PreviewStepProps extends StepProps {
  onReset: () => void;
}

export function PreviewStep({ formState, onPrevious, onReset }: PreviewStepProps) {
  const [copied, setCopied] = useState(false);
  const [quickCommand, setQuickCommand] = useState('');
  const [commandCopied, setCommandCopied] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState('');

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

  const generateQuickCommand = async () => {
    if (formState.platform === 'windows') {
      setError('Quick install commands are only available for macOS and Linux');
      return;
    }

    setIsGenerating(true);
    setError('');
    
    try {
      const response = await fetch('/api/generate-script', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          platform: formState.platform,
          distribution: formState.distribution,
          selectedApps: formState.selectedApps,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to generate quick command');
      }

      const data = await response.json();
      setQuickCommand(data.command);
    } catch (err) {
      setError('Failed to generate quick install command. Please try again.');
      console.error('Error generating command:', err);
    } finally {
      setIsGenerating(false);
    }
  };

  const copyCommandToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(quickCommand);
      setCommandCopied(true);
      setTimeout(() => setCommandCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy command: ', err);
    }
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

      {/* Quick Install Command Section */}
      {(formState.platform === 'macos' || formState.platform === 'linux') && (
        <div className="mt-6 bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-200 rounded-lg p-6">
          <h3 className="font-bold text-purple-900 mb-3 flex items-center">
            ⚡ Quick Install Command
            <span className="ml-2 text-xs bg-purple-200 text-purple-800 px-2 py-1 rounded">NEW</span>
          </h3>
          <p className="text-purple-800 text-sm mb-4">
            Generate a one-line command that others can copy and run directly in their terminal. 
            Perfect for sharing with teammates or documentation!
          </p>

          {!quickCommand && (
            <button
              onClick={generateQuickCommand}
              disabled={isGenerating}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center"
            >
              {isGenerating ? (
                <>
                  <svg className="animate-spin -ml-1 mr-3 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Generating...
                </>
              ) : (
                '🚀 Generate Quick Command'
              )}
            </button>
          )}

          {error && (
            <div className="mt-4 p-3 bg-red-100 border border-red-300 rounded text-red-700 text-sm">
              {error}
            </div>
          )}

          {quickCommand && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-purple-900">Your Quick Install Command:</span>
                <button
                  onClick={copyCommandToClipboard}
                  className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                    commandCopied
                      ? 'bg-green-500 text-white'
                      : 'bg-purple-600 text-white hover:bg-purple-700'
                  }`}
                >
                  {commandCopied ? '✓ Copied!' : '📋 Copy'}
                </button>
              </div>
              <div className="bg-gray-900 text-green-400 p-3 rounded font-mono text-sm overflow-x-auto">
                {quickCommand}
              </div>
              <p className="text-xs text-purple-700 mt-2">
                ⏰ This command expires in 10 minutes for security
              </p>
            </div>
          )}
        </div>
      )}

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
              <p><strong>Option 1 - Quick Command:</strong></p>
              <p>• Generate a quick command above and share it with others</p>
              <p>• Recipients can copy-paste directly into terminal</p>
              <p className="mb-3">• No file download needed!</p>
              
              <p><strong>Option 2 - Manual Download:</strong></p>
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
