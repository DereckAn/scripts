#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[1;36m'
BLUE='\033[1;34m'
NC='\033[0m'

# --- Detectar distro y package manager ---

detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO=$ID
    else
        echo "${RED}No se pudo detectar la distribución. Saliendo...${NC}"
        exit 1
    fi

    case "$DISTRO" in
        ubuntu|debian|linuxmint|pop)
            PKG_MANAGER="apt"
            PKG_INSTALL="sudo apt install -y"
            PKG_UPDATE="sudo apt update -y"
            PKG_CHECK="dpkg -l"
            ;;
        fedora|rhel|centos|rocky|almalinux)
            PKG_MANAGER="dnf"
            PKG_INSTALL="sudo dnf install -y"
            PKG_UPDATE="sudo dnf check-update -y"
            PKG_CHECK="rpm -q"
            ;;
        arch|manjaro|endeavouros|garuda)
            PKG_MANAGER="pacman"
            PKG_INSTALL="sudo pacman -S --noconfirm"
            PKG_UPDATE="sudo pacman -Sy"
            PKG_CHECK="pacman -Q"
            ;;
        *)
            echo "${RED}Distribución '$DISTRO' no soportada. Saliendo...${NC}"
            exit 1
            ;;
    esac

    echo "${GREEN}Distribución detectada: $DISTRO (usando $PKG_MANAGER)${NC}"
}

# --- Helpers ---

run_command() {
    local cmd="$1"
    local desc="$2"
    echo -n "${YELLOW}${desc}...${NC} "
    if eval "$cmd" >/dev/null 2>&1; then
        echo "${GREEN}Hecho${NC}"
        return 0
    else
        echo "${RED}Error${NC}"
        return 1
    fi
}

is_app_installed() {
    local package_name="$1"
    case "$PKG_MANAGER" in
        apt)    dpkg -l "$package_name" 2>/dev/null | grep -q "^ii" ;;
        dnf)    rpm -q "$package_name" >/dev/null 2>&1 ;;
        pacman) pacman -Q "$package_name" >/dev/null 2>&1 ;;
    esac
}

is_snap_installed() {
    command -v snap >/dev/null 2>&1 && snap list "$1" >/dev/null 2>&1
}

is_flatpak_installed() {
    command -v flatpak >/dev/null 2>&1 && flatpak list | grep -qi "$1"
}

add_to_path() {
    local app_name="$1"
    local path_to_add="$2"
    local executable="$3"

    [ -z "$path_to_add" ] || [ -z "$executable" ] && return

    if command -v "$executable" >/dev/null 2>&1; then
        echo "${GREEN}${executable} ya está en el PATH.${NC}"
        return
    fi

    local zshrc="$HOME/.zshrc"
    local export_line="export PATH=\"${path_to_add}:\$PATH\""
    if grep -q "$export_line" "$zshrc" 2>/dev/null; then
        echo "${GREEN}Ruta ${path_to_add} ya está en ~/.zshrc.${NC}"
        return
    fi

    echo "${YELLOW}Añadiendo ${path_to_add} al PATH en ~/.zshrc...${NC}"
    echo "# Añadido por setup_linux.sh" >> "$zshrc"
    echo "$export_line" >> "$zshrc"
    echo "${GREEN}Ruta para ${app_name} añadida al PATH.${NC}"
}

write_to_zshrc() {
    local description="$1"
    local line="$2"
    local zshrc="$HOME/.zshrc"

    if grep -qF "$line" "$zshrc" 2>/dev/null; then
        echo "${GREEN}${description} ya está en ~/.zshrc.${NC}"
        return
    fi

    echo "${YELLOW}Añadiendo ${description} a ~/.zshrc...${NC}"
    echo "# Añadido por setup_linux.sh - ${description}" >> "$zshrc"
    echo "$line" >> "$zshrc"
    echo "${GREEN}${description} añadido a ~/.zshrc.${NC}"
}

# --- Verificar dependencias base ---

check_dependencies() {
    echo "${YELLOW}Actualizando lista de paquetes...${NC}"
    eval "$PKG_UPDATE" >/dev/null 2>&1

    for dep in curl git zsh; do
        if ! command -v "$dep" >/dev/null 2>&1; then
            echo "${YELLOW}${dep} no encontrado. Instalando...${NC}"
            run_command "$PKG_INSTALL $dep" "Instalando $dep" || {
                echo "${RED}Error instalando $dep. Saliendo...${NC}"
                exit 1
            }
        else
            echo "${GREEN}${dep} encontrado.${NC}"
        fi
    done
}

