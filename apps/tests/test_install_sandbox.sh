#!/usr/bin/env bash
#
# Test end-to-end AISLADO de setup_macos.sh (requiere red).
#
# Crea un $HOME sandbox simulando una terminal concreta, ejecuta la lógica real
# de instalación de Oh My Zsh + Powerlevel10k, y verifica que todo queda en el
# sitio correcto y funcionando. NO toca tu sistema real.
#
# Uso:   bash apps/tests/test_install_sandbox.sh [terax|vscode|plain]
#        (escenario por defecto: terax)
# Exit:  0 si todo pasa, 1 si algo falla.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP="$SCRIPT_DIR/../setup_macos.sh"
SCENARIO="${1:-terax}"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; CYAN=$'\033[1;36m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'
passed=0; failed=0
ok() {  # ok <exit-status> <descripción>
    if [ "$1" -eq 0 ]; then printf "%s✓ %s%s\n" "$GREEN" "$2" "$NC"; ((passed++))
    else printf "%s✗ %s%s\n" "$RED" "$2" "$NC"; ((failed++)); fi
}

SANDBOX="$(mktemp -d /tmp/omz-e2e.XXXXXX)"
INSTALL_LOG="$SANDBOX/install.log"
trap 'rm -rf "$SANDBOX"' EXIT

export HOME="$SANDBOX"
# Partir de un entorno de terminal limpio
unset ZDOTDIR TERAX_TERMINAL TERAX_USER_ZDOTDIR USER_ZDOTDIR VSCODE_INJECTION

STARTUP_ZDOTDIR="$HOME"   # con qué ZDOTDIR arrancaría zsh en esta terminal
case "$SCENARIO" in
    plain)
        export TERM_PROGRAM="Apple_Terminal"
        ;;
    terax)
        export TERAX_TERMINAL=1
        export ZDOTDIR="$SANDBOX/.cache/terax/shell-integration/zsh"
        mkdir -p "$ZDOTDIR"
        # Integración Terax: delega en el rc real y NO restablece ZDOTDIR
        printf '{ _z="${TERAX_USER_ZDOTDIR:-$HOME}"; [ -f "$_z/.zshrc" ] && source "$_z/.zshrc"; unset _z; }\n:\n' \
            > "$ZDOTDIR/.zshrc"
        STARTUP_ZDOTDIR="$ZDOTDIR"
        ;;
    vscode)
        export TERM_PROGRAM="vscode" VSCODE_INJECTION=1
        export USER_ZDOTDIR="$HOME"
        export ZDOTDIR="$SANDBOX/.vscode-zsh"
        mkdir -p "$ZDOTDIR"
        # Integración VS Code: restablece ZDOTDIR al original y carga el rc real
        printf 'ZDOTDIR="$USER_ZDOTDIR"\n[ -f "$USER_ZDOTDIR/.zshrc" ] && source "$USER_ZDOTDIR/.zshrc"\n' \
            > "$ZDOTDIR/.zshrc"
        STARTUP_ZDOTDIR="$ZDOTDIR"
        ;;
    *)
        echo "Escenario desconocido: $SCENARIO (usa: terax | vscode | plain)"; exit 2 ;;
esac

printf "%s=== E2E install (%s) ===%s\n" "$CYAN" "$SCENARIO" "$NC"
printf "%sHOME=%s%s\n" "$CYAN" "$SANDBOX" "$NC"
printf "%sZDOTDIR=%s  TERM_PROGRAM=%s%s\n\n" "$CYAN" "${ZDOTDIR:-<unset>}" "${TERM_PROGRAM:-<unset>}" "$NC"

# Importar las funciones reales del script (main no se ejecuta al hacer source)
source "$SETUP"

resolve_user_zshrc
printf "%sUSER_ZSHRC resuelto: %s%s\n" "$YELLOW" "$USER_ZSHRC" "$NC"
[ "$USER_ZSHRC" = "${USER_ZDOTDIR:-$HOME}/.zshrc" ]
ok $? "USER_ZSHRC apunta al rc real (no al directorio efímero)"

printf "%sInstalando (clona OMZ + tema + plugins; puede tardar)...%s\n" "$YELLOW" "$NC"
printf 'Y\n' | install_oh_my_zsh >"$INSTALL_LOG" 2>&1

[ -d "$HOME/.oh-my-zsh" ];                                                   ok $? "Oh My Zsh instalado en \$HOME"
[ ! -d "${ZDOTDIR:-/no}/ohmyzsh" ];                                          ok $? "Sin instalación residual en \$ZDOTDIR/ohmyzsh"
[ -d "$HOME/.oh-my-zsh/custom/themes/powerlevel10k" ];                       ok $? "Tema Powerlevel10k clonado"
[ -d "$HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions" ];                ok $? "Plugin zsh-autosuggestions"
[ -d "$HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting" ];            ok $? "Plugin zsh-syntax-highlighting"
[ -d "$HOME/.oh-my-zsh/custom/plugins/zsh-history-substring-search" ];       ok $? "Plugin zsh-history-substring-search"
grep -q 'source "$ZSH/oh-my-zsh.sh"' "$USER_ZSHRC";                          ok $? "El rc hace source de oh-my-zsh.sh"
[ "$(grep -c 'setup_macos.sh (Oh My Zsh' "$USER_ZSHRC")" = "2" ];            ok $? "Bloque gestionado presente (2 marcadores)"

# Idempotencia: una segunda corrida no debe duplicar el bloque
printf 'Y\n' | install_oh_my_zsh >/dev/null 2>&1
[ "$(grep -c 'setup_macos.sh (Oh My Zsh' "$USER_ZSHRC")" = "2" ];            ok $? "Idempotente: siguen 2 marcadores tras 2da corrida"

# Powerlevel10k carga en una zsh INTERACTIVA arrancada como lo haría la terminal
p10k_out="$(ZDOTDIR="$STARTUP_ZDOTDIR" zsh -i 2>/dev/null <<'ZEOF'
(( $+functions[p10k] )) && print P10K_OK
ZEOF
)"
printf '%s' "$p10k_out" | grep -q P10K_OK;                                   ok $? "Powerlevel10k carga en zsh interactivo (asistente disponible)"

# La desinstalación limpia los restos pero preserva líneas propias del usuario
printf '\nexport PATH="$HOME/.local/bin:$PATH"  # linea-usuario\n' >> "$USER_ZSHRC"
clean_zshrc >/dev/null 2>&1
[ "$(grep -cE 'oh-my-zsh\.sh|ZSH_THEME|\.p10k\.zsh|setup_macos\.sh \(Oh My' "$USER_ZSHRC")" = "0" ]
ok $? "Uninstall: sin restos de OMZ/p10k en el rc"
grep -q 'linea-usuario' "$USER_ZSHRC";                                       ok $? "Uninstall: preserva líneas propias del usuario"

printf "\n%s--- Resultado (%s) ---%s\n" "$CYAN" "$SCENARIO" "$NC"
printf "%sPasaron: %s%s\n" "$GREEN" "$passed" "$NC"
printf "%sFallaron: %s%s\n" "$RED" "$failed" "$NC"
if [ "$failed" -ne 0 ]; then
    printf "%sLog de instalación: %s%s\n" "$YELLOW" "$INSTALL_LOG" "$NC"
    cp "$INSTALL_LOG" /tmp/omz-e2e-last-install.log 2>/dev/null
    printf "%s(copiado a /tmp/omz-e2e-last-install.log)%s\n" "$YELLOW" "$NC"
    exit 1
fi
printf "%sTodo correcto.%s\n" "$GREEN" "$NC"
exit 0
