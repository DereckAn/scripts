#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[1;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

passed=0
failed=0

assert() {
    local condition="$1"
    local description="$2"
    local location="$3"
    if eval "$condition" >/dev/null 2>&1; then
        if [ -n "$location" ]; then
            echo "${GREEN}✓ $description${NC} ${YELLOW}→ $location${NC}"
        else
            echo "${GREEN}✓ $description${NC}"
        fi
        ((passed++))
    else
        echo "${RED}✗ $description${NC}"
        ((failed++))
    fi
}

echo "${CYAN}=== Smoke Test — macOS Setup ===${NC}"
echo

echo "${CYAN}--- Herramientas base ---${NC}"
assert "command -v brew"  "Homebrew instalado"  "$(command -v brew 2>/dev/null)"
assert "command -v git"   "Git instalado"        "$(command -v git 2>/dev/null)"

echo
echo "${CYAN}--- Oh My Zsh ---${NC}"
assert "[ -d $HOME/.oh-my-zsh ]"                                    "Oh My Zsh instalado"                   "$HOME/.oh-my-zsh"
assert "[ -d $HOME/.oh-my-zsh/custom/themes/powerlevel10k ]"        "Powerlevel10k instalado"               "$HOME/.oh-my-zsh/custom/themes/powerlevel10k"
assert "grep -q 'powerlevel10k/powerlevel10k' $HOME/.zshrc"         "Powerlevel10k configurado en .zshrc"   "$HOME/.zshrc"
assert "[ -d $HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions ]"          "Plugin zsh-autosuggestions instalado"          "$HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions"
assert "[ -d $HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting ]"      "Plugin zsh-syntax-highlighting instalado"      "$HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting"
assert "[ -d $HOME/.oh-my-zsh/custom/plugins/zsh-history-substring-search ]" "Plugin zsh-history-substring-search instalado" "$HOME/.oh-my-zsh/custom/plugins/zsh-history-substring-search"
assert "grep -q 'zsh-autosuggestions' $HOME/.zshrc"                 "Plugins configurados en .zshrc"        "$HOME/.zshrc"

echo
echo "${CYAN}--- Git ---${NC}"
git_name=$(git config --global user.name 2>/dev/null)
git_email=$(git config --global user.email 2>/dev/null)
assert "git config --global user.name | grep -q '.'"   "Git user.name configurado"   "${git_name}"
assert "git config --global user.email | grep -q '.'"  "Git user.email configurado"  "${git_email}"

echo
echo "${CYAN}--- SSH ---${NC}"
assert "[ -f $HOME/.ssh/id_ed25519 ]"                       "Clave SSH privada existe"              "$HOME/.ssh/id_ed25519"
assert "[ -f $HOME/.ssh/id_ed25519.pub ]"                   "Clave SSH pública existe"              "$HOME/.ssh/id_ed25519.pub"
assert "grep -q 'Host github.com' $HOME/.ssh/config"        "Config SSH para GitHub existe"         "$HOME/.ssh/config"
assert "[ \$(stat -f '%A' $HOME/.ssh/config) = '600' ]"     "Permisos correctos en ~/.ssh/config"   "$(stat -f '%A' $HOME/.ssh/config 2>/dev/null)"

echo
echo "${CYAN}--- Resultado ---${NC}"
echo "${GREEN}Pasaron: $passed${NC}"
echo "${RED}Fallaron: $failed${NC}"

if [ "$failed" -eq 0 ]; then
    echo "${GREEN}Todo correcto.${NC}"
else
    echo "${RED}Algunos checks fallaron. Revisa los items marcados con ✗.${NC}"
fi
