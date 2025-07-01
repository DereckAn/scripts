import { App } from '@/types/script-generator';

export const APPS: App[] = [
  // Productivity Tools
  {
    id: 'raycast',
    name: 'Raycast',
    description: 'Blazingly fast, totally extendable launcher',
    icon: '🚀',
    category: 'productivity',
    macosOnly: true,
    install: {
      macos: { cask: 'raycast' }
    },
    checkInstall: 'command -v raycast'
  },
  {
    id: 'spotify',
    name: 'Spotify',
    description: 'Music streaming service',
    icon: '🎵',
    category: 'productivity',
    install: {
      macos: { cask: 'spotify' },
      ubuntu: { snap: 'spotify' },
      fedora: { command: 'flatpak install -y flathub com.spotify.Client' },
      arch: { aur: 'spotify' }
    },
    checkInstall: 'command -v spotify'
  },
  {
    id: 'amphetamine',
    name: 'Amphetamine',
    description: 'Keep your Mac awake',
    icon: '☕',
    category: 'productivity',
    macosOnly: true,
    install: {
      macos: { command: 'mas install 937984704' }
    },
    postInstall: {
      macos: ['echo "Install Amphetamine from Mac App Store manually if mas failed"']
    }
  },

  // Code Editors/IDEs
  {
    id: 'vscode',
    name: 'Visual Studio Code',
    description: 'Code editor by Microsoft',
    icon: '📝',
    category: 'code-editors',
    install: {
      macos: { cask: 'visual-studio-code' },
      ubuntu: { command: 'wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg && sudo install -o root -g root -m 644 packages.microsoft.gpg /etc/apt/trusted.gpg.d/ && sudo sh -c \'echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/trusted.gpg.d/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list\' && apt update && apt install -y code' },
      fedora: { command: 'rpm --import https://packages.microsoft.com/keys/microsoft.asc && sh -c \'echo -e "[code]\\nname=Visual Studio Code\\nbaseurl=https://packages.microsoft.com/yumrepos/vscode\\nenabled=1\\ngpgcheck=1\\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc" > /etc/yum.repos.d/vscode.repo\' && dnf check-update && dnf install -y code' },
      arch: { aur: 'visual-studio-code-bin' }
    },
    checkInstall: 'command -v code'
  },
  {
    id: 'cursor',
    name: 'Cursor',
    description: 'AI-powered code editor',
    icon: '🎯',
    category: 'code-editors',
    install: {
      macos: { cask: 'cursor' },
      ubuntu: { command: 'wget -O cursor.AppImage https://download.cursor.sh/linux/appImage/x64 && chmod +x cursor.AppImage && sudo mv cursor.AppImage /usr/local/bin/cursor' },
      fedora: { command: 'wget -O cursor.AppImage https://download.cursor.sh/linux/appImage/x64 && chmod +x cursor.AppImage && sudo mv cursor.AppImage /usr/local/bin/cursor' },
      arch: { aur: 'cursor-bin' }
    },
    checkInstall: 'command -v cursor'
  },
  {
    id: 'intellij',
    name: 'IntelliJ IDEA',
    description: 'Java IDE by JetBrains',
    icon: '🧠',
    category: 'code-editors',
    install: {
      macos: { cask: 'intellij-idea' },
      ubuntu: { snap: 'intellij-idea-community --classic' },
      fedora: { command: 'flatpak install -y flathub com.jetbrains.IntelliJ-IDEA-Community' },
      arch: { pacman: 'intellij-idea-community-edition' }
    },
    checkInstall: 'command -v idea'
  },
  {
    id: 'vim',
    name: 'Vim',
    description: 'Vi IMproved text editor',
    icon: '📄',
    category: 'code-editors',
    install: {
      macos: { homebrew: 'vim' },
      ubuntu: { apt: 'vim' },
      fedora: { dnf: 'vim' },
      arch: { pacman: 'vim' }
    },
    checkInstall: 'command -v vim'
  },
  {
    id: 'webstorm',
    name: 'WebStorm',
    description: 'JavaScript IDE by JetBrains',
    icon: '🌐',
    category: 'code-editors',
    install: {
      macos: { cask: 'webstorm' },
      ubuntu: { snap: 'webstorm --classic' },
      fedora: { command: 'flatpak install -y flathub com.jetbrains.WebStorm' },
      arch: { aur: 'webstorm' }
    },
    checkInstall: 'command -v webstorm'
  },
  {
    id: 'zed',
    name: 'Zed',
    description: 'High-performance multiplayer code editor',
    icon: '⚡',
    category: 'code-editors',
    install: {
      macos: { cask: 'zed' },
      ubuntu: { command: 'curl https://zed.dev/install.sh | sh' },
      fedora: { command: 'curl https://zed.dev/install.sh | sh' },
      arch: { aur: 'zed' }
    },
    checkInstall: 'command -v zed'
  },
  {
    id: 'vscodium',
    name: 'VSCodium',
    description: 'Open source version of VS Code',
    icon: '📝',
    category: 'code-editors',
    install: {
      macos: { cask: 'vscodium' },
      ubuntu: { command: 'wget -qO - https://gitlab.com/paulcarroty/vscodium-deb-rpm-repo/raw/master/pub.gpg | gpg --dearmor | sudo dd of=/usr/share/keyrings/vscodium-archive-keyring.gpg && echo \'deb [ signed-by=/usr/share/keyrings/vscodium-archive-keyring.gpg ] https://paulcarroty.gitlab.io/vscodium-deb-rpm-repo/debs vscodium main\' | sudo tee /etc/apt/sources.list.d/vscodium.list && sudo apt update && sudo apt install -y codium' },
      fedora: { command: 'rpm --import https://gitlab.com/paulcarroty/vscodium-deb-rpm-repo/-/raw/master/pub.gpg && printf "[gitlab.com_paulcarroty_vscodium_repo]\\nname=download.vscodium.com\\nbaseurl=https://paulcarroty.gitlab.io/vscodium-deb-rpm-repo/rpms/\\nenabled=1\\ngpgcheck=1\\nrepo_gpgcheck=1\\ngpgkey=https://gitlab.com/paulcarroty/vscodium-deb-rpm-repo/-/raw/master/pub.gpg\\nmetadata_expire=1h" | sudo tee -a /etc/yum.repos.d/vscodium.repo && sudo dnf install -y codium' },
      arch: { pacman: 'vscodium-bin' }
    },
    checkInstall: 'command -v codium'
  },

  // Terminals
  {
    id: 'warp',
    name: 'Warp',
    description: 'The terminal for the 21st century',
    icon: '🚀',
    category: 'terminals',
    macosOnly: true,
    install: {
      macos: { cask: 'warp' }
    },
    checkInstall: 'command -v warp'
  },
  {
    id: 'iterm2',
    name: 'iTerm2',
    description: 'Terminal emulator for macOS',
    icon: '💻',
    category: 'terminals',
    macosOnly: true,
    install: {
      macos: { cask: 'iterm2' }
    },
    checkInstall: 'ls /Applications | grep -i iterm'
  },

  // Browsers
  {
    id: 'chrome',
    name: 'Google Chrome',
    description: 'Web browser by Google',
    icon: '🌐',
    category: 'browsers',
    install: {
      macos: { cask: 'google-chrome' },
      ubuntu: { command: 'wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add - && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list && sudo apt update && sudo apt install -y google-chrome-stable' },
      fedora: { command: 'dnf install -y fedora-workstation-repositories && dnf config-manager --set-enabled google-chrome && dnf install -y google-chrome-stable' },
      arch: { aur: 'google-chrome' }
    },
    checkInstall: 'command -v google-chrome || command -v google-chrome-stable'
  },
  {
    id: 'brave',
    name: 'Brave',
    description: 'Privacy-focused web browser',
    icon: '🦁',
    category: 'browsers',
    install: {
      macos: { cask: 'brave-browser' },
      ubuntu: { command: 'curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg && echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg arch=amd64] https://brave-browser-apt-release.s3.brave.com/ stable main" | sudo tee /etc/apt/sources.list.d/brave-browser-release.list && sudo apt update && sudo apt install -y brave-browser' },
      fedora: { command: 'dnf install -y dnf-plugins-core && dnf config-manager --add-repo https://brave-browser-rpm-release.s3.brave.com/x86_64/ && rpm --import https://brave-browser-rpm-release.s3.brave.com/brave-core.asc && dnf install -y brave-browser' },
      arch: { pacman: 'brave-bin' }
    },
    checkInstall: 'command -v brave-browser || command -v brave'
  },
  {
    id: 'edge',
    name: 'Microsoft Edge',
    description: 'Web browser by Microsoft',
    icon: '🌊',
    category: 'browsers',
    install: {
      macos: { cask: 'microsoft-edge' },
      ubuntu: { command: 'curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > microsoft.gpg && sudo install -o root -g root -m 644 microsoft.gpg /etc/apt/trusted.gpg.d/ && sudo sh -c \'echo "deb [arch=amd64] https://packages.microsoft.com/repos/edge stable main" > /etc/apt/sources.list.d/microsoft-edge-dev.list\' && sudo apt update && sudo apt install -y microsoft-edge-stable' },
      fedora: { command: 'rpm --import https://packages.microsoft.com/keys/microsoft.asc && dnf config-manager --add-repo https://packages.microsoft.com/yumrepos/edge && dnf install -y microsoft-edge-stable' },
      arch: { aur: 'microsoft-edge-stable-bin' }
    },
    checkInstall: 'command -v microsoft-edge'
  },
  {
    id: 'firefox',
    name: 'Firefox',
    description: 'Open source web browser',
    icon: '🦊',
    category: 'browsers',
    install: {
      macos: { cask: 'firefox' },
      ubuntu: { apt: 'firefox' },
      fedora: { dnf: 'firefox' },
      arch: { pacman: 'firefox' }
    },
    checkInstall: 'command -v firefox'
  },
  {
    id: 'opera',
    name: 'Opera',
    description: 'Web browser with built-in VPN',
    icon: '🎭',
    category: 'browsers',
    install: {
      macos: { cask: 'opera' },
      ubuntu: { command: 'wget -qO- https://deb.opera.com/archive.key | sudo apt-key add - && echo "deb https://deb.opera.com/opera-stable/ stable non-free" | sudo tee /etc/apt/sources.list.d/opera-stable.list && sudo apt update && sudo apt install -y opera-stable' },
      fedora: { command: 'rpm --import https://rpm.opera.com/rpmrepo.key && dnf config-manager --add-repo https://rpm.opera.com/rpm && dnf install -y opera-stable' },
      arch: { pacman: 'opera' }
    },
    checkInstall: 'command -v opera'
  },

  // Development Tools
  {
    id: 'git',
    name: 'Git',
    description: 'Version control system',
    icon: '🌳',
    category: 'development-tools',
    install: {
      macos: { homebrew: 'git' },
      ubuntu: { apt: 'git' },
      fedora: { dnf: 'git' },
      arch: { pacman: 'git' }
    },
    checkInstall: 'command -v git'
  },
  {
    id: 'github-cli',
    name: 'GitHub CLI',
    description: 'GitHub command line interface',
    icon: '🐙',
    category: 'development-tools',
    install: {
      macos: { homebrew: 'gh' },
      ubuntu: { command: 'curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && sudo apt update && sudo apt install -y gh' },
      fedora: { dnf: 'gh' },
      arch: { pacman: 'github-cli' }
    },
    checkInstall: 'command -v gh'
  },
  {
    id: 'aws-cli',
    name: 'AWS CLI',
    description: 'Amazon Web Services command line interface',
    icon: '☁️',
    category: 'development-tools',
    install: {
      macos: { homebrew: 'awscli' },
      ubuntu: { command: 'curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && unzip awscliv2.zip && sudo ./aws/install && rm -rf aws awscliv2.zip' },
      fedora: { command: 'curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && unzip awscliv2.zip && sudo ./aws/install && rm -rf aws awscliv2.zip' },
      arch: { pacman: 'aws-cli' }
    },
    checkInstall: 'command -v aws'
  },
  {
    id: 'docker',
    name: 'Docker Desktop',
    description: 'Containerization platform',
    icon: '🐳',
    category: 'development-tools',
    install: {
      macos: { cask: 'docker' },
      ubuntu: { command: 'curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null && sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin' },
      fedora: { dnf: 'docker docker-compose' },
      arch: { pacman: 'docker docker-compose' }
    },
    postInstall: {
      ubuntu: ['sudo systemctl enable docker', 'sudo systemctl start docker', 'sudo usermod -aG docker $USER'],
      fedora: ['sudo systemctl enable docker', 'sudo systemctl start docker', 'sudo usermod -aG docker $USER'],
      arch: ['sudo systemctl enable docker', 'sudo systemctl start docker', 'sudo usermod -aG docker $USER']
    },
    checkInstall: 'command -v docker'
  },
  {
    id: 'llm-studio',
    name: 'LLM Studio',
    description: 'Local LLM management',
    icon: '🤖',
    category: 'development-tools',
    install: {
      macos: { cask: 'lm-studio' },
      ubuntu: { command: 'wget -O lmstudio.AppImage https://releases.lmstudio.ai/linux/x86/0.2.19/LM_Studio-0.2.19.AppImage && chmod +x lmstudio.AppImage && sudo mv lmstudio.AppImage /usr/local/bin/lmstudio' },
      fedora: { command: 'wget -O lmstudio.AppImage https://releases.lmstudio.ai/linux/x86/0.2.19/LM_Studio-0.2.19.AppImage && chmod +x lmstudio.AppImage && sudo mv lmstudio.AppImage /usr/local/bin/lmstudio' },
      arch: { aur: 'lm-studio-bin' }
    },
    checkInstall: 'command -v lmstudio'
  },

  // Programming Languages
  {
    id: 'python',
    name: 'Python',
    description: 'Python programming language',
    icon: '🐍',
    category: 'programming-languages',
    install: {
      macos: { homebrew: 'python' },
      ubuntu: { apt: 'python3 python3-pip' },
      fedora: { dnf: 'python3 python3-pip' },
      arch: { pacman: 'python python-pip' }
    },
    postInstall: {
      macos: ['pip3 install --upgrade pip'],
      ubuntu: ['pip3 install --upgrade pip'],
      fedora: ['pip3 install --upgrade pip'],
      arch: ['pip install --upgrade pip']
    },
    checkInstall: 'command -v python3 || command -v python'
  },
  {
    id: 'java',
    name: 'Java',
    description: 'Java Development Kit',
    icon: '☕',
    category: 'programming-languages',
    install: {
      macos: { homebrew: 'openjdk' },
      ubuntu: { apt: 'openjdk-11-jdk' },
      fedora: { dnf: 'java-11-openjdk-devel' },
      arch: { pacman: 'jdk-openjdk' }
    },
    checkInstall: 'command -v java'
  },
  {
    id: 'rust',
    name: 'Rust',
    description: 'Rust programming language',
    icon: '🦀',
    category: 'programming-languages',
    install: {
      macos: { command: 'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y' },
      ubuntu: { command: 'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y' },
      fedora: { command: 'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y' },
      arch: { command: 'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y' }
    },
    postInstall: {
      macos: ['source ~/.cargo/env'],
      ubuntu: ['source ~/.cargo/env'],
      fedora: ['source ~/.cargo/env'],
      arch: ['source ~/.cargo/env']
    },
    checkInstall: 'command -v rustc'
  },
  {
    id: 'nodejs',
    name: 'Node.js',
    description: 'JavaScript runtime',
    icon: '📗',
    category: 'programming-languages',
    install: {
      macos: { homebrew: 'node' },
      ubuntu: { command: 'curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt-get install -y nodejs' },
      fedora: { dnf: 'nodejs npm' },
      arch: { pacman: 'nodejs npm' }
    },
    checkInstall: 'command -v node'
  },
  {
    id: 'ruby',
    name: 'Ruby',
    description: 'Ruby programming language',
    icon: '💎',
    category: 'programming-languages',
    install: {
      macos: { homebrew: 'ruby' },
      ubuntu: { apt: 'ruby-full' },
      fedora: { dnf: 'ruby' },
      arch: { pacman: 'ruby' }
    },
    checkInstall: 'command -v ruby'
  },
  {
    id: 'go',
    name: 'Go',
    description: 'Go programming language',
    icon: '🐹',
    category: 'programming-languages',
    install: {
      macos: { homebrew: 'go' },
      ubuntu: { apt: 'golang-go' },
      fedora: { dnf: 'golang' },
      arch: { pacman: 'go' }
    },
    checkInstall: 'command -v go'
  },
  {
    id: 'csharp',
    name: 'C#/.NET',
    description: '.NET development platform',
    icon: '🔷',
    category: 'programming-languages',
    install: {
      macos: { homebrew: 'dotnet' },
      ubuntu: { command: 'wget https://packages.microsoft.com/config/ubuntu/20.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb && sudo dpkg -i packages-microsoft-prod.deb && rm packages-microsoft-prod.deb && sudo apt-get update && sudo apt-get install -y dotnet-sdk-6.0' },
      fedora: { dnf: 'dotnet-sdk-6.0' },
      arch: { pacman: 'dotnet-sdk' }
    },
    checkInstall: 'command -v dotnet'
  },
  {
    id: 'cpp',
    name: 'C++',
    description: 'C++ compiler and tools',
    icon: '⚙️',
    category: 'programming-languages',
    install: {
      macos: { command: 'xcode-select --install' },
      ubuntu: { apt: 'build-essential' },
      fedora: { dnf: 'gcc-c++ make' },
      arch: { pacman: 'base-devel' }
    },
    checkInstall: 'command -v g++'
  },
  {
    id: 'php',
    name: 'PHP',
    description: 'PHP programming language',
    icon: '🐘',
    category: 'programming-languages',
    install: {
      macos: { homebrew: 'php' },
      ubuntu: { apt: 'php php-cli php-mbstring php-xml' },
      fedora: { dnf: 'php php-cli' },
      arch: { pacman: 'php' }
    },
    checkInstall: 'command -v php'
  },

  // Frameworks
  {
    id: 'laravel',
    name: 'Laravel',
    description: 'PHP web framework',
    icon: '🏗️',
    category: 'frameworks',
    install: {
      macos: { command: 'composer global require laravel/installer' },
      ubuntu: { command: 'composer global require laravel/installer' },
      fedora: { command: 'composer global require laravel/installer' },
      arch: { command: 'composer global require laravel/installer' }
    },
    postInstall: {
      macos: ['echo "export PATH=\\"$PATH:$HOME/.composer/vendor/bin\\"" >> ~/.zshrc'],
      ubuntu: ['echo "export PATH=\\"$PATH:$HOME/.composer/vendor/bin\\"" >> ~/.bashrc'],
      fedora: ['echo "export PATH=\\"$PATH:$HOME/.composer/vendor/bin\\"" >> ~/.bashrc'],
      arch: ['echo "export PATH=\\"$PATH:$HOME/.composer/vendor/bin\\"" >> ~/.bashrc']
    },
    checkInstall: 'command -v laravel'
  },
  {
    id: 'kubernetes',
    name: 'Kubernetes',
    description: 'Container orchestration',
    icon: '⚓',
    category: 'frameworks',
    install: {
      macos: { homebrew: 'kubectl' },
      ubuntu: { command: 'curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && rm kubectl' },
      fedora: { command: 'curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && rm kubectl' },
      arch: { pacman: 'kubectl' }
    },
    checkInstall: 'command -v kubectl'
  }
];