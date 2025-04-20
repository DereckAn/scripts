#!/bin/bash

# Colores para la interfaz
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[1;36m'
BLUE='\033[1;34m'
NC='\033[0m' # No color

# Función para ejecutar comandos con retroalimentación
run_command() {
    local cmd="$1"
    local desc="$2"
    echo -n "${YELLOW}${desc}...${NC} "
    if $cmd >/dev/null 2>&1; then
        echo "${GREEN}Hecho${NC}"
        return 0
    else
        echo "${RED}Error${NC}"
        return 1
    fi
}

# Verificar Homebrew
check_brew() {
    echo "${YELLOW}Verificando Homebrew...${NC}"
    if ! command -v brew >/dev/null 2>&1; then
        echo "${YELLOW}Homebrew no encontrado. Instalando...${NC}"
        run_command '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"' "Instalando Homebrew" || {
            echo "${RED}Error instalando Homebrew. Saliendo...${NC}"
            exit 1
        }
    else
        echo "${GREEN}Homebrew encontrado.${NC}"
    fi
}

# Verificar Git
check_git() {
    echo "${YELLOW}Verificando Git...${NC}"
    if ! command -v git >/dev/null 2>&1; then
        echo "${YELLOW}Git no encontrado. Instalando...${NC}"
        run_command "brew install git" "Instalando Git" || {
            echo "${RED}Error instalando Git. Saliendo...${NC}"
            exit 1
        }
    else
        echo "${GREEN}Git encontrado.${NC}"
    fi
}

# Instalar Oh My Zsh y Powerlevel10k
install_oh_my_zsh() {
    echo "${YELLOW}Configurando Oh My Zsh...${NC}"
    if [ -d "$HOME/.oh-my-zsh" ]; then
        echo "${GREEN}Oh My Zsh ya instalado.${NC}"
    else
        echo "${YELLOW}Instalando Oh My Zsh...${NC}"
        run_command 'sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" --unattended' "Instalando Oh My Zsh" || {
            echo "${RED}Error instalando Oh My Zsh. Saliendo...${NC}"
            exit 1
        }
    fi

    echo "${YELLOW}Instalando Powerlevel10k...${NC}"
    run_command "git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k" "Instalando Powerlevel10k"
    sed -i '' 's/ZSH_THEME="robbyrussell"/ZSH_THEME="powerlevel10k\/powerlevel10k"/' ~/.zshrc

    echo "${YELLOW}Instalando plugins de Zsh...${NC}"
    run_command "git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autosuggestions" "Instalando zsh-autosuggestions"
    run_command "git clone https://github.com/zsh-users/zsh-history-substring-search ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-history-substring-search" "Instalando zsh-history-substring-search"
    run_command "git clone https://github.com/zsh-users/zsh-syntax-highlighting ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting" "Instalando zsh-syntax-highlighting"
    sed -i '' 's/plugins=(git)/plugins=(git jump zsh-autosuggestions zsh-history-substring-search jsontools zsh-syntax-highlighting zsh-interactive-cd)/' ~/.zshrc
}

# Configurar credenciales de Git
configure_git_global() {
    echo "${YELLOW}¿Configurar credenciales globales de Git? [Y/n]: ${NC}"
    read -r configure_git
    if [[ "$configure_git" != "n" && "$configure_git" != "N" ]]; then
        echo "${YELLOW}Configurando credenciales de Git...${NC}"
        # Verificar si ya están configuradas
        current_user=$(git config --global user.name)
        current_email=$(git config --global user.email)
        if [ -n "$current_user" ] && [ -n "$current_email" ]; then
            echo "${GREEN}Credenciales ya configuradas: $current_user <$current_email>${NC}"
            echo "${YELLOW}¿Sobrescribir? [y/N]: ${NC}"
            read -r overwrite
            if [[ "$overwrite" != "y" && "$overwrite" != "Y" ]]; then
                return
            fi
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

# Configurar clave SSH
configure_ssh_key() {
    echo "${YELLOW}¿Configurar clave SSH para GitHub? [Y/n]: ${NC}"
    read -r configure_ssh
    if [[ "$configure_ssh" != "n" && "$configure_ssh" != "N" ]]; then
        ssh_key_path="$HOME/.ssh/id_ed25519"
        if [ -f "$ssh_key_path" ]; then
            echo "${GREEN}Clave SSH ya existe en ~/.ssh/id_ed25519.${NC}"
            echo "${YELLOW}¿Generar nueva clave (sobrescribirá la existente)? [y/N]: ${NC}"
            read -r overwrite
            if [[ "$overwrite" != "y" && "$overwrite" != "Y" ]]; then
                echo "${YELLOW}Usando clave existente.${NC}"
                add_ssh_key_to_github
                return
            fi
        fi

        # Instalar GitHub CLI si no está presente
        if ! command -v gh >/dev/null 2>&1; then
            echo "${YELLOW}GitHub CLI no encontrado. Instalando...${NC}"
            run_command "brew install gh" "Instalando GitHub CLI"
        fi

        echo "${YELLOW}Generando clave SSH...${NC}"
        echo -n "Ingresa tu correo para SSH (e.g., juan@example.com): "
        read -r ssh_email
        if [ -n "$ssh_email" ]; then
            run_command "ssh-keygen -t ed25519 -C \"$ssh_email\" -f \"$ssh_key_path\" -N \"\"" "Generando clave SSH" || {
                echo "${RED}Error generando clave SSH.${NC}"
                return
            }
            run_command "eval \$(ssh-agent -s)" "Iniciando ssh-agent"
            run_command "ssh-add $ssh_key_path" "Añadiendo clave SSH al agente"

            # Configurar ~/.ssh/config
            ssh_config_path="$HOME/.ssh/config"
            ssh_config_content="
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
"
            mkdir -p "$(dirname "$ssh_config_path")"
            if ! grep -q "Host github.com" "$ssh_config_path" 2>/dev/null; then
                echo "$ssh_config_content" >> "$ssh_config_path"
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

# Añadir clave SSH a GitHub
add_ssh_key_to_github() {
    local public_key_path="$HOME/.ssh/id_ed25519.pub"
    if [ ! -f "$public_key_path" ]; then
        echo "${RED}No se encontró la clave pública SSH.${NC}"
        return
    fi

    if command -v gh >/dev/null 2>&1; then
        echo "${YELLOW}Verificando autenticación en GitHub CLI...${NC}"
        if ! gh auth status >/dev/null 2>&1; then
            echo "${YELLOW}Autenticando en GitHub CLI...${NC}"
            run_command "gh auth login" "Autenticando en GitHub CLI" || {
                show_ssh_key_instructions
                return
            }
        fi
        echo "${YELLOW}Añadiendo clave SSH a GitHub...${NC}"
        run_command "gh ssh-key add \"$public_key_path\" --title \"MacBook_$(date +%Y%m%d)\" --type authentication" "Añadiendo clave SSH a GitHub" || {
            show_ssh_key_instructions
            return
        }
        echo "${GREEN}Clave SSH añadida a GitHub.${NC}"

        echo "${YELLOW}Probando conexión SSH con GitHub...${NC}"
        if ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
            echo "${GREEN}Conexión SSH verificada.${NC}"
        else
            echo "${YELLOW}No se pudo verificar la conexión. Verifica la clave en GitHub.${NC}"
        fi
    else
        echo "${RED}GitHub CLI no encontrado.${NC}"
        show_ssh_key_instructions
    fi
}

# Mostrar instrucciones para añadir clave SSH manualmente
show_ssh_key_instructions() {
    local public_key_path="$HOME/.ssh/id_ed25519.pub"
    if [ -f "$public_key_path" ]; then
        echo "${CYAN}Clave pública SSH:${NC}"
        cat "$public_key_path"
        echo
        echo "${CYAN}Instrucciones:${NC}"
        echo "1. Copia la clave pública arriba."
        echo "2. Ve a https://github.com/settings/keys"
        echo "3. Haz clic en 'New SSH key' o 'Add SSH key'."
        echo "4. Pega la clave en el campo 'Key' y dale un título (e.g., 'MacBook')."
        echo "5. Haz clic en 'Add SSH key'."
    else
        echo "${RED}No se encontró la clave pública SSH.${NC}"
    fi
}

# Verificar si una aplicación está instalada
is_app_installed() {
    local package_name="$1"
    local is_cask="$2"
    if [ "$is_cask" = "true" ]; then
        brew list --cask | grep -q "^${package_name}$"
    else
        brew list | grep -q "^${package_name}$"
    fi
    return $?
}

# Añadir al PATH
add_to_path() {
    local app_name="$1"
    local path_to_add="$2"
    local executable="$3"
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
    echo "# Añadido por setup_macos.sh" >> "$zshrc"
    echo "$export_line" >> "$zshrc"
    echo "${GREEN}Ruta para ${app_name} añadida al PATH.${NC}"
}

# Seleccionar aplicaciones
select_apps() {
    echo "${CYAN}Selecciona las aplicaciones a instalar por categoría:${NC}"
    local selected_apps=()

    # Definir categorías y aplicaciones
    declare -A categories=(
        ["Gestores de Paquetes"]="pnpm:brew install pnpm:false:: Bun:brew install oven-sh/bun/bun:false:: Yarn:brew install yarn:false:: npm:brew install node:false::"
        ["Herramientas de Contenedores"]="Docker:brew install --cask docker:true:: kubectl:brew install kubectl:false:: Minikube:brew install minikube:false::"
        ["IDEs y Editores"]="Visual Studio Code:brew install --cask visual-studio-code:true:: Cursor:brew install --cask cursor:true:: IntelliJ IDEA:brew install --cask intellij-idea:true:: WebStorm:brew install --cask webstorm:true::"
        ["Navegadores"]="Google Chrome:brew install --cask google-chrome:true:: Brave:brew install --cask brave-browser:true:: Opera:brew install --cask opera:true:: Firefox:brew install --cask firefox:true::"
        ["Terminales"]="iTerm2:brew install --cask iterm2:true:: Warp:brew install --cask warp:true::"
        ["Lenguajes de Programación"]="Python:brew install python:false:/opt/homebrew/bin:python3 Java:brew install java:false:/opt/homebrew/opt/openjdk/bin:java Rust:brew install rust:false:/opt/homebrew/bin:rustc C++ (clang):brew install llvm:false:/opt/homebrew/opt/llvm/bin:clang++ C# (Mono):brew install mono:false:/opt/homebrew/bin:mono Go:brew install go:false:/opt/homebrew/bin:go Ruby:brew install ruby:false:/opt/homebrew/bin:ruby PHP:brew install php:false:/opt/homebrew/bin:php TypeScript:brew install typescript:false:/opt/homebrew/bin:tsc"
        ["Bases de Datos"]="PostgreSQL:brew install postgresql:false:: MySQL:brew install mysql:false:: MongoDB:brew install mongodb-community:false::"
        ["Otros"]="Raycast:brew install raycast:false:: Telegram:brew install --cask telegram:true:: Slack:brew install --cask slack:true:: Tailscale:brew install tailscale:false:: fzf:brew install fzf:false:: GitHub CLI (gh):brew install gh:false:: Obsidian:brew install --cask obsidian:true:: Notion:brew install --cask notion:true::"
    )

    for category in "${!categories[@]}"; do
        echo
        echo "${BLUE}Categoría: $category${NC}"
        echo "${CYAN}ID   Aplicación${NC}"

        # Parsear aplicaciones
        IFS=' ' read -ra apps <<< "${categories[$category]}"
        local app_list=()
        local i=1
        for app in "${apps[@]}"; do
            IFS=':' read -r name cmd cask path executable <<< "$app"
            echo "${CYAN}[$i]  $name${NC}"
            app_list[$i]="$name:$cmd:$cask:$path:$executable"
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

    # Devolver aplicaciones seleccionadas
    printf '%s\n' "${selected_apps[@]}"
}

# Instalar aplicaciones
install_apps() {
    local apps=("$@")
    if [ ${#apps[@]} -eq 0 ]; then
        echo "${YELLOW}No se seleccionaron aplicaciones.${NC}"
        return
    fi

    echo "${CYAN}Aplicaciones a instalar:${NC}"
    for app in "${apps[@]}"; do
        IFS=':' read -r name _ _ _ _ <<< "$app"
        echo "  - $name"
    done

    for app in "${apps[@]}"; do
        IFS=':' read -r name cmd cask path executable <<< "$app"
        local package_name=$(echo "$cmd" | awk '{print $NF}')
        if is_app_installed "$package_name" "$cask"; then
            echo "${GREEN}${name} ya está instalado.${NC}"
            if [ -n "$path" ] && [ -n "$executable" ]; then
                add_to_path "$name" "$path" "$executable"
            fi
            continue
        fi
        echo "${YELLOW}Instalando ${name}...${NC}"
        run_command "$cmd" "Instalando ${name}" || echo "${RED}Error instalando ${name}.${NC}"
        if [ -n "$path" ] && [ -n "$executable" ]; then
            add_to_path "$name" "$path" "$executable"
        fi
    done
}

# Ocultar el Dock
hide_dock() {
    echo "${YELLOW}¿Ocultar el Dock de macOS? [Y/n]: ${NC}"
    read -r hide_dock
    if [[ "$hide_dock" != "n" && "$hide_dock" != "N" ]]; then
        run_command "defaults write com.apple.dock autohide -bool true && killall Dock" "Ocultando Dock"
        echo "${GREEN}Dock ocultado.${NC}"
    else
        echo "${GREEN}El Dock permanecerá visible.${NC}"
    fi
}

# Reiniciar terminal
restart_terminal() {
    echo "${YELLOW}¿Reiniciar la terminal para aplicar cambios? [Y/n]: ${NC}"
    read -r restart
    if [[ "$restart" != "n" && "$restart" != "N" ]]; then
        echo "${YELLOW}Abriendo nueva ventana de terminal y cerrando la actual...${NC}"
        run_command "osascript -e 'tell application \"Terminal\" to do script \"\"' -e 'tell application \"Terminal\" to close (every window whose name contains \"bash\")'" "Reiniciando terminal"
        exit 0
    else
        echo "${YELLOW}No se reinició la terminal. Reinicia manualmente para aplicar cambios.${NC}"
    fi
}

# Función principal
main() {
    echo "${CYAN}Script de Configuración para macOS${NC}"
    echo

    check_brew
    check_git
    install_oh_my_zsh
    configure_git_global
    configure_ssh_key
    selected_apps=($(select_apps))
    install_apps "${selected_apps[@]}"
    hide_dock
    echo
    echo "${GREEN}¡Configuración completada! Los cambios en la terminal requieren reiniciar.${NC}"
    restart_terminal
}

main