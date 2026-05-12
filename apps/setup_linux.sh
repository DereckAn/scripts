#!/usr/bin/env bash

# Colores para la interfaz
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[1;36m'
BLUE=$'\033[1;34m'
NC=$'\033[0m' # No color

# Función para ejecutar comandos con retroalimentación
run_command() {
    local cmd="$1"
    local desc="$2"
    printf "${YELLOW}%s...${NC} " "$desc"
    local error_output
    error_output=$(eval "$cmd" 2>&1 1>/dev/null)
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        printf "${GREEN}Hecho${NC}\n"
        return 0
    else
        printf "${RED}Error (código $exit_code)${NC}\n"
        if [ -n "$error_output" ]; then
            printf "${RED}  → %s${NC}\n" "$error_output"
        fi
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Detección de distribución y gestor de paquetes
#
# En macOS el gestor es siempre Homebrew. En Linux variamos según la familia:
#   - apt    -> Debian, Ubuntu, Linux Mint, Pop!_OS
#   - dnf    -> Fedora, RHEL, Rocky, AlmaLinux
#   - pacman -> Arch, Manjaro, EndeavourOS, Garuda
# Las apps gráficas que no tienen paquete nativo se instalan vía Flatpak.
# ---------------------------------------------------------------------------
PKG_MANAGER=""
PKG_INSTALL=""
PKG_UPDATE=""
PKG_REMOVE=""
DISTRO=""

detect_distro() {
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        DISTRO="$ID"
    else
        echo "${RED}No se pudo detectar la distribución (/etc/os-release). Saliendo...${NC}"
        exit 1
    fi

    case "$DISTRO" in
        ubuntu|debian|linuxmint|pop|elementary|zorin|kali|raspbian)
            PKG_MANAGER="apt"
            PKG_INSTALL="sudo apt-get install -y"
            PKG_UPDATE="sudo apt-get update -y"
            PKG_REMOVE="sudo apt-get remove -y"
            ;;
        fedora|rhel|centos|rocky|almalinux|nobara)
            PKG_MANAGER="dnf"
            PKG_INSTALL="sudo dnf install -y"
            PKG_UPDATE="sudo dnf check-update"
            PKG_REMOVE="sudo dnf remove -y"
            ;;
        arch|manjaro|endeavouros|garuda|cachyos)
            PKG_MANAGER="pacman"
            PKG_INSTALL="sudo pacman -S --noconfirm --needed"
            PKG_UPDATE="sudo pacman -Sy"
            PKG_REMOVE="sudo pacman -R --noconfirm"
            ;;
        *)
            # Familias derivadas: intentar adivinar por ID_LIKE
            case "${ID_LIKE:-}" in
                *debian*|*ubuntu*) PKG_MANAGER="apt";  PKG_INSTALL="sudo apt-get install -y"; PKG_UPDATE="sudo apt-get update -y"; PKG_REMOVE="sudo apt-get remove -y" ;;
                *fedora*|*rhel*)   PKG_MANAGER="dnf";  PKG_INSTALL="sudo dnf install -y";     PKG_UPDATE="sudo dnf check-update";  PKG_REMOVE="sudo dnf remove -y" ;;
                *arch*)            PKG_MANAGER="pacman"; PKG_INSTALL="sudo pacman -S --noconfirm --needed"; PKG_UPDATE="sudo pacman -Sy"; PKG_REMOVE="sudo pacman -R --noconfirm" ;;
                *)
                    echo "${RED}Distribución '$DISTRO' no soportada. Saliendo...${NC}"
                    exit 1
                    ;;
            esac
            ;;
    esac

    echo "${GREEN}Distribución detectada: ${DISTRO} (gestor: ${PKG_MANAGER}).${NC}"
}

# Asegurar dependencias base: curl, git y zsh
bootstrap_base() {
    echo "${YELLOW}Actualizando índice de paquetes...${NC}"
    eval "$PKG_UPDATE" >/dev/null 2>&1 || true

    local dep
    for dep in curl git zsh; do
        if command -v "$dep" >/dev/null 2>&1; then
            echo "${GREEN}${dep} encontrado.${NC}"
        else
            echo "${YELLOW}${dep} no encontrado. Instalando...${NC}"
            run_command "$PKG_INSTALL $dep" "Instalando $dep" || {
                echo "${RED}Error instalando ${dep}. Saliendo...${NC}"
                exit 1
            }
        fi
    done
}