# --- Oh My Zsh ---

install_oh_my_zsh() {
    echo "${YELLOW}Configurando Oh My Zsh...${NC}"
    if [ -d "$HOME/.oh-my-zsh" ]; then
        echo "${GREEN}Oh My Zsh ya instalado.${NC}"
    else
        run_command 'sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" --unattended' "Instalando Oh My Zsh" || {
            echo "${RED}Error instalando Oh My Zsh. Saliendo...${NC}"
            exit 1
        }
    fi

    run_command "git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k" "Instalando Powerlevel10k"
    sed -i 's/ZSH_THEME="robbyrussell"/ZSH_THEME="powerlevel10k\/powerlevel10k"/' ~/.zshrc

    run_command "git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autosuggestions" "Instalando zsh-autosuggestions"
    run_command "git clone https://github.com/zsh-users/zsh-history-substring-search ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-history-substring-search" "Instalando zsh-history-substring-search"
    run_command "git clone https://github.com/zsh-users/zsh-syntax-highlighting ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting" "Instalando zsh-syntax-highlighting"
    sed -i 's/plugins=(git)/plugins=(git jump zsh-autosuggestions zsh-history-substring-search jsontools zsh-syntax-highlighting zsh-interactive-cd)/' ~/.zshrc

    echo "${YELLOW}Cambiando shell por defecto a Zsh...${NC}"
    run_command "chsh -s $(which zsh)" "Cambiando shell a Zsh"
}

# --- Git ---

configure_git_global() {
    echo "${YELLOW}¿Configurar credenciales globales de Git? [Y/n]: ${NC}"
    read -r configure_git
    if [[ "$configure_git" != "n" && "$configure_git" != "N" ]]; then
        current_user=$(git config --global user.name)
        current_email=$(git config --global user.email)
        if [ -n "$current_user" ] && [ -n "$current_email" ]; then
            echo "${GREEN}Credenciales ya configuradas: $current_user <$current_email>${NC}"
            echo "${YELLOW}¿Sobrescribir? [y/N]: ${NC}"
            read -r overwrite
            [[ "$overwrite" != "y" && "$overwrite" != "Y" ]] && return
        fi
        echo -n "Ingresa tu nombre para Git (e.g., Juan Pérez): "
        read -r git_name
        echo -n "Ingresa tu correo para Git (e.g., juan@example.com): "
        read -r git_email
        if [ -n "$git_name" ] && [ -n "$git_email" ]; then
            run_command "git config --global user.name \"$git_name\"" "Configurando nombre de Git"
            run_command "git config --global user.email \"$git_email\"" "Configurando correo de Git"
            echo "${GREEN}Credenciales configuradas: $git_name <$git_email>${NC}"
        else
            echo "${YELLOW}No se proporcionaron credenciales válidas. Saltando...${NC}"
        fi
    else
        echo "${YELLOW}Saltando configuración de Git.${NC}"
    fi
}

# --- SSH ---

configure_ssh_key() {
    echo "${YELLOW}¿Configurar clave SSH para GitHub? [Y/n]: ${NC}"
    read -r configure_ssh
    if [[ "$configure_ssh" != "n" && "$configure_ssh" != "N" ]]; then
        local ssh_key_path="$HOME/.ssh/id_ed25519"
        if [ -f "$ssh_key_path" ]; then
            echo "${GREEN}Clave SSH ya existe en ~/.ssh/id_ed25519.${NC}"
            echo "${YELLOW}¿Generar nueva clave (sobrescribirá la existente)? [y/N]: ${NC}"
            read -r overwrite
            if [[ "$overwrite" != "y" && "$overwrite" != "Y" ]]; then
                add_ssh_key_to_github
                return
            fi
        fi

        if ! command -v gh >/dev/null 2>&1; then
            echo "${YELLOW}GitHub CLI no encontrado. Instalando...${NC}"
            install_github_cli
        fi

        echo -n "Ingresa tu correo para SSH (e.g., juan@example.com): "
        read -r ssh_email
        if [ -n "$ssh_email" ]; then
            run_command "ssh-keygen -t ed25519 -C \"$ssh_email\" -f \"$ssh_key_path\" -N \"\"" "Generando clave SSH" || return
            run_command "eval \$(ssh-agent -s)" "Iniciando ssh-agent"
            run_command "ssh-add $ssh_key_path" "Añadiendo clave SSH al agente"

            mkdir -p "$HOME/.ssh"
            local ssh_config_path="$HOME/.ssh/config"
            if ! grep -q "Host github.com" "$ssh_config_path" 2>/dev/null; then
                cat >> "$ssh_config_path" << 'EOF'
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
EOF
            fi
            run_command "chmod 600 $ssh_config_path" "Configurando permisos de ~/.ssh/config"
            add_ssh_key_to_github
        else
            echo "${YELLOW}No se proporcionó correo válido. Saltando...${NC}"
        fi
    else
        echo "${YELLOW}Saltando configuración de clave SSH.${NC}"
    fi
}

