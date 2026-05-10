#!/usr/bin/env bash
#
# Test rápido (sin red) de resolve_user_zshrc en setup_macos.sh.
#
# Verifica que, sea cual sea la terminal, la configuración se escriba en el
# .zshrc que la shell carga de verdad — y no en un directorio efímero que la
# terminal regenera (Terax, VS Code/Cursor/Trae) ni ignorando un $ZDOTDIR que
# el usuario eligió a propósito.
#
# Uso:  bash apps/tests/test_terminal_detection.sh
# Exit: 0 si todo pasa, 1 si algo falla.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP="$SCRIPT_DIR/../setup_macos.sh"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; CYAN=$'\033[1;36m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'
passed=0; failed=0
THOME="/tmp/zshrc-detect-home"   # HOME simulado y determinista

# Corre resolve_user_zshrc en un entorno limpio con las vars dadas e imprime
# "<USER_ZSHRC>|<TERAX_DETECTED>".
resolve_in_env() {
    env -i HOME="$THOME" PATH="$PATH" "$@" bash -c '
        source "'"$SETUP"'" >/dev/null 2>&1
        resolve_user_zshrc
        printf "%s|%s\n" "$USER_ZSHRC" "$TERAX_DETECTED"
    '
}

# check "<descripción>" "<ruta esperada>" [VAR=VAL ...]
check() {
    local desc="$1" expected="$2"; shift 2
    local got path
    got="$(resolve_in_env "$@")"
    path="${got%%|*}"
    if [ "$path" = "$expected" ]; then
        printf "%s✓ %s%s %s→ %s%s\n" "$GREEN" "$desc" "$NC" "$YELLOW" "$path" "$NC"
        ((passed++))
    else
        printf "%s✗ %s%s\n" "$RED" "$desc" "$NC"
        printf "    esperado: %s\n" "$expected"
        printf "    obtenido: %s\n" "$path"
        ((failed++))
    fi
}

printf "%s=== Test: resolución de .zshrc por terminal ===%s\n" "$CYAN" "$NC"
printf "%s(HOME simulado = %s)%s\n\n" "$CYAN" "$THOME" "$NC"

# --- Clase A: terminales que NO tocan $ZDOTDIR -> ~/.zshrc ---
check "Terminal.app / iTerm2 / Ghostty (sin ZDOTDIR)" "$THOME/.zshrc"
check "Warp (sin ZDOTDIR)"                             "$THOME/.zshrc" TERM_PROGRAM=WarpTerminal

# --- Clase B: wrappers que redirigen $ZDOTDIR a un dir efímero ---
check "Terax"                              "$THOME/.zshrc" \
    TERAX_TERMINAL=1 ZDOTDIR="$THOME/.cache/terax/shell-integration/zsh"
check "Terax con TERAX_USER_ZDOTDIR custom" "$THOME/.config/zsh/.zshrc" \
    TERAX_TERMINAL=1 ZDOTDIR="$THOME/.cache/terax/x" TERAX_USER_ZDOTDIR="$THOME/.config/zsh"
check "VS Code (USER_ZDOTDIR + temp ZDOTDIR)" "$THOME/.zshrc" \
    TERM_PROGRAM=vscode VSCODE_INJECTION=1 ZDOTDIR=/tmp/vscode-zsh USER_ZDOTDIR="$THOME"
check "VS Code (solo TERM_PROGRAM)"          "$THOME/.zshrc" \
    TERM_PROGRAM=vscode ZDOTDIR=/tmp/vscode-zsh
check "Cursor"                              "$THOME/.zshrc" \
    TERM_PROGRAM=cursor ZDOTDIR=/tmp/cursor-zsh USER_ZDOTDIR="$THOME"
check "Trae"                                "$THOME/.zshrc" \
    TERM_PROGRAM=trae ZDOTDIR=/tmp/trae-zsh USER_ZDOTDIR="$THOME"
check "VS Code con USER_ZDOTDIR custom"     "$THOME/.config/zsh/.zshrc" \
    TERM_PROGRAM=vscode ZDOTDIR=/tmp/vscode-zsh USER_ZDOTDIR="$THOME/.config/zsh"

# --- $ZDOTDIR deliberado del usuario: hay que respetarlo ---
check "ZDOTDIR propio del usuario (deliberado)" "$THOME/.config/zsh/.zshrc" \
    ZDOTDIR="$THOME/.config/zsh"

printf "\n%s--- Resultado ---%s\n" "$CYAN" "$NC"
printf "%sPasaron: %s%s\n" "$GREEN" "$passed" "$NC"
printf "%sFallaron: %s%s\n" "$RED" "$failed" "$NC"
if [ "$failed" -eq 0 ]; then
    printf "%sTodo correcto.%s\n" "$GREEN" "$NC"; exit 0
else
    printf "%sHay fallos en la detección de terminal.%s\n" "$RED" "$NC"; exit 1
fi