# Asegurar que flatpak esté disponible y con el remoto Flathub configurado.
# Se usa como mecanismo de respaldo para apps gráficas sin paquete nativo.
ensure_flatpak() {
    if ! command -v flatpak >/dev/null 2>&1; then
        echo "${YELLOW}Flatpak no encontrado. Instalando...${NC}"
        run_command "$PKG_INSTALL flatpak" "Instalando Flatpak" || return 1
    fi
    if ! flatpak remotes 2>/dev/null | grep -q "flathub"; then
        run_command "flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo" "Añadiendo remoto Flathub"
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Resolución del .zshrc correcto
#
# La mayoría de terminales (GNOME Terminal, Konsole, Alacritty, Kitty, Warp…)
# NO tocan $ZDOTDIR, así que el rc real es ~/.zshrc.
#
# Otras (Terax, y la terminal integrada de VS Code / Cursor / Trae y forks)
# redirigen $ZDOTDIR a un directorio EFÍMERO que ellas regeneran, y cargan el
# rc real desde una variable puntero (TERAX_USER_ZDOTDIR o USER_ZDOTDIR).
# Escribir en el directorio efímero se pierde, así que apuntamos al rc real.
#
# El instalador de Oh My Zsh y `p10k configure` SÍ respetan $ZDOTDIR; por eso
# el bloque que escribimos resuelve la ruta de p10k en tiempo de ejecución con
# ${ZDOTDIR:-$HOME}, que coincide con donde el asistente guarda la config.
# ---------------------------------------------------------------------------
USER_ZSHRC=""
TERAX_DETECTED=0
resolve_user_zshrc() {
    TERAX_DETECTED=0
    local zdot="${ZDOTDIR:-$HOME}"

    # Caso normal: $ZDOTDIR sin redirigir -> el rc real es ~/.zshrc
    if [ "$zdot" = "$HOME" ]; then
        USER_ZSHRC="$HOME/.zshrc"
        return
    fi

    # Terax -> TERAX_USER_ZDOTDIR (fallback $HOME)
    if [ -n "$TERAX_TERMINAL" ] || [[ "$zdot" == *"/terax/"* ]]; then
        USER_ZSHRC="${TERAX_USER_ZDOTDIR:-$HOME}/.zshrc"
        TERAX_DETECTED=1
        return
    fi

    # VS Code / Cursor / Trae y forks -> USER_ZDOTDIR (fallback $HOME)
    if [ -n "$USER_ZDOTDIR" ] || [ -n "$VSCODE_INJECTION" ] || \
       [[ "$TERM_PROGRAM" == "vscode" || "$TERM_PROGRAM" == "cursor" || "$TERM_PROGRAM" == "trae" ]]; then
        USER_ZSHRC="${USER_ZDOTDIR:-$HOME}/.zshrc"
        return
    fi

    # $ZDOTDIR personalizado deliberadamente por el usuario -> respetarlo
    USER_ZSHRC="$zdot/.zshrc"
}

ZSHRC_BLOCK_START="# >>> setup_linux.sh (Oh My Zsh + Powerlevel10k) >>>"
ZSHRC_BLOCK_END="# <<< setup_linux.sh (Oh My Zsh + Powerlevel10k) <<<"

# Eliminar el bloque gestionado (entre marcadores) de un archivo (idempotente)
remove_managed_block() {
    local target="$1"
    [ -f "$target" ] || return 0
    sed -i "/^# >>> setup_linux.sh (Oh My Zsh + Powerlevel10k) >>>/,/^# <<< setup_linux.sh (Oh My Zsh + Powerlevel10k) <<</d" "$target"
}

# (Re)escribir el bloque gestionado de OMZ + p10k de forma idempotente
write_managed_block() {
    local plugins_line="$1"
    local target="$USER_ZSHRC"
    touch "$target"
    remove_managed_block "$target"
    {
        echo ""
        echo "$ZSHRC_BLOCK_START"
        echo 'export ZSH="$HOME/.oh-my-zsh"'
        echo 'ZSH_THEME="powerlevel10k/powerlevel10k"'
        echo "$plugins_line"
        echo 'source "$ZSH/oh-my-zsh.sh"'
        echo '# `p10k configure` escribe la config en ${ZDOTDIR:-$HOME}/.p10k.zsh'
        echo '[[ ! -f "${ZDOTDIR:-$HOME}/.p10k.zsh" ]] || source "${ZDOTDIR:-$HOME}/.p10k.zsh"'
        echo "$ZSHRC_BLOCK_END"
    } >> "$target"
}

# Clonar un repo solo si el destino no existe (idempotente)
clone_if_missing() {
    local repo="$1"
    local dest="$2"
    local label="$3"
    if [ -d "$dest" ]; then
        echo "${GREEN}${label} ya está clonado.${NC}"
    else
        run_command "git clone --depth=1 $repo \"$dest\"" "Clonando ${label}"
    fi
}

# Instalar Oh My Zsh y Powerlevel10k
install_oh_my_zsh() {
    echo "${YELLOW}¿Instalar Oh My Zsh y Powerlevel10k? [Y/n]: ${NC}"
    read -r install_omz
    if [[ "$install_omz" == "n" || "$install_omz" == "N" ]]; then
        echo "${YELLOW}Saltando instalación de Oh My Zsh.${NC}"
        return
    fi

    resolve_user_zshrc
    if [ "${ZDOTDIR:-$HOME}" != "$HOME" ]; then
        echo "${CYAN}Detectado \$ZDOTDIR redirigido: $ZDOTDIR${NC}"
    fi
    echo "${CYAN}La configuración de zsh se escribirá en: $USER_ZSHRC${NC}"

    # Instalar Oh My Zsh SIN que toque ningún .zshrc (lo gestionamos nosotros).
    # Exportar ZSH es obligatorio: con $ZDOTDIR definido el instalador usa
    # "$ZDOTDIR/ohmyzsh" como ruta de instalación por defecto.
    export ZSH="$HOME/.oh-my-zsh"
    if [ -d "$ZSH" ]; then
        echo "${GREEN}Oh My Zsh ya está instalado en $ZSH.${NC}"
    else
        echo "${YELLOW}Instalando Oh My Zsh...${NC}"
        # Asegurar que el .zshrc que inspecciona el instalador exista, para que
        # --keep-zshrc lo conserve y NO escriba su plantilla (evita duplicar
        # `source oh-my-zsh.sh`).
        touch "$USER_ZSHRC" "${ZDOTDIR:-$HOME}/.zshrc" 2>/dev/null
        RUNZSH=no CHSH=no KEEP_ZSHRC=yes \
            sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended --keep-zshrc
        if [ ! -d "$ZSH" ]; then
            echo "${RED}Error instalando Oh My Zsh.${NC}"
            exit 1
        fi
        echo "${GREEN}Oh My Zsh instalado.${NC}"
    fi

    # Tema y plugins (idempotente)
    local custom="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"
    echo "${YELLOW}Instalando Powerlevel10k y plugins...${NC}"
    clone_if_missing "https://github.com/romkatv/powerlevel10k.git" "$custom/themes/powerlevel10k" "Powerlevel10k"
    clone_if_missing "https://github.com/zsh-users/zsh-autosuggestions" "$custom/plugins/zsh-autosuggestions" "zsh-autosuggestions"
    clone_if_missing "https://github.com/zsh-users/zsh-history-substring-search" "$custom/plugins/zsh-history-substring-search" "zsh-history-substring-search"
    clone_if_missing "https://github.com/zsh-users/zsh-syntax-highlighting" "$custom/plugins/zsh-syntax-highlighting" "zsh-syntax-highlighting"

    # Escribir el bloque gestionado en el .zshrc real
    write_managed_block "plugins=(git jump zsh-autosuggestions sublime zsh-history-substring-search jsontools zsh-syntax-highlighting zsh-interactive-cd)"
    echo "${GREEN}Configuración de Oh My Zsh + Powerlevel10k escrita en $USER_ZSHRC.${NC}"

    # A diferencia de macOS, en Linux la shell por defecto suele ser bash.
    if [ "$(basename "${SHELL:-}")" != "zsh" ]; then
        echo "${YELLOW}¿Establecer zsh como tu shell por defecto (chsh)? [Y/n]: ${NC}"
        read -r set_default_shell
        if [[ "$set_default_shell" != "n" && "$set_default_shell" != "N" ]]; then
            run_command "chsh -s \"$(command -v zsh)\"" "Cambiando shell por defecto a zsh" || \
                echo "${YELLOW}No se pudo cambiar la shell. Ejecútalo manualmente: chsh -s \$(which zsh)${NC}"
        fi
    fi

    echo "${CYAN}El asistente de Powerlevel10k se abrirá al iniciar una nueva sesión de zsh${NC}"
    echo "${CYAN}(o ejecútalo manualmente con: ${NC}${GREEN}p10k configure${NC}${CYAN}).${NC}"
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
            git config --global user.name "$git_name" && printf "${GREEN}Configurando nombre de Git... Hecho${NC}\n"
            git config --global user.email "$git_email" && printf "${GREEN}Configurando correo de Git... Hecho${NC}\n"
            echo "${GREEN}Credenciales configuradas: $git_name <$git_email>${NC}"
        else
            echo "${YELLOW}No se proporcionaron credenciales válidas. Saltando...${NC}"
        fi
    else
        echo "${YELLOW}Saltando configuración de Git.${NC}"
    fi
}

# Instalar GitHub CLI según la distribución
install_github_cli() {
    if command -v gh >/dev/null 2>&1; then
        echo "${GREEN}GitHub CLI ya instalado.${NC}"
        return 0
    fi
    echo "${YELLOW}GitHub CLI no encontrado. Instalando...${NC}"
    case "$PKG_MANAGER" in
        apt)
            run_command "sudo mkdir -p -m 755 /etc/apt/keyrings && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg && echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null && sudo apt-get update && sudo apt-get install -y gh" "Instalando GitHub CLI"
            ;;
        dnf)
            run_command "sudo dnf install -y gh" "Instalando GitHub CLI"
            ;;
        pacman)
            run_command "sudo pacman -S --noconfirm --needed github-cli" "Instalando GitHub CLI"
            ;;
    esac
}

