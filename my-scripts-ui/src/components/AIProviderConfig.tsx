'use client';

import { useState, useEffect } from 'react';
import { AIProviderConfig, AI_PROVIDER_PRESETS } from '@/types/image-analysis';
import { testAIConnection } from '@/utils/image-analysis';

interface AIProviderConfigProps {
  config: AIProviderConfig;
  onChange: (config: AIProviderConfig) => void;
}

export default function AIProviderConfigComponent({ 
  config, 
  onChange 
}: AIProviderConfigProps) {
  const [connectionStatus, setConnectionStatus] = useState<{
    testing: boolean;
    connected: boolean;
    error?: string;
  }>({ testing: false, connected: false });

  const [showAdvanced, setShowAdvanced] = useState(false);

  const handlePresetChange = (presetId: string) => {
    const preset = AI_PROVIDER_PRESETS.find(p => p.id === presetId);
    if (preset) {
      onChange(preset.config);
    }
  };

  const handleConfigChange = (field: keyof AIProviderConfig, value: any) => {
    onChange({
      ...config,
      [field]: value
    });
  };

  const handleTestConnection = async () => {
    setConnectionStatus({ testing: true, connected: false });
    
    try {
      const result = await testAIConnection(config);
      setConnectionStatus({
        testing: false,
        connected: result.connected,
        error: result.error
      });
    } catch (error) {
      setConnectionStatus({
        testing: false,
        connected: false,
        error: error instanceof Error ? error.message : 'Error desconocido'
      });
    }
  };

  // Test connection when config changes
  useEffect(() => {
    if (config.endpoint && config.model) {
      const timeoutId = setTimeout(() => {
        handleTestConnection();
      }, 1000);
      
      return () => clearTimeout(timeoutId);
    }
  }, [config.endpoint, config.model]);

  return (
    <div className="bg-white/80 dark:bg-stone-900/80 backdrop-blur-sm rounded-xl shadow-lg p-6 border border-stone-200/60 dark:border-stone-800/60">
      <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100 mb-6">
        🤖 Configuración de IA Local
      </h3>

      <div className="space-y-6">
        {/* Preset Selection */}
        <div>
          <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-3">
            Configuración predefinida
          </label>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {AI_PROVIDER_PRESETS.map((preset) => (
              <button
                key={preset.id}
                onClick={() => handlePresetChange(preset.id)}
                className={`p-4 border rounded-lg text-left transition-all duration-200 ${
                  config.provider === preset.config.provider && 
                  config.endpoint === preset.config.endpoint &&
                  config.model === preset.config.model
                    ? 'bg-purple-50 dark:bg-purple-900/20 border-purple-500 dark:border-purple-400'
                    : 'bg-white dark:bg-stone-800 border-stone-300 dark:border-stone-600 hover:bg-stone-50 dark:hover:bg-stone-700'
                }`}
              >
                <div className="font-medium text-stone-900 dark:text-stone-100">
                  {preset.name}
                </div>
                <div className="text-sm text-stone-600 dark:text-stone-400 mb-2">
                  {preset.description}
                </div>
                {preset.requirements && (
                  <div className="text-xs text-stone-500 dark:text-stone-500">
                    Requisitos: {preset.requirements.join(', ')}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Basic Configuration */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
              Endpoint URL
            </label>
            <input
              type="url"
              value={config.endpoint}
              onChange={(e) => handleConfigChange('endpoint', e.target.value)}
              placeholder="http://localhost:11434"
              className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
              Modelo
            </label>
            <input
              type="text"
              value={config.model}
              onChange={(e) => handleConfigChange('model', e.target.value)}
              placeholder="llava:latest"
              className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
            />
          </div>
        </div>

        {/* Connection Status */}
        <div className="flex items-center justify-between p-4 rounded-lg bg-stone-50 dark:bg-stone-800">
          <div className="flex items-center space-x-3">
            <div className={`w-3 h-3 rounded-full ${
              connectionStatus.testing 
                ? 'bg-yellow-500 animate-pulse'
                : connectionStatus.connected 
                  ? 'bg-green-500' 
                  : 'bg-red-500'
            }`} />
            <span className="text-sm font-medium text-stone-900 dark:text-stone-100">
              {connectionStatus.testing 
                ? 'Probando conexión...' 
                : connectionStatus.connected 
                  ? 'Conectado' 
                  : 'Desconectado'}
            </span>
            {connectionStatus.error && (
              <span className="text-sm text-red-600 dark:text-red-400">
                ({connectionStatus.error})
              </span>
            )}
          </div>
          
          <button
            onClick={handleTestConnection}
            disabled={connectionStatus.testing}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-stone-400 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
          >
            {connectionStatus.testing ? 'Probando...' : 'Probar'}
          </button>
        </div>

        {/* Advanced Configuration */}
        <div>
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center space-x-2 text-sm text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100"
          >
            <span>{showAdvanced ? '▼' : '▶'}</span>
            <span>Configuración avanzada</span>
          </button>

          {showAdvanced && (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
                  Temperatura
                </label>
                <input
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={config.temperature || 0.1}
                  onChange={(e) => handleConfigChange('temperature', parseFloat(e.target.value))}
                  className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
                  Max Tokens
                </label>
                <input
                  type="number"
                  min="100"
                  max="8000"
                  value={config.maxTokens || 4000}
                  onChange={(e) => handleConfigChange('maxTokens', parseInt(e.target.value))}
                  className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
                  API Key (opcional)
                </label>
                <input
                  type="password"
                  value={config.apiKey || ''}
                  onChange={(e) => handleConfigChange('apiKey', e.target.value)}
                  placeholder="sk-..."
                  className="w-full p-3 border border-stone-300 dark:border-stone-600 rounded-lg bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
                />
              </div>
            </div>
          )}
        </div>

        {/* Installation Instructions */}
        {!connectionStatus.connected && (
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
            <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-2">
              📋 Instrucciones de instalación
            </h4>
            
            {config.provider === 'ollama' && (
              <div className="text-sm text-blue-800 dark:text-blue-200 space-y-2">
                <p><strong>Para Ollama:</strong></p>
                <ol className="list-decimal list-inside space-y-1 ml-4">
                  <li>Instalar Ollama: <code className="bg-blue-200 dark:bg-blue-800 px-1 rounded">curl -fsSL https://ollama.ai/install.sh | sh</code></li>
                  <li>Descargar modelo: <code className="bg-blue-200 dark:bg-blue-800 px-1 rounded">ollama pull llava:latest</code></li>
                  <li>Ejecutar: <code className="bg-blue-200 dark:bg-blue-800 px-1 rounded">ollama serve</code></li>
                </ol>
              </div>
            )}
            
            {config.provider === 'llamastudio' && (
              <div className="text-sm text-blue-800 dark:text-blue-200 space-y-2">
                <p><strong>Para LM Studio:</strong></p>
                <ol className="list-decimal list-inside space-y-1 ml-4">
                  <li>Descargar LM Studio desde su página oficial</li>
                  <li>Cargar un modelo con capacidades de visión</li>
                  <li>Iniciar el servidor local en puerto 1234</li>
                </ol>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}