export interface Platform {
  windows?: {
    winget?: string;
    choco?: string;
  };
  macos?: {
    brew: string;
    cask?: boolean;
  };
  linux?: {
    ubuntu?: string;
    fedora?: string;
    arch?: string;
    opensuse?: string;
    snap?: string;
    aur?: boolean;
  };
}

export interface Application {
  name: string;
  description: string;
  category: string;
  platforms: Platform;
}

export interface Distribution {
  name: string;
  packageManager: string;
  updateCommand: string;
}

export interface Category {
  name: string;
  icon: string;
}

export interface ScriptConfig {
  platform: 'windows' | 'macos' | 'linux';
  distribution?: string;
  selectedApps: string[];
}

export interface FormState {
  step: number;
  platform: 'windows' | 'macos' | 'linux' | '';
  distribution: string;
  selectedApps: string[];
  generatedScript: string;
}

export interface StepProps {
  formState: FormState;
  onUpdate: (updates: Partial<FormState>) => void;
  onNext: () => void;
  onPrevious: () => void;
}