# Generar una clave ed25519 pidiendo el correo de la cuenta
# Uso: _generate_key <key_file> <account_label>
_generate_key() {
    local key_file="$1" label="$2"
    local ssh_email
    echo -n "Correo de GitHub para la cuenta '$label' (e.g., juan@example.com): "
    read -r ssh_email
    if [ -z "$ssh_email" ]; then
        echo "${YELLOW}No se proporcionó correo. Saltando cuenta '$label'.${NC}"
        return 1
    fi
    printf "${YELLOW}Generando clave ed25519 para '%s'...${NC} " "$label"
    if ssh-keygen -t ed25519 -C "$ssh_email" -f "$key_file" -N "" >/dev/null 2>&1; then
        printf "${GREEN}Hecho${NC}\n"
        return 0
    fi
    printf "${RED}Error${NC}\n"
    return 1
}

# Generar/usar una clave SSH y vincularla a una cuenta de GitHub
# Uso: setup_github_account <label> <key_file> <host_alias> [github_host]
#   label      — etiqueta legible (e.g. "personal", "trabajo")
#   key_file   — ruta de la clave (e.g. ~/.ssh/id_ed25519_trabajo)
#   host_alias — alias del Host en ~/.ssh/config (e.g. "github.com" o "github-trabajo")
setup_github_account() {
    local account_label="$1"
    local key_file="$2"
    local host_alias="$3"
    local github_host="${4:-github.com}"
    local ssh_config_path="$HOME/.ssh/config"

    # Clave: reutilizar la existente o (re)generar
    if [ -f "$key_file" ]; then
        echo "${GREEN}Ya existe una clave en $key_file.${NC}"
        echo "${YELLOW}¿Generar una nueva (sobrescribe la existente)? [y/N]: ${NC}"
        read -r overwrite
        if [[ "$overwrite" == "y" || "$overwrite" == "Y" ]]; then
            rm -f "$key_file" "$key_file.pub"
            _generate_key "$key_file" "$account_label" || return
        else
            echo "${YELLOW}Usando la clave existente para '$account_label'.${NC}"
        fi
    else
        _generate_key "$key_file" "$account_label" || return
    fi

    # Añadir al agente (en Linux el agente del escritorio/keyring persiste la clave)
    eval "$(ssh-agent -s)" >/dev/null 2>&1
    if ssh-add "$key_file" >/dev/null 2>&1; then
        echo "${GREEN}Clave añadida al agente SSH.${NC}"
    else
        echo "${YELLOW}Advertencia: no se pudo añadir la clave al agente.${NC}"
    fi

    # Bloque Host en ~/.ssh/config (idempotente, coincidencia anclada)
    mkdir -p "$(dirname "$ssh_config_path")"; chmod 700 "$(dirname "$ssh_config_path")" 2>/dev/null
    [ ! -f "$ssh_config_path" ] && install -m 600 /dev/null "$ssh_config_path"
    if ! grep -qE "^Host[[:space:]]+${host_alias}([[:space:]]|\$)" "$ssh_config_path" 2>/dev/null; then
        printf "\nHost %s\n    HostName %s\n    User git\n    IdentityFile %s\n    IdentitiesOnly yes\n" \
            "$host_alias" "$github_host" "$key_file" >> "$ssh_config_path"
        echo "${GREEN}Bloque Host '$host_alias' (HostName $github_host) añadido a ~/.ssh/config.${NC}"
    else
        echo "${GREEN}El host '$host_alias' ya existe en ~/.ssh/config.${NC}"
    fi

    add_ssh_key_to_github "$key_file" "$host_alias" "$account_label" "$github_host"
}

# Opciones globales de SSH (añadir claves al agente automáticamente), una vez.
# En macOS aquí iría "UseKeychain yes"; en Linux no aplica.
ensure_ssh_defaults() {
    local cfg="$HOME/.ssh/config"
    mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh" 2>/dev/null
    [ ! -f "$cfg" ] && install -m 600 /dev/null "$cfg"
    if ! grep -qE "^Host \*$" "$cfg" 2>/dev/null; then
        printf "Host *\n    AddKeysToAgent yes\n\n" >> "$cfg"
        echo "${GREEN}Opciones SSH globales añadidas a ~/.ssh/config.${NC}"
    fi
}

# Convierte una etiqueta libre en un slug seguro para nombre de archivo/host
slugify() {
    local s
    s=$(echo "$1" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-')
    echo "${s:-cuenta}"
}

# Configurar una o varias claves SSH para GitHub (tantas cuentas como quieras)
configure_ssh_key() {
    echo "${YELLOW}¿Configurar clave(s) SSH para GitHub? [Y/n]: ${NC}"
    read -r configure_ssh
    if [[ "$configure_ssh" == "n" || "$configure_ssh" == "N" ]]; then
        echo "${YELLOW}Saltando configuración de clave SSH.${NC}"
        return
    fi

    # Instalar GitHub CLI una sola vez
    install_github_cli

    ensure_ssh_defaults

    # Cuenta 1: personal (host por defecto github.com -> clonas como git@github.com:...)
    echo
    echo "${CYAN}=== Cuenta 1: personal (host: github.com) ===${NC}"
    setup_github_account "personal" "$HOME/.ssh/id_ed25519" "github.com" "github.com"

    # Cuentas adicionales, en bucle (trabajo, clientes, GitHub Enterprise, etc.)
    local n=2
    while true; do
        echo
        echo "${CYAN}¿Configurar otra clave SSH para otra cuenta de GitHub? [y/N]: ${NC}"
        read -r more
        [[ "$more" == "y" || "$more" == "Y" ]] || break

        local default_label="cuenta$n"
        [ "$n" -eq 2 ] && default_label="trabajo"
        echo -n "Etiqueta para esta cuenta (e.g., trabajo, cliente1) [$default_label]: "
        read -r label
        [ -z "$label" ] && label="$default_label"
        local safe
        safe=$(slugify "$label")

        # ¿github.com o GitHub Enterprise (otra URL)?
        local gh_host="github.com" host_choice ent
        echo "${YELLOW}¿Esta cuenta es de github.com o de GitHub Enterprise con URL propia?${NC}"
        echo "  ${CYAN}[1]${NC} github.com (incluye cuentas gestionadas/EMU con login por SSO)"
        echo "  ${CYAN}[2]${NC} GitHub Enterprise Server o data residency (otra URL, e.g. github.miempresa.com o algo.ghe.com)"
        printf "${YELLOW}Elige [1/2]: ${NC}"
        read -r host_choice
        if [ "$host_choice" = "2" ]; then
            printf "${YELLOW}Host de GitHub Enterprise (sin https://, e.g. github.miempresa.com): ${NC}"
            read -r ent
            ent=$(echo "$ent" | sed -E 's#^https?://##; s#/.*$##')
            [ -n "$ent" ] && gh_host="$ent"
        fi

        echo
        echo "${CYAN}=== Cuenta $n: $label (host alias: github-$safe -> $gh_host) ===${NC}"
        echo "${CYAN}Para clonar repos de esta cuenta usa: git clone git@github-$safe:org/repo.git${NC}"
        setup_github_account "$label" "$HOME/.ssh/id_ed25519_$safe" "github-$safe" "$gh_host"
        n=$((n + 1))
    done

    echo
    echo "${GREEN}Configuración de claves SSH completada ($((n - 1)) cuenta(s)).${NC}"
}

# Asegurar que gh esté autenticado con la cuenta correcta para esta clave.
# Obliga a ELEGIR explícitamente la cuenta destino (no asume la activa) y pide
# una confirmación final mostrando a qué cuenta se añadirá la clave. Por defecto
# la confirmación es NO, para no añadir la clave a la cuenta equivocada.
# Uso: _ensure_gh_account <label> [github_host]
_ensure_gh_account() {
    local label="$1" host="${2:-github.com}" active="" choice confirm
    if gh auth status -h "$host" >/dev/null 2>&1; then
        active=$(GH_HOST="$host" gh api user --jq .login 2>/dev/null)
    fi

    echo "${CYAN}--- Cuenta de GitHub para la clave de '${label}' (host: ${host}) ---${NC}"
    if [ -n "$active" ]; then
        echo "${CYAN}Cuenta activa ahora mismo: ${GREEN}${active}${NC}"
    else
        echo "${YELLOW}No hay ninguna cuenta activa en GitHub CLI.${NC}"
    fi
    echo "${YELLOW}¿A qué cuenta de GitHub quieres AÑADIR esta clave?${NC}"
    echo "  ${CYAN}[1]${NC} Usar la cuenta activa${active:+ (${active})}"
    echo "  ${CYAN}[2]${NC} Cambiar a otra cuenta ya autenticada (gh auth switch)"
    echo "  ${CYAN}[3]${NC} Iniciar sesión en otra cuenta (gh auth login)"
    printf "${YELLOW}Elige [1/2/3] (por defecto 1): ${NC}"
    read -r choice
    case "$choice" in
        2)
            echo "${CYAN}Selecciona la cuenta a activar...${NC}"
            gh auth switch -h "$host" || {
                echo "${RED}No se pudo cambiar de cuenta. Si nunca iniciaste sesión con ella, usa la opción 3.${NC}"
                return 1
            }
            ;;
        3)
            echo "${CYAN}Inicia sesión con la otra cuenta (se abrirá el navegador)...${NC}"
            gh auth login --hostname "$host" --scopes admin:public_key || return 1
            ;;
        *)
            : # usar la cuenta activa
            ;;
    esac

    active=$(GH_HOST="$host" gh api user --jq .login 2>/dev/null)
    echo "${YELLOW}La clave de '${label}' se añadirá a la cuenta: ${GREEN}${active:-desconocida}${NC} (host: ${host})"
    printf "${YELLOW}¿Es la cuenta correcta? [y/N]: ${NC}"
    read -r confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "${YELLOW}Cancelado: no se añadió la clave de '${label}'.${NC}"
        return 1
    fi
    return 0
}

