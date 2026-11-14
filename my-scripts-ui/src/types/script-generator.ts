export type OperatingSystem = 'macos' | 'ubuntu' | 'fedora' | 'arch';

export interface App {
  id: string;
  name: string;
  description: string;
  category: string;
  macosOnly?: boolean;
  linuxOnly?: boolean;
  install: {
    macos?: {
      homebrew?: string;
      cask?: string;
      command?: string;
    };
    ubuntu?: {
      apt?: string;
      snap?: string;
      command?: string;
    };
    fedora?: {
      dnf?: string;
      command?: string;
    };
    arch?: {
      pacman?: string;
      aur?: string;
      command?: string;
    };
  };
  postInstall?: {
    macos?: string[];
    ubuntu?: string[];
    fedora?: string[];
    arch?: string[];
  };
  checkInstall?: string;
}

export interface ScriptOptions {
  updateSystem: boolean;
  createBackup: boolean;
  showProgress: boolean;
  configureDotfiles: boolean;
  installOhMyZsh: boolean;
}

export interface ScriptConfig {
  os: OperatingSystem;
  selectedApps: string[];
  options: ScriptOptions;
}