install_github_cli() {
    case "$PKG_MANAGER" in
        apt)
            run_command "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null && sudo apt update && sudo apt install gh -y" "Instalando GitHub CLI"
            ;;
        dnf)
            run_command "sudo dnf install -y gh" "Instalando GitHub CLI"
            ;;
        pacman)
            run_command "sudo pacman -S --noconfirm github-cli" "Instalando GitHub CLI"
            ;;
    esac
}

add_ssh_key_to_github() {
    local public_key_path="$HOME/.ssh/id_ed25519.pub"
    [ ! -f "$public_key_path" ] && echo "${RED}No se encontró la clave pública SSH.${NC}" && return

    if command -v gh >/dev/null 2>&1; then
        if ! gh auth status >/dev/null 2>&1; then
            run_command "gh auth login" "Autenticando en GitHub CLI" || { show_ssh_key_instructions; return; }
        fi
        run_command "gh ssh-key add \"$public_key_path\" --title \"Linux_$(date +%Y%m%d)\" --type authentication" "Añadiendo clave SSH a GitHub" || { show_ssh_key_instructions; return; }
        echo "${GREEN}Clave SSH añadida a GitHub.${NC}"
        ssh -T git@github.com 2>&1 | grep -q "successfully authenticated" && \
            echo "${GREEN}Conexión SSH verificada.${NC}" || \
            echo "${YELLOW}No se pudo verificar la conexión. Verifica la clave en GitHub.${NC}"
    else
        show_ssh_key_instructions
    fi
}

show_ssh_key_instructions() {
    local public_key_path="$HOME/.ssh/id_ed25519.pub"
    if [ -f "$public_key_path" ]; then
        echo "${CYAN}Clave pública SSH:${NC}"
        cat "$public_key_path"
        echo
        echo "${CYAN}Instrucciones:${NC}"
        echo "1. Copia la clave pública arriba."
        echo "2. Ve a https://github.com/settings/keys"
        echo "3. Haz clic en 'New SSH key'."
        echo "4. Pega la clave y dale un título (e.g., 'Linux')."
        echo "5. Haz clic en 'Add SSH key'."
    fi
}

# --- Instalación de apps por distro ---

# Devuelve el comando de instalación correcto para la distro actual
pkg_cmd() {
    local apt_cmd="$1"
    local dnf_cmd="$2"
    local pacman_cmd="$3"
    case "$PKG_MANAGER" in
        apt)    echo "$apt_cmd" ;;
        dnf)    echo "$dnf_cmd" ;;
        pacman) echo "$pacman_cmd" ;;
    esac
}

post_install_config() {
    local name="$1"
    case "$name" in
        eza)
            write_to_zshrc "eza alias ls" 'alias ls="eza --color=auto --icons"'
            write_to_zshrc "eza alias ll" 'alias ll="eza -lh --icons --git"'
            write_to_zshrc "eza alias la" 'alias la="eza -lah --icons --git"'
            write_to_zshrc "eza alias lt" 'alias lt="eza --tree --icons"'
            echo "${CYAN}Nota: configura tu terminal para usar una Nerd Font para ver los iconos.${NC}"
            ;;
        zoxide)
            write_to_zshrc "zoxide init" 'eval "$(zoxide init zsh)"'
            ;;
        docker)
            echo "${CYAN}Nota: añadiendo usuario al grupo docker para usar sin sudo...${NC}"
            run_command "sudo usermod -aG docker $USER" "Añadiendo $USER al grupo docker"
            echo "${YELLOW}Cierra sesión y vuelve a entrar para aplicar el grupo docker.${NC}"
            ;;
    esac
}