# Asegurar el scope admin:public_key (necesario para `gh ssh-key add`)
# Uso: _ensure_gh_scope [github_host]
_ensure_gh_scope() {
    local host="${1:-github.com}"
    if gh auth status -h "$host" 2>&1 | grep -q "admin:public_key"; then
        return 0
    fi
    echo "${YELLOW}Falta el permiso 'admin:public_key' en gh (host: $host). Solicitándolo...${NC}"
    gh auth refresh -h "$host" -s admin:public_key || return 1
    return 0
}

# Añadir una clave SSH a la cuenta de GitHub activa del host indicado
# Uso: add_ssh_key_to_github <key_file> <host_alias> <label> [github_host]
add_ssh_key_to_github() {
    local key_file="${1:-$HOME/.ssh/id_ed25519}"
    local host_alias="${2:-github.com}"
    local label="${3:-personal}"
    local github_host="${4:-github.com}"
    local public_key_path="${key_file}.pub"

    if [ ! -f "$public_key_path" ]; then
        echo "${RED}No se encontró la clave pública SSH: $public_key_path${NC}"
        return
    fi

    if ! command -v gh >/dev/null 2>&1; then
        echo "${RED}GitHub CLI no encontrado.${NC}"
        show_ssh_key_instructions "$public_key_path"
        return
    fi

    _ensure_gh_account "$label" "$github_host" || { show_ssh_key_instructions "$public_key_path"; return; }
    _ensure_gh_scope "$github_host"            || { show_ssh_key_instructions "$public_key_path"; return; }

    local key_title="$(hostname -s 2>/dev/null || hostname)_${host_alias}_$(date +%Y%m%d)"
    echo "${YELLOW}Añadiendo clave SSH con título '$key_title' (host: $github_host)...${NC}"
    local out rc
    out=$(GH_HOST="$github_host" gh ssh-key add "$public_key_path" --title "$key_title" --type authentication 2>&1)
    rc=$?
    if [ $rc -eq 0 ]; then
        echo "${GREEN}Clave SSH añadida a GitHub.${NC}"
    elif echo "$out" | grep -qiE "already|key is already in use"; then
        echo "${GREEN}La clave ya estaba registrada en la cuenta. OK.${NC}"
    else
        echo "${RED}No se pudo añadir la clave: $out${NC}"
        show_ssh_key_instructions "$public_key_path"
        return
    fi

    echo "${YELLOW}Probando conexión SSH (git@${host_alias})...${NC}"
    if ssh -T "git@${host_alias}" -o StrictHostKeyChecking=accept-new 2>&1 | grep -q "successfully authenticated"; then
        echo "${GREEN}Conexión SSH verificada para $host_alias.${NC}"
    else
        echo "${YELLOW}No se pudo verificar la conexión todavía. Revisa la clave en GitHub.${NC}"
    fi
}

# Mostrar instrucciones para añadir clave SSH manualmente
show_ssh_key_instructions() {
    local public_key_path="${1:-$HOME/.ssh/id_ed25519.pub}"
    if [ -f "$public_key_path" ]; then
        echo "${CYAN}Clave pública SSH:${NC}"
        cat "$public_key_path"
        echo
        echo "${CYAN}Instrucciones:${NC}"
        echo "1. Copia la clave pública arriba."
        echo "2. Ve a https://github.com/settings/keys"
        echo "3. Haz clic en 'New SSH key' o 'Add SSH key'."
        echo "4. Pega la clave en el campo 'Key' y dale un título (e.g., 'Linux')."
        echo "5. Haz clic en 'Add SSH key'."
    else
        echo "${RED}No se encontró la clave pública SSH.${NC}"
    fi
}

# ---------------------------------------------------------------------------
# Comprobación de instalación
#
# En Linux no hay "cask"; consultamos el gestor nativo (dpkg/rpm/pacman) y,
# como respaldo, Flatpak. Las apps con instalador propio (@func) se comprueban
# por su ejecutable.
# ---------------------------------------------------------------------------
is_app_installed() {
    local package_name="$1"
    case "$PKG_MANAGER" in
        apt)    dpkg-query -W -f='${Status}' "$package_name" 2>/dev/null | grep -q "install ok installed" ;;
        dnf)    rpm -q "$package_name" >/dev/null 2>&1 ;;
        pacman) pacman -Q "$package_name" >/dev/null 2>&1 ;;
        *)      return 1 ;;
    esac
}

is_flatpak_installed() {
    command -v flatpak >/dev/null 2>&1 || return 1
    flatpak list --columns=application 2>/dev/null | grep -qx "$1"
}

# ¿Está presente esta app? Decide según el tipo de instalación.
# Uso: app_is_present <field> <flatpak_id> <executable>
app_is_present() {
    local field="$1" flatpak_id="$2" executable="$3"
    if [ -n "$field" ]; then
        if [[ "$field" == @* ]]; then
            [ -n "$executable" ] && command -v "$executable" >/dev/null 2>&1
            return $?
        fi
        is_app_installed "$field"
        return $?
    fi
    if [ -n "$flatpak_id" ]; then
        is_flatpak_installed "$flatpak_id"
        return $?
    fi
    return 1
}

