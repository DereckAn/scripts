export interface ImageAnalysisResult {
  id: string;
  filename: string;
  fileSize: number;
  dimensions: {
    width: number;
    height: number;
  };
  analysis: string;
  timestamp: string;
  processingTime?: number;
  error?: string;
  status: 'pending' | 'analyzing' | 'completed' | 'error';
}

export interface ImageFile {
  id: string;
  file: File;
  preview: string;
  filename: string;
  fileSize: number;
}

export interface AnalysisProgress {
  current: number;
  total: number;
  percentage: number;
  currentFile: string;
  status: 'preparing' | 'analyzing' | 'completed' | 'error';
}

export interface AIProviderConfig {
  provider: 'ollama' | 'llamastudio' | 'custom';
  endpoint: string;
  model: string;
  apiKey?: string;
  temperature?: number;
  maxTokens?: number;
}

export interface AIProviderPreset {
  id: string;
  name: string;
  description: string;
  config: AIProviderConfig;
  isLocal: boolean;
  requirements?: string[];
}

export const DEFAULT_ANALYSIS_PROMPT = `bla bla bla`;

export const AI_PROVIDER_PRESETS: AIProviderPreset[] = [
  {
    id: 'ollama-llava',
    name: 'Ollama + LLaVA',
    description: 'Local AI with LLaVA vision model (uncensored)',
    config: {
      provider: 'ollama',
      endpoint: 'http://localhost:11434',
      model: 'llava:latest',
      temperature: 0.1,
      maxTokens: 4000
    },
    isLocal: true,
    requirements: ['Ollama installed', 'LLaVA model downloaded']
  },
  {
    id: 'ollama-llava-phi3',
    name: 'Ollama + LLaVA Phi3',
    description: 'Faster local model with good vision capabilities',
    config: {
      provider: 'ollama',
      endpoint: 'http://localhost:11434',
      model: 'llava-phi3:latest',
      temperature: 0.1,
      maxTokens: 4000
    },
    isLocal: true,
    requirements: ['Ollama installed', 'LLaVA Phi3 model downloaded']
  },
  {
    id: 'llamastudio',
    name: 'LM Studio',
    description: 'Local LM Studio with vision model',
    config: {
      provider: 'llamastudio',
      endpoint: 'http://localhost:1234',
      model: 'local-model',
      temperature: 0.1,
      maxTokens: 4000
    },
    isLocal: true,
    requirements: ['LM Studio running', 'Vision model loaded']
  },
  {
    id: 'custom',
    name: 'Custom Endpoint',
    description: 'Custom API endpoint configuration',
    config: {
      provider: 'custom',
      endpoint: 'http://localhost:8000',
      model: 'custom-model',
      temperature: 0.1,
      maxTokens: 4000
    },
    isLocal: true,
    requirements: ['Custom API server running']
  }
];