select_apps() {
    echo "${CYAN}Selecciona las aplicaciones a instalar por categoría:${NC}"
    local selected_apps=()

    # Formato: "Nombre:comando_apt:comando_dnf:comando_pacman:path:executable"
    declare -A categories=(
        ["Gestores de Paquetes"]="pnpm:npm install -g pnpm:npm install -g pnpm:npm install -g pnpm:: Bun:curl -fsSL https://bun.sh/install | bash:curl -fsSL https://bun.sh/install | bash:curl -fsSL https://bun.sh/install | bash:: Yarn:npm install -g yarn:npm install -g yarn:npm install -g yarn:: Node.js:sudo apt install -y nodejs:sudo dnf install -y nodejs:sudo pacman -S --noconfirm nodejs::"

        ["Herramientas de Contenedores"]="Docker:sudo apt install -y docker.io:sudo dnf install -y docker:sudo pacman -S --noconfirm docker:: kubectl:sudo apt install -y kubectl:sudo dnf install -y kubectl:sudo pacman -S --noconfirm kubectl:: Minikube:curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64 && sudo install minikube-linux-amd64 /usr/local/bin/minikube:curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64 && sudo install minikube-linux-amd64 /usr/local/bin/minikube:sudo pacman -S --noconfirm minikube::"

        ["IDEs y Editores"]="Visual Studio Code:sudo snap install code --classic:sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc && sudo sh -c 'echo -e \"[code]\nname=Visual Studio Code\nbaseurl=https://packages.microsoft.com/yumrepos/vscode\nenabled=1\ngpgcheck=1\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc\" > /etc/yum.repos.d/vscode.repo' && sudo dnf install -y code:sudo pacman -S --noconfirm code:: Cursor:sudo snap install cursor --classic:sudo snap install cursor --classic:sudo snap install cursor --classic:: IntelliJ IDEA:sudo snap install intellij-idea-community --classic:sudo snap install intellij-idea-community --classic:sudo snap install intellij-idea-community --classic:: WebStorm:sudo snap install webstorm --classic:sudo snap install webstorm --classic:sudo snap install webstorm --classic::"

        ["Navegadores"]="Google Chrome:wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && sudo apt install -y /tmp/chrome.deb:sudo dnf install -y https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm:sudo pacman -S --noconfirm google-chrome:: Brave:sudo apt install -y brave-browser:sudo dnf install -y brave-browser:sudo pacman -S --noconfirm brave-bin:: Firefox:sudo apt install -y firefox:sudo dnf install -y firefox:sudo pacman -S --noconfirm firefox::"

        ["Lenguajes de Programación"]="Python:sudo apt install -y python3:sudo dnf install -y python3:sudo pacman -S --noconfirm python:/usr/bin:python3 Java:sudo apt install -y default-jdk:sudo dnf install -y java-latest-openjdk:sudo pacman -S --noconfirm jdk-openjdk:/usr/bin:java Rust:curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y:curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y:curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y:$HOME/.cargo/bin:rustc Go:sudo apt install -y golang:sudo dnf install -y golang:sudo pacman -S --noconfirm go:/usr/local/go/bin:go Ruby:sudo apt install -y ruby:sudo dnf install -y ruby:sudo pacman -S --noconfirm ruby:/usr/bin:ruby PHP:sudo apt install -y php:sudo dnf install -y php:sudo pacman -S --noconfirm php:/usr/bin:php"

        ["Bases de Datos"]="PostgreSQL:sudo apt install -y postgresql:sudo dnf install -y postgresql-server:sudo pacman -S --noconfirm postgresql:: MySQL:sudo apt install -y mysql-server:sudo dnf install -y mysql-server:sudo pacman -S --noconfirm mysql:: MongoDB:sudo apt install -y mongodb:sudo dnf install -y mongodb-org:sudo pacman -S --noconfirm mongodb::"

        ["Herramientas CLI"]="eza:sudo apt install -y eza:sudo dnf install -y eza:sudo pacman -S --noconfirm eza:: zoxide:sudo apt install -y zoxide:sudo dnf install -y zoxide:sudo pacman -S --noconfirm zoxide:: btop:sudo apt install -y btop:sudo dnf install -y btop:sudo pacman -S --noconfirm btop:: ranger:sudo apt install -y ranger:sudo dnf install -y ranger:sudo pacman -S --noconfirm ranger:: fzf:sudo apt install -y fzf:sudo dnf install -y fzf:sudo pacman -S --noconfirm fzf:: GitHub CLI (gh):sudo apt install -y gh:sudo dnf install -y gh:sudo pacman -S --noconfirm github-cli::"

        ["Otros"]="Telegram:sudo apt install -y telegram-desktop:sudo dnf install -y telegram-desktop:sudo pacman -S --noconfirm telegram-desktop:: Slack:sudo snap install slack:sudo snap install slack:sudo snap install slack:: Tailscale:curl -fsSL https://tailscale.com/install.sh | sh:curl -fsSL https://tailscale.com/install.sh | sh:curl -fsSL https://tailscale.com/install.sh | sh:: Obsidian:sudo snap install obsidian --classic:sudo snap install obsidian --classic:sudo snap install obsidian --classic:: Notion:sudo snap install notion-snap:sudo snap install notion-snap:sudo snap install notion-snap::"
    )

    for category in "${!categories[@]}"; do
        echo
        echo "${BLUE}Categoría: $category${NC}"
        echo "${CYAN}ID   Aplicación${NC}"

        IFS=' ' read -ra apps <<< "${categories[$category]}"
        local app_list=()
        local i=1
        for app in "${apps[@]}"; do
            IFS=':' read -r name apt_cmd dnf_cmd pacman_cmd path executable <<< "$app"
            local install_cmd
            case "$PKG_MANAGER" in
                apt)    install_cmd="$apt_cmd" ;;
                dnf)    install_cmd="$dnf_cmd" ;;
                pacman) install_cmd="$pacman_cmd" ;;
            esac
            local package_name
            package_name=$(echo "$install_cmd" | awk '{print $NF}')
            if is_app_installed "$package_name"; then
                echo "${GREEN}[$i]  $name (instalado)${NC}"
            else
                echo "${CYAN}[$i]  $name${NC}"
            fi
            app_list[$i]="$name:$install_cmd:$path:$executable"
            ((i++))
        done

        echo -n "${YELLOW}Ingresa los números (ej. 1,3,5), 'all', '0' o 'n' para omitir: ${NC}"
        read -r choices
        choices=$(echo "$choices" | tr '[:upper:]' '[:lower:]')
        if [ "$choices" = "all" ]; then
            for ((j=1; j<i; j++)); do
                selected_apps+=("${app_list[$j]}")
            done
        elif [[ "$choices" = "0" || "$choices" = "n" || -z "$choices" ]]; then
            echo "${YELLOW}Omitiendo categoría $category.${NC}"
        else
            IFS=',' read -ra indices <<< "$choices"
            for idx in "${indices[@]}"; do
                if [[ "$idx" =~ ^[0-9]+$ && "$idx" -ge 1 && "$idx" -lt "$i" ]]; then
                    selected_apps+=("${app_list[$idx]}")
                fi
            done
        fi
    done

    printf '%s\n' "${selected_apps[@]}"
}