# Ejecutar la instalación de una app según su tipo.
# Uso: run_install <field> <flatpak_id> <name>
run_install() {
    local field="$1" flatpak_id="$2" name="$3"
    if [ -n "$field" ]; then
        if [[ "$field" == @* ]]; then
            "${field#@}"   # instalador propio (función)
        else
            run_command "$PKG_INSTALL $field" "Instalando $name"
        fi
        return
    fi
    if [ -n "$flatpak_id" ]; then
        ensure_flatpak && run_command "flatpak install -y flathub $flatpak_id" "Instalando $name (Flatpak)"
    fi
}

# --- Instaladores propios (apps sin paquete nativo simple) ---

install_node() {
    case "$PKG_MANAGER" in
        apt|dnf) run_command "$PKG_INSTALL nodejs npm" "Instalando Node.js + npm" ;;
        pacman)  run_command "$PKG_INSTALL nodejs npm" "Instalando Node.js + npm" ;;
    esac
}

install_pnpm() {
    run_command "curl -fsSL https://get.pnpm.io/install.sh | sh -" "Instalando pnpm"
}

install_yarn() {
    if command -v corepack >/dev/null 2>&1; then
        run_command "corepack enable && corepack prepare yarn@stable --activate" "Activando Yarn vía corepack"
    elif command -v npm >/dev/null 2>&1; then
        run_command "sudo npm install -g yarn" "Instalando Yarn (npm global)"
    else
        echo "${YELLOW}Yarn requiere Node.js/npm. Instala Node primero.${NC}"
    fi
}

install_bun() {
    run_command "curl -fsSL https://bun.sh/install | bash" "Instalando Bun"
}

install_rust() {
    run_command "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y" "Instalando Rust (rustup)"
}

install_typescript() {
    if command -v npm >/dev/null 2>&1; then
        run_command "sudo npm install -g typescript" "Instalando TypeScript"
    else
        echo "${YELLOW}TypeScript requiere Node.js/npm. Instala Node primero.${NC}"
    fi
}

install_kubectl() {
    run_command "curl -fsSLO \"https://dl.k8s.io/release/\$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl\" && sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && rm -f kubectl" "Instalando kubectl"
}

install_minikube() {
    run_command "curl -fsSLO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64 && sudo install minikube-linux-amd64 /usr/local/bin/minikube && rm -f minikube-linux-amd64" "Instalando Minikube"
}

install_vscode() {
    case "$PKG_MANAGER" in
        apt)
            run_command "curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /usr/share/keyrings/packages.microsoft.gpg >/dev/null && echo \"deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main\" | sudo tee /etc/apt/sources.list.d/vscode.list >/dev/null && sudo apt-get update && sudo apt-get install -y code" "Instalando Visual Studio Code"
            ;;
        dnf)
            run_command "sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc && printf '[code]\nname=Visual Studio Code\nbaseurl=https://packages.microsoft.com/yumrepos/vscode\nenabled=1\nautorefresh=1\ngpgcheck=1\ngpgkey=https://packages.microsoft.com/keys/microsoft.asc\n' | sudo tee /etc/yum.repos.d/vscode.repo >/dev/null && sudo dnf install -y code" "Instalando Visual Studio Code"
            ;;
        pacman)
            echo "${CYAN}En Arch, 'code' (OSS) está en los repos; el build oficial está en AUR (visual-studio-code-bin).${NC}"
            run_command "$PKG_INSTALL code" "Instalando Code - OSS" || \
                { ensure_flatpak && run_command "flatpak install -y flathub com.visualstudio.code" "Instalando VS Code (Flatpak)"; }
            ;;
    esac
}

install_chrome() {
    case "$PKG_MANAGER" in
        apt)
            run_command "curl -fsSL -o /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && sudo apt-get install -y /tmp/google-chrome.deb && rm -f /tmp/google-chrome.deb" "Instalando Google Chrome"
            ;;
        dnf)
            run_command "sudo dnf install -y https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm" "Instalando Google Chrome"
            ;;
        pacman)
            echo "${YELLOW}Google Chrome no está en los repos oficiales de Arch.${NC}"
            echo "${CYAN}Instálalo desde AUR (e.g. 'yay -S google-chrome') o usa Chromium: sudo pacman -S chromium${NC}"
            ;;
    esac
}

install_brave() {
    # El instalador oficial de Brave soporta apt y dnf.
    case "$PKG_MANAGER" in
        apt|dnf) run_command "curl -fsS https://dl.brave.com/install.sh | sh" "Instalando Brave" ;;
        pacman)
            echo "${YELLOW}Brave no está en los repos oficiales de Arch.${NC}"
            echo "${CYAN}Instálalo desde AUR (e.g. 'yay -S brave-bin') o usa Flatpak: flatpak install flathub com.brave.Browser${NC}"
            ;;
    esac
}

install_tailscale() {
    run_command "curl -fsSL https://tailscale.com/install.sh | sh" "Instalando Tailscale"
}

install_mongodb() {
    echo "${CYAN}MongoDB Community requiere el repositorio oficial de MongoDB.${NC}"
    echo "${CYAN}Guía: https://www.mongodb.com/docs/manual/administration/install-on-linux/${NC}"
    case "$PKG_MANAGER" in
        pacman) echo "${CYAN}En Arch, usa AUR: 'yay -S mongodb-bin'.${NC}" ;;
    esac
}

# Instalar una Nerd Font (requerida por los iconos de eza)
install_nerd_font() {
    if fc-list 2>/dev/null | grep -qi "FiraCode Nerd"; then
        echo "${GREEN}FiraCode Nerd Font ya instalada.${NC}"
        return 0
    fi
    if ! command -v unzip >/dev/null 2>&1; then
        run_command "$PKG_INSTALL unzip" "Instalando unzip (para la fuente)" || {
            echo "${YELLOW}No se pudo instalar unzip; instala la Nerd Font manualmente.${NC}"; return 1; }
    fi
    local font_dir="$HOME/.local/share/fonts"
    mkdir -p "$font_dir"
    run_command "curl -fsSL -o /tmp/FiraCode.zip https://github.com/ryanoasis/nerd-fonts/releases/latest/download/FiraCode.zip && unzip -o /tmp/FiraCode.zip -d \"$font_dir\" >/dev/null && rm -f /tmp/FiraCode.zip && fc-cache -f \"$font_dir\"" "Instalando FiraCode Nerd Font"
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
    if grep -qF "$export_line" "$zshrc" 2>/dev/null; then
        echo "${GREEN}Ruta ${path_to_add} ya está en ~/.zshrc.${NC}"
        return
    fi

    echo "${YELLOW}Añadiendo ${path_to_add} al PATH en ~/.zshrc...${NC}"
    echo "# Añadido por setup_linux.sh" >> "$zshrc"
    echo "$export_line" >> "$zshrc"
    echo "${GREEN}Ruta para ${app_name} añadida al PATH.${NC}"
}

# Escribir línea en ~/.zshrc si no existe
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

# Configuración post-instalación por herramienta
post_install_config() {
    local name="$1"
    case "$name" in
        eza)
            echo "${YELLOW}Instalando FiraCode Nerd Font (requerida para iconos de eza)...${NC}"
            install_nerd_font
            write_to_zshrc "eza alias ls" 'alias ls="eza --color=auto --icons"'
            write_to_zshrc "eza alias ll" 'alias ll="eza -lh --icons --git"'
            write_to_zshrc "eza alias la" 'alias la="eza -lah --icons --git"'
            write_to_zshrc "eza alias lt" 'alias lt="eza --tree --icons"'
            echo "${CYAN}Nota: configura tu terminal para usar 'FiraCode Nerd Font' para ver los iconos.${NC}"
            ;;
        zoxide)
            write_to_zshrc "zoxide init" 'eval "$(zoxide init zsh)"'
            ;;
        Docker)
            echo "${CYAN}Habilitando el servicio de Docker y añadiendo tu usuario al grupo 'docker'...${NC}"
            run_command "sudo systemctl enable --now docker" "Habilitando servicio docker" || true
            run_command "sudo usermod -aG docker $USER" "Añadiendo $USER al grupo docker"
            echo "${YELLOW}Cierra sesión y vuelve a entrar para usar docker sin sudo.${NC}"
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Catálogo de aplicaciones
#
# Cada entrada (delimitada por ':') tiene 7 campos:
#   name:apt:dnf:pacman:flatpak_id:path:executable
#
# Los campos apt/dnf/pacman pueden ser:
#   - un nombre de paquete    -> se instala con $PKG_INSTALL
#   - "@funcion"              -> instalador propio (función de este script)
#   - vacío                   -> no disponible nativamente; se usa flatpak_id
# flatpak_id se usa como respaldo cuando el campo de la distro está vacío.
# path/executable son opcionales (para add_to_path).
#
# Ninguno de los campos contiene ':' (son nombres de paquete, @funciones,
# IDs de Flatpak con puntos, o rutas), por lo que el split por ':' es seguro.
# ---------------------------------------------------------------------------

# Procesar una categoría y añadir selecciones a selected_apps (array global)
process_category() {
    local category="$1"
    shift
    local apps=("$@")

    echo
    echo "${BLUE}Categoría: $category${NC}"
    echo "${CYAN}ID   Aplicación${NC}"

    local app_list=()
    local i=1
    for app in "${apps[@]}"; do
        IFS=':' read -r name apt_f dnf_f pacman_f flatpak_id path executable <<< "$app"
        local field
        case "$PKG_MANAGER" in
            apt)    field="$apt_f" ;;
            dnf)    field="$dnf_f" ;;
            pacman) field="$pacman_f" ;;
            *)      field="" ;;
        esac
        # No disponible en esta distro y sin respaldo Flatpak -> no listar
        [ -z "$field" ] && [ -z "$flatpak_id" ] && continue

        if app_is_present "$field" "$flatpak_id" "$executable"; then
            echo "${GREEN}[$i]  $name (instalado)${NC}"
        else
            echo "${CYAN}[$i]  $name${NC}"
        fi
        app_list[$i]="$name|$field|$flatpak_id|$path|$executable"
        ((i++))
    done

    printf "${YELLOW}Ingresa los números (ej. 1,3,5), 'all', '0' o 'n' para omitir: ${NC}"
    read -r choices
    choices=$(echo "$choices" | tr '[:upper:]' '[:lower:]')

    if [ "$choices" = "all" ]; then
        for ((j=1; j<i; j++)); do
            selected_apps+=("${app_list[$j]}")
        done
    elif [ "$choices" = "0" ] || [ "$choices" = "n" ] || [ -z "$choices" ]; then
        echo "${YELLOW}Omitiendo categoría $category.${NC}"
    else
        IFS=',' read -ra indices <<< "$choices"
        for idx in "${indices[@]}"; do
            if echo "$idx" | grep -qE '^[0-9]+$' && [ "$idx" -ge 1 ] && [ "$idx" -lt "$i" ]; then
                selected_apps+=("${app_list[$idx]}")
            fi
        done
    fi
}

# Seleccionar aplicaciones
select_apps() {
    echo "${CYAN}Selecciona las aplicaciones a instalar por categoría:${NC}"
    selected_apps=()

    process_category "Gestores de Paquetes" \
        "Node.js:@install_node:@install_node:@install_node:::node" \
        "pnpm:@install_pnpm:@install_pnpm:@install_pnpm:::pnpm" \
        "Bun:@install_bun:@install_bun:@install_bun::\$HOME/.bun/bin:bun" \
        "Yarn:@install_yarn:@install_yarn:@install_yarn:::yarn"

    process_category "Herramientas de Contenedores" \
        "Docker:docker.io:docker:docker:::" \
        "kubectl:@install_kubectl:@install_kubectl:@install_kubectl:::kubectl" \
        "Minikube:@install_minikube:@install_minikube:@install_minikube:::minikube"

    process_category "IDEs y Editores" \
        "Visual Studio Code:@install_vscode:@install_vscode:@install_vscode:com.visualstudio.code::code" \
        "IntelliJ IDEA::::com.jetbrains.IntelliJ-IDEA-Community::" \
        "WebStorm::::com.jetbrains.WebStorm::"

    process_category "Navegadores" \
        "Google Chrome:@install_chrome:@install_chrome:@install_chrome:::google-chrome-stable" \
        "Brave:@install_brave:@install_brave:@install_brave:com.brave.Browser::brave-browser" \
        "Firefox:firefox-esr:firefox:firefox:::" \
        "Opera::::com.opera.Opera::"

    process_category "Terminales" \
        "Kitty:kitty:kitty:kitty:::" \
        "Alacritty:alacritty:alacritty:alacritty:::"

    process_category "Lenguajes de Programacion" \
        "Python:python3:python3:python:::python3" \
        "Java:default-jdk:java-latest-openjdk:jdk-openjdk:::java" \
        "Rust:@install_rust:@install_rust:@install_rust::\$HOME/.cargo/bin:rustc" \
        "Go:golang:golang:go:::go" \
        "Ruby:ruby:ruby:ruby:::ruby" \
        "PHP:php:php:php:::php" \
        "TypeScript:@install_typescript:@install_typescript:@install_typescript:::tsc"

    process_category "Bases de Datos" \
        "PostgreSQL:postgresql:postgresql-server:postgresql:::" \
        "MariaDB:mariadb-server:mariadb-server:mariadb:::" \
        "MongoDB:@install_mongodb:@install_mongodb:@install_mongodb:::mongod"

    process_category "Herramientas CLI" \
        "eza:eza:eza:eza:::" \
        "zoxide:zoxide:zoxide:zoxide:::" \
        "btop:btop:btop:btop:::" \
        "ranger:ranger:ranger:ranger:::" \
        "fzf:fzf:fzf:fzf:::"

    process_category "Otros" \
        "Telegram:telegram-desktop:telegram-desktop:telegram-desktop:org.telegram.desktop::" \
        "Slack::::com.slack.Slack::" \
        "Tailscale:@install_tailscale:@install_tailscale:@install_tailscale:::tailscale" \
        "GitHub CLI:@install_github_cli:@install_github_cli:@install_github_cli:::gh" \
        "Obsidian::::md.obsidian.Obsidian::"
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
        IFS='|' read -r name _ _ _ _ <<< "$app"
        echo "  - $name"
    done

    for app in "${apps[@]}"; do
        IFS='|' read -r name field flatpak_id path executable <<< "$app"
        if app_is_present "$field" "$flatpak_id" "$executable"; then
            echo "${GREEN}${name} ya está instalado.${NC}"
            if [ -n "$path" ] && [ -n "$executable" ]; then
                add_to_path "$name" "$path" "$executable"
            fi
            post_install_config "$name"
            continue
        fi
        echo "${YELLOW}Instalando ${name}... (puede tardar; se muestra el progreso)${NC}"
        run_install "$field" "$flatpak_id" "$name"
        if [ -n "$path" ] && [ -n "$executable" ]; then
            add_to_path "$name" "$path" "$executable"
        fi
        post_install_config "$name"
    done
}

