#!/usr/bin/env bash
#
# Test AISLADO de la selección de apps de setup_macos.sh.
#
# Reproduce el bug del "freeze": antes, select_apps se capturaba con
# `done < <(select_apps)`, lo que enviaba el menú y los prompts a una tubería
# (el usuario no los veía y `read` se quedaba colgado), y además metía el TEXTO
# del menú dentro de selected_apps.
#
# Ahora select_apps rellena el array global directamente. Este test alimenta
# selecciones por stdin y comprueba que selected_apps contiene SOLO las apps
# elegidas (y ningún texto de menú).
#
# Uso:  bash apps/tests/test_app_selection.sh
# Exit: 0 si todo pasa.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP="$SCRIPT_DIR/../setup_macos.sh"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; CYAN=$'\033[1;36m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'
passed=0; failed=0
ok() { if [ "$1" -eq 0 ]; then printf "%s✓ %s%s\n" "$GREEN" "$2" "$NC"; ((passed++)); else printf "%s✗ %s%s\n" "$RED" "$2" "$NC"; ((failed++)); fi; }

export HOME="$(mktemp -d /tmp/appsel.XXXXXX)"
trap 'rm -rf "$HOME"' EXIT

# Importar funciones (main no corre al hacer source bajo bash)
source "$SETUP"

# Sin caché de brew -> nada aparece como "instalado" (no afecta la selección)
BREW_LIST_CACHE=""; BREW_CASK_LIST_CACHE=""

printf "%s=== Test: selección de apps (sin freeze, array correcto) ===%s\n\n" "$CYAN" "$NC"

# 9 categorías -> 9 líneas de respuesta:
#  Gestores=1,3 (pnpm,Yarn) | Contenedores=n | IDEs=all | Navegadores=0 |
#  Terminales=n | Lenguajes=2 (Java) | BD=n | CLI=1,6 (eza,fzf) | Otros=n
select_apps >/dev/null 2>&1 <<'INPUT'
1,3
n
all
0
n
2
n
1,6
n
INPUT

# Unir el array para inspección
joined=$(printf '%s\n' "${selected_apps[@]}")

[ "${#selected_apps[@]}" = "9" ]; ok $? "selected_apps tiene 9 entradas (2+4+1+2), no basura de menú"

echo "$joined" | grep -q '^pnpm:'                ; ok $? "incluye pnpm (Gestores idx 1)"
echo "$joined" | grep -q '^Yarn:'                ; ok $? "incluye Yarn (Gestores idx 3)"
echo "$joined" | grep -q '^Visual Studio Code:'  ; ok $? "incluye Visual Studio Code (IDEs 'all')"
echo "$joined" | grep -q '^Cursor:'              ; ok $? "incluye Cursor (IDEs 'all')"
echo "$joined" | grep -q '^WebStorm:'            ; ok $? "incluye WebStorm (IDEs 'all')"
echo "$joined" | grep -q '^Java:'                ; ok $? "incluye Java (Lenguajes idx 2)"
echo "$joined" | grep -q '^eza:'                 ; ok $? "incluye eza (CLI idx 1)"
echo "$joined" | grep -q '^fzf:'                 ; ok $? "incluye fzf (CLI idx 6)"

# Negativos: categorías omitidas y NADA de texto de menú capturado
echo "$joined" | grep -q '^Docker:'              && ng=1 || ng=0; [ "$ng" = "0" ]; ok $? "NO incluye Docker (Contenedores omitido con 'n')"
echo "$joined" | grep -qiE 'Selecciona|Categoría|Ingresa los números' && nm=1 || nm=0; [ "$nm" = "0" ]; ok $? "NO captura texto del menú como si fuera app"

# Caso 'all' real: cada entrada debe tener el formato name:cmd:cask:path:exe
bad=0
for e in "${selected_apps[@]}"; do
    IFS=':' read -r n c rest <<< "$e"
    [ -n "$n" ] && [ -n "$c" ] || bad=1
done
[ "$bad" = "0" ]; ok $? "todas las entradas tienen formato name:cmd:... válido"

printf "\n%s--- Resultado ---%s\n" "$CYAN" "$NC"
printf "%sPasaron: %s%s\n" "$GREEN" "$passed" "$NC"
printf "%sFallaron: %s%s\n" "$RED" "$failed" "$NC"
[ "$failed" -eq 0 ] && { printf "%sTodo correcto.%s\n" "$GREEN" "$NC"; exit 0; } || { printf "%sHay fallos.%s\n" "$RED" "$NC"; exit 1; }
