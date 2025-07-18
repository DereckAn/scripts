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

export const DEFAULT_ANALYSIS_PROMPT = `Please analyze the provided image of one or more female models (or a close-up of footwear if no model is present) and generate an ultra-detailed description as if conducted by a medical professional and a professional shoe designer with expertise in stripper footwear. For each individual present in the image, focus on the following aspects with precision:

Bust Size: Estimate the bra size (e.g., 34C, 38DD) based on visible proportions, cup volume, and firmness, considering underbust and overbust measurements. Note if the breasts appear natural, surgically enhanced, firm, sagging, or asymmetrical, and describe their overall shape.

Nipples (if visible): Detail size (e.g., small, large), color (e.g., light pink, dark brown), thickness, projection (e.g., flat, protruding), and any visible texture or pigmentation, analyzing as a medical expert.

Hip/Glute Size: Estimate hip circumference (e.g., 40-42 inches) and describe gluteal shape (e.g., round, high, full), projection, and firmness. Note if they appear natural, surgically enhanced, or asymmetrical.

Vagina (if visible): Describe visible external features (e.g., labia majora/minora size, color, symmetry) with clinical precision, avoiding speculation beyond observable details.

Skin Tone: Describe the exact shade (e.g., light olive, medium brown with golden undertones) and any variations (e.g., tan lines, freckles, scars).

Feet: Detail visibility, arch (e.g., high, flat), size relative to body, condition (e.g., pedicured, calluses), and any impact from footwear.

Posture: Analyze spinal alignment, shoulder position, and overall stance (e.g., erect, relaxed, leaning), considering the influence of high heels if worn.

Facial Expression: Note the emotion (e.g., neutral, smiling) and any muscle tension or relaxation in the face.

Hair: Describe length, texture (e.g., wavy, curly), color, style (e.g., loose, updo), and health (e.g., shiny, split ends).

Nails: Detail length, shape (e.g., almond, square), color, and manicure condition.

Pose: Describe body orientation (e.g., frontal, side profile), limb positioning, and dynamic elements (e.g., hand on hip).

Heels (if worn): As a professional shoe designer with stripper footwear expertise, analyze with extreme detail:
Height: Measure the heel height (e.g., 9 inches/230mm) and platform height (e.g., 5 1/4 inches/135mm) with precision, emphasizing super-high designs.
Style: Identify type (e.g., stiletto, platform, block) and design (e.g., criss-cross straps, closed back, open toe).
Color and Material: Note color (e.g., black vegan leather) and material quality (e.g., glossy finish, durable synthetic).
Construction: Describe closure (e.g., back zip), strap arrangement, and structural support (e.g., reinforced sole).
Aesthetic: Evaluate boldness, elegance, and suitability for performance (e.g., stripper/stage use).

If no heels are present, note the absence and describe barefoot condition.

Clothing: Describe fabric, color, pattern, fit (e.g., tight, loose), and design details (e.g., cutouts, straps), or confirm if the model is nude, including any accessories.

Ensure the description is exhaustive for each individual in the image, covering all visible anatomical, stylistic, and footwear features. Use precise language to aid in training an AI to generate highly accurate and realistic female models, with a special focus on super-high heels and detailed anatomical accuracy, including nudity if applicable.`;

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