# Generar cheatsheet de herramientas instaladas
generate_cheatsheet() {
    local apps=("$@")
    local output="$HOME/cheatsheet_linux_setup.md"
    local date_now
    date_now=$(date '+%Y-%m-%d')

    cat > "$output" << HEREDOC
# Cheatsheet — Linux Setup
Generado el $date_now

---

## Zsh Plugins (instalados por defecto)

### zsh-autosuggestions
Sugiere comandos mientras escribes basándose en tu historial.
- Acepta sugerencia completa: → (flecha derecha) o \`End\`
- Acepta siguiente palabra: \`Ctrl + →\`

### zsh-syntax-highlighting
Colorea los comandos en tiempo real (verde = válido, rojo = inválido).
- No requiere comandos — funciona automáticamente.

### zsh-history-substring-search
Busca en el historial por subcadena.
- Buscar hacia arriba: \`↑\` (con texto ya escrito)
- Buscar hacia abajo: \`↓\`

### Oh My Zsh plugins incluidos
- \`jump\` — marca directorios: \`mark <nombre>\`, \`jump <nombre>\`
- \`jsontools\` — formatea JSON: \`pp_json\`, \`is_json\`, \`urlencode_json\`
- \`zsh-interactive-cd\` — autocompletado interactivo al usar \`cd\`

---
HEREDOC

    # Secciones por herramienta instalada
    for app in "${apps[@]}"; do
        local name
        IFS='|' read -r name _ _ _ _ <<< "$app"
        case "$name" in
            eza)
                cat >> "$output" << 'EOF'
## eza — Listado de archivos moderno

Reemplaza `ls` con iconos, colores y soporte para Git.

| Alias | Comando | Descripción |
|-------|---------|-------------|
| `ls`  | `eza --color=auto --icons` | Listado básico con iconos |
| `ll`  | `eza -lh --icons --git` | Listado detallado con info de Git |
| `la`  | `eza -lah --icons --git` | Incluye archivos ocultos |
| `lt`  | `eza --tree --icons` | Vista de árbol |

Comandos extra:
- `eza --tree --level=2` — árbol con profundidad limitada
- `eza -l --sort=size` — ordenar por tamaño
- `eza -l --sort=modified` — ordenar por fecha de modificación

> Requiere fuente: **FiraCode Nerd Font** en tu terminal.

---
EOF
            ;;
            zoxide)
                cat >> "$output" << 'EOF'
## zoxide — cd inteligente

Aprende los directorios que más usas y salta a ellos con pocas letras.

| Comando | Descripción |
|---------|-------------|
| `z foo` | Salta al directorio más frecuente que coincida con "foo" |
| `z foo bar` | Coincidencia con múltiples términos |
| `z -` | Vuelve al directorio anterior |
| `zi` | Modo interactivo con fzf (requiere fzf) |
| `zoxide query -l` | Lista todos los directorios en la base de datos |

> Activado con `eval "$(zoxide init zsh)"` en `~/.zshrc`.

---
EOF
            ;;
            btop)
                cat >> "$output" << 'EOF'
## btop — Monitor de recursos

Monitor visual de CPU, memoria, disco y red.

| Comando | Descripción |
|---------|-------------|
| `btop` | Iniciar |
| `btop --utf-force` | Forzar caracteres UTF-8 |

Teclas dentro de btop:
- `q` — salir
- `f` — filtrar procesos
- `k` — matar proceso seleccionado
- `m` — cambiar modo de memoria
- `←/→` — cambiar entre paneles

---
EOF
            ;;
            ranger)
                cat >> "$output" << 'EOF'
## ranger — Gestor de archivos en terminal

Navegador de archivos con vista de tres paneles estilo vim.

| Comando | Descripción |
|---------|-------------|
| `ranger` | Iniciar |

Navegación:
- `h/j/k/l` o flechas — moverse
- `Enter` — abrir archivo/directorio
- `q` — salir

Operaciones:
- `yy` — copiar, `dd` — cortar, `pp` — pegar
- `dD` — eliminar
- `cw` — renombrar
- `zh` — mostrar/ocultar archivos ocultos
- `/` — buscar

---
EOF
            ;;
            fzf)
                cat >> "$output" << 'EOF'
## fzf — Buscador difuso interactivo

| Atajo | Descripción |
|-------|-------------|
| `Ctrl + R` | Búsqueda difusa en historial de comandos |
| `Ctrl + T` | Búsqueda difusa de archivos en directorio actual |
| `Alt + C` | Saltar a directorio con búsqueda difusa |

Uso en comandos:
- `vim $(fzf)` — abrir archivo seleccionado con vim
- `kill -9 $(ps aux | fzf | awk '{print $2}')` — matar proceso interactivamente

---
EOF
            ;;
            Docker)
                cat >> "$output" << 'EOF'
## Docker — Contenedores

| Comando | Descripción |
|---------|-------------|
| `docker ps` | Contenedores en ejecución |
| `docker ps -a` | Todos los contenedores |
| `docker images` | Imágenes locales |
| `docker run -it <imagen>` | Ejecutar contenedor interactivo |
| `docker build -t <nombre> .` | Construir imagen |
| `docker compose up -d` | Levantar servicios en background |
| `docker compose down` | Detener servicios |
| `docker logs <id>` | Ver logs de contenedor |
| `docker exec -it <id> bash` | Entrar a contenedor en ejecución |

> En Linux: añade tu usuario al grupo `docker` (`sudo usermod -aG docker $USER`) y reinicia sesión para usarlo sin sudo.

---
EOF
            ;;
            kubectl)
                cat >> "$output" << 'EOF'
## kubectl — Kubernetes CLI

| Comando | Descripción |
|---------|-------------|
| `kubectl get pods` | Listar pods |
| `kubectl get pods -n <namespace>` | Pods en namespace específico |
| `kubectl describe pod <nombre>` | Detalles de un pod |
| `kubectl logs <pod>` | Ver logs |
| `kubectl apply -f <archivo.yaml>` | Aplicar configuración |
| `kubectl delete -f <archivo.yaml>` | Eliminar recursos |
| `kubectl exec -it <pod> -- bash` | Entrar a pod |
| `kubectl port-forward <pod> 8080:80` | Redirigir puerto |

---
EOF
            ;;
        esac
    done

    # Sección de ~/.zshrc siempre incluida
    cat >> "$output" << 'EOF'
## ~/.zshrc — Referencia rápida

| Acción | Comando |
|--------|---------|
| Recargar configuración | `source ~/.zshrc` |
| Editar configuración | `nano ~/.zshrc` o `code ~/.zshrc` |
| Ver aliases definidos | `alias` |
| Ver PATH actual | `echo $PATH` |

EOF

    echo "${GREEN}Cheatsheet guardado en: $output${NC}"
}

# Preguntar si generar cheatsheet
ask_cheatsheet() {
    local apps=("$@")
    echo
    echo "${YELLOW}¿Generar un cheatsheet con los comandos y aliases de las herramientas instaladas? [Y/n]: ${NC}"
    read -r gen_cheatsheet
    if [[ "$gen_cheatsheet" != "n" && "$gen_cheatsheet" != "N" ]]; then
        generate_cheatsheet "${apps[@]}"
    fi
}

# Recargar la shell para aplicar cambios
restart_terminal() {
    echo "${YELLOW}¿Recargar zsh ahora para aplicar los cambios? [Y/n]: ${NC}"
    read -r restart
    if [[ "$restart" != "n" && "$restart" != "N" ]]; then
        echo "${CYAN}Iniciando una nueva sesión de zsh en esta terminal...${NC}"
        echo "${CYAN}Si no hay config de p10k, se abrirá el asistente automáticamente.${NC}"
        exec zsh -l
    else
        echo "${YELLOW}Abre una nueva pestaña/ventana o ejecuta 'exec zsh' para aplicar los cambios.${NC}"
        echo "${YELLOW}Para estilizar el prompt cuando quieras: 'p10k configure'.${NC}"
    fi
}

# Eliminar la configuración añadida por el script
clean_zshrc() {
    resolve_user_zshrc
    # 1) Quitar el bloque gestionado del .zshrc real
    remove_managed_block "$USER_ZSHRC"
    # 2) Limpiar líneas heredadas/sueltas de versiones anteriores del script,
    #    en todas las ubicaciones posibles ($HOME y el dir de $ZDOTDIR).
    local f
    for f in "$USER_ZSHRC" "${ZDOTDIR:-$HOME}/.zshrc" "$HOME/.zshrc"; do
        [ -f "$f" ] || continue
        sed -i '/# Enable Powerlevel10k instant prompt/,/^fi$/d' "$f"
        sed -i '/# Añadido por setup_linux\.sh/d' "$f"
        sed -i '/^export ZSH=/d' "$f"
        sed -i '/^ZSH_THEME=/d' "$f"
        sed -i '/^plugins=/d' "$f"
        sed -i '/^source .*oh-my-zsh\.sh/d' "$f"
        sed -i '/\.p10k\.zsh/d' "$f"
    done
    echo "${GREEN}.zshrc limpiado (bloque gestionado y líneas heredadas).${NC}"
}

# Eliminar las entradas de GitHub en ~/.ssh/config
clean_ssh_config() {
    local ssh_config="$HOME/.ssh/config"
    [ ! -f "$ssh_config" ] && return
    # Elimina bloques "Host github.com" y cualquier "Host github-*" (5 líneas:
    # Host / HostName / User / IdentityFile / IdentitiesOnly).
    sed -i '/^Host github\.com$/{N;N;N;N;d;}' "$ssh_config"
    sed -i '/^Host github-/{N;N;N;N;d;}' "$ssh_config"
    echo "${GREEN}Entradas de GitHub eliminadas de ~/.ssh/config.${NC}"
}

# Desinstalar configuración
uninstall() {
    echo "${CYAN}Modo de desinstalación${NC}"
    echo

    echo "${YELLOW}¿Desinstalar Oh My Zsh, Powerlevel10k y plugins? [Y/n]: ${NC}"
    read -r remove_omz
    if [[ "$remove_omz" != "n" && "$remove_omz" != "N" ]]; then
        resolve_user_zshrc
        run_command "rm -rf $HOME/.oh-my-zsh" "Eliminando directorio Oh My Zsh"
        # La config de p10k puede estar en $HOME o en el dir de $ZDOTDIR (Terax)
        run_command "rm -f \"$HOME/.p10k.zsh\" \"${ZDOTDIR:-$HOME}/.p10k.zsh\"" "Eliminando configuración de Powerlevel10k"
        run_command "rm -rf $HOME/.cache/p10k-* $HOME/.cache/gitstatus" "Eliminando caché de Powerlevel10k"
        run_command "rm -f \"${ZDOTDIR:-$HOME}/.zshrc.pre-oh-my-zsh\"* \"$HOME/.zshrc.pre-oh-my-zsh\"*" "Eliminando backups de .zshrc"
        # OMZ residual que el instalador pudo dejar en \$ZDOTDIR/ohmyzsh
        if [ -n "$ZDOTDIR" ] && [ -d "$ZDOTDIR/ohmyzsh" ]; then
            run_command "rm -rf \"$ZDOTDIR/ohmyzsh\"" "Eliminando OMZ residual en \$ZDOTDIR"
        fi
        # Limpiar el .zshrc: bloque gestionado + líneas heredadas
        clean_zshrc
        echo "${GREEN}Oh My Zsh y Powerlevel10k eliminados completamente.${NC}"
    fi

    echo "${YELLOW}¿Eliminar las claves SSH generadas por el script (~/.ssh/id_ed25519*)? [y/N]: ${NC}"
    read -r remove_ssh
    if [[ "$remove_ssh" == "y" || "$remove_ssh" == "Y" ]]; then
        run_command "rm -f $HOME/.ssh/id_ed25519 $HOME/.ssh/id_ed25519.pub $HOME/.ssh/id_ed25519_*" "Eliminando claves SSH"
        clean_ssh_config
        echo "${GREEN}Claves SSH eliminadas.${NC}"
    fi

    echo "${YELLOW}¿Eliminar el cheatsheet generado? [Y/n]: ${NC}"
    read -r remove_cheatsheet
    if [[ "$remove_cheatsheet" != "n" && "$remove_cheatsheet" != "N" ]]; then
        run_command "rm -f $HOME/cheatsheet_linux_setup.md" "Eliminando cheatsheet"
    fi

    echo "${YELLOW}¿Desinstalar aplicaciones instaladas por este script? [Y/n]: ${NC}"
    read -r remove_apps
    if [[ "$remove_apps" != "n" && "$remove_apps" != "N" ]]; then
        select_apps
        if [ ${#selected_apps[@]} -gt 0 ]; then
            for app in "${selected_apps[@]}"; do
                IFS='|' read -r name field flatpak_id _ _ <<< "$app"
                if [ -n "$field" ] && [[ "$field" != @* ]]; then
                    run_command "$PKG_REMOVE $field" "Desinstalando $name" || \
                        echo "${YELLOW}No se pudo desinstalar $name.${NC}"
                elif [ -z "$field" ] && [ -n "$flatpak_id" ]; then
                    run_command "flatpak uninstall -y $flatpak_id" "Desinstalando $name" || \
                        echo "${YELLOW}No se pudo desinstalar $name.${NC}"
                else
                    echo "${YELLOW}$name se instaló con un instalador propio; elimínalo manualmente.${NC}"
                fi
            done
        fi
    fi

    echo
    echo "${GREEN}Desinstalación completada.${NC}"
}

# Función principal
main() {
    detect_distro
    resolve_user_zshrc
    echo "${CYAN}Script de Configuración para Linux (${DISTRO})${NC}"
    echo
    echo "${CYAN}¿Qué deseas hacer?${NC}"
    echo "${CYAN}[1] Instalar y configurar${NC}"
    echo "${CYAN}[2] Desinstalar${NC}"
    echo -n "${YELLOW}Elige una opción (1/2): ${NC}"
    read -r mode

    case "$mode" in
        2)
            uninstall
            ;;
        *)
            bootstrap_base
            install_oh_my_zsh
            configure_git_global
            configure_ssh_key
            select_apps
            install_apps "${selected_apps[@]}"
            ask_cheatsheet "${selected_apps[@]}"
            echo
            echo "${GREEN}¡Configuración completada! Los cambios en la terminal requieren reiniciar.${NC}"
            restart_terminal
            ;;
    esac
}

# Ejecutar main solo si el script se EJECUTA directamente con bash
# (p. ej. `bash setup_linux.sh` o `bash <(curl ...)`), no al hacer `source`.
# Bajo zsh o al importarse desde un test, BASH_SOURCE[0] != $0 (o está vacío),
# así que main NO se lanza y se pueden usar las funciones de forma aislada.
if [ -n "${BASH_SOURCE:-}" ] && [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main
fi