install_apps() {
    local apps=("$@")
    [ ${#apps[@]} -eq 0 ] && echo "${YELLOW}No se seleccionaron aplicaciones.${NC}" && return

    echo "${CYAN}Aplicaciones a instalar:${NC}"
    for app in "${apps[@]}"; do
        IFS=':' read -r name _ _ _ _ <<< "$app"
        echo "  - $name"
    done

    for app in "${apps[@]}"; do
        IFS=':' read -r name cmd path executable <<< "$app"
        local package_name
        package_name=$(echo "$cmd" | awk '{print $NF}')
        if is_app_installed "$package_name"; then
            echo "${GREEN}${name} ya está instalado.${NC}"
            add_to_path "$name" "$path" "$executable"
            post_install_config "$name"
            continue
        fi
        echo "${YELLOW}Instalando ${name}...${NC}"
        run_command "$cmd" "Instalando ${name}" || echo "${RED}Error instalando ${name}.${NC}"
        add_to_path "$name" "$path" "$executable"
        post_install_config "$name"
    done
}

# --- Desinstalar ---

uninstall() {
    echo "${CYAN}Modo de desinstalación${NC}"
    echo

    echo "${YELLOW}¿Desinstalar Oh My Zsh, Powerlevel10k y plugins? [Y/n]: ${NC}"
    read -r remove_omz
    if [[ "$remove_omz" != "n" && "$remove_omz" != "N" ]]; then
        if [ -d "$HOME/.oh-my-zsh" ]; then
            run_command "rm -rf $HOME/.oh-my-zsh" "Eliminando Oh My Zsh"
            echo "${GREEN}Oh My Zsh eliminado.${NC}"
        else
            echo "${YELLOW}Oh My Zsh no está instalado.${NC}"
        fi
        run_command "rm -f $HOME/.p10k.zsh" "Eliminando configuración de Powerlevel10k"

        # Limpiar ~/.zshrc
        local zshrc="$HOME/.zshrc"
        if [ -f "$zshrc" ]; then
            sed -i '/# Añadido por setup_linux\.sh/{ N; d; }' "$zshrc"
            sed -i 's/ZSH_THEME="powerlevel10k\/powerlevel10k"/ZSH_THEME="robbyrussell"/' "$zshrc"
            sed -i 's/plugins=(git jump zsh-autosuggestions zsh-history-substring-search jsontools zsh-syntax-highlighting zsh-interactive-cd)/plugins=(git)/' "$zshrc"
            echo "${GREEN}~/.zshrc limpiado.${NC}"
        fi
    fi

    echo "${YELLOW}¿Eliminar clave SSH (~/.ssh/id_ed25519)? [y/N]: ${NC}"
    read -r remove_ssh
    if [[ "$remove_ssh" == "y" || "$remove_ssh" == "Y" ]]; then
        run_command "rm -f $HOME/.ssh/id_ed25519 $HOME/.ssh/id_ed25519.pub" "Eliminando clave SSH"
        # Eliminar entrada de GitHub en ~/.ssh/config
        local ssh_config="$HOME/.ssh/config"
        if [ -f "$ssh_config" ]; then
            sed -i '/^Host github\.com/{N;N;N;N;d;}' "$ssh_config"
            echo "${GREEN}Entrada de GitHub eliminada de ~/.ssh/config.${NC}"
        fi
        echo "${GREEN}Clave SSH eliminada.${NC}"
    fi

    echo "${YELLOW}¿Desinstalar aplicaciones instaladas por este script? [Y/n]: ${NC}"
    read -r remove_apps
    if [[ "$remove_apps" != "n" && "$remove_apps" != "N" ]]; then
        selected_apps=($(select_apps))
        for app in "${selected_apps[@]}"; do
            IFS=':' read -r name cmd _ _ <<< "$app"
            local package_name
            package_name=$(echo "$cmd" | awk '{print $NF}')
            case "$PKG_MANAGER" in
                apt)    run_command "sudo apt remove -y $package_name" "Desinstalando $name" ;;
                dnf)    run_command "sudo dnf remove -y $package_name" "Desinstalando $name" ;;
                pacman) run_command "sudo pacman -R --noconfirm $package_name" "Desinstalando $name" ;;
            esac
        done
    fi

    echo
    echo "${GREEN}Desinstalación completada.${NC}"
}

# --- Main ---

main() {
    echo "${CYAN}Script de Configuración para Linux${NC}"
    echo
    echo "${CYAN}¿Qué deseas hacer?${NC}"
    echo "${CYAN}[1] Instalar y configurar${NC}"
    echo "${CYAN}[2] Desinstalar${NC}"
    echo -n "${YELLOW}Elige una opción (1/2): ${NC}"
    read -r mode

    detect_distro

    case "$mode" in
        2)
            uninstall
            ;;
        *)
            check_dependencies
            install_oh_my_zsh
            configure_git_global
            configure_ssh_key
            selected_apps=($(select_apps))
            install_apps "${selected_apps[@]}"
            echo
            echo "${GREEN}¡Configuración completada! Reinicia la terminal para aplicar cambios.${NC}"
            echo "${YELLOW}Si Zsh no es tu shell por defecto aún, ejecuta: chsh -s \$(which zsh)${NC}"
            ;;
    esac
}

main
