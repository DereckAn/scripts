#!/usr/bin/env bash
#
# Test AISLADO del flujo SSH multi-cuenta de setup_macos.sh.
#
# Mockea gh / ssh-keygen / ssh-add / ssh-agent / ssh para no tocar tu sistema,
# tu cuenta de GitHub ni la red. Verifica que el bucle configure_ssh_key:
#   - crea una clave por cuenta y un bloque Host por cuenta en ~/.ssh/config,
#   - usa coincidencia anclada (no duplica bloques al re-ejecutar),
#   - llama a `gh ssh-key add` una vez por cuenta,
#   - y que clean_ssh_config elimina todos los bloques github sin tocar otros.
#
# Uso:  bash apps/tests/test_ssh_multiaccount.sh
# Exit: 0 si todo pasa.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP="$SCRIPT_DIR/../setup_macos.sh"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; CYAN=$'\033[1;36m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'
passed=0; failed=0
ok() { if [ "$1" -eq 0 ]; then printf "%s✓ %s%s\n" "$GREEN" "$2" "$NC"; ((passed++)); else printf "%s✗ %s%s\n" "$RED" "$2" "$NC"; ((failed++)); fi; }

SANDBOX="$(mktemp -d /tmp/ssh-mac.XXXXXX)"
trap 'rm -rf "$SANDBOX"' EXIT
export HOME="$SANDBOX"
mkdir -p "$SANDBOX/bin"
export GH_LOG="$SANDBOX/gh_calls.log"; : > "$GH_LOG"

# --- mocks -----------------------------------------------------------------
cat > "$SANDBOX/bin/gh" <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
  "auth status") echo "github.com"; echo "  - Token scopes: 'admin:public_key', 'repo', 'read:org'"; exit 0 ;;
  "api user")    echo "testuser"; exit 0 ;;
  "auth login")  exit 0 ;;
  "auth switch") exit 0 ;;
  "auth refresh") exit 0 ;;
  "ssh-key add") echo "ssh-key add $*" >> "$GH_LOG"; echo "✓ Public key added"; exit 0 ;;
  *) exit 0 ;;
esac
EOF
cat > "$SANDBOX/bin/ssh-keygen" <<'EOF'
#!/usr/bin/env bash
f=""
while [ $# -gt 0 ]; do [ "$1" = "-f" ] && f="$2"; shift; done
[ -n "$f" ] && { echo "PRIVATE" > "$f"; echo "ssh-ed25519 AAAAFAKE test" > "$f.pub"; }
exit 0
EOF
printf '#!/usr/bin/env bash\necho ":"\nexit 0\n'                       > "$SANDBOX/bin/ssh-agent"
printf '#!/usr/bin/env bash\nexit 0\n'                                 > "$SANDBOX/bin/ssh-add"
printf '#!/usr/bin/env bash\necho "Hi testuser! You'\''ve successfully authenticated" 1>&2\nexit 1\n' > "$SANDBOX/bin/ssh"
chmod +x "$SANDBOX"/bin/*
export PATH="$SANDBOX/bin:$PATH"

# Importar funciones (main no se ejecuta al hacer source bajo bash)
source "$SETUP"

CFG="$HOME/.ssh/config"

printf "%s=== Test: SSH multi-cuenta (gh/ssh mockeados) ===%s\n" "$CYAN" "$NC"
printf "%sHOME=%s%s\n\n" "$CYAN" "$SANDBOX" "$NC"

# --- ejecutar el bucle con 3 cuentas: personal, trabajo, "Client X" --------
# trabajo se configura como GitHub Enterprise (host github.empresa.com)
configure_ssh_key >/dev/null 2>&1 <<'INPUT'
Y
me@example.com
1
y
y
trabajo
2
github.empresa.com
work@example.com
1
y
y
Client X
1
client@example.com
1
y
n
INPUT

# --- asserts: bloques Host (coincidencia anclada y exacta) ------------------
[ "$(grep -cE '^Host github\.com$'      "$CFG")" = "1" ]; ok $? "Host github.com presente (cuenta personal)"
[ "$(grep -cE '^Host github-trabajo$'   "$CFG")" = "1" ]; ok $? "Host github-trabajo presente"
[ "$(grep -cE '^Host github-client-x$'  "$CFG")" = "1" ]; ok $? "Host github-client-x presente (slug de 'Client X')"
[ "$(grep -cE '^Host \*$'               "$CFG")" = "1" ]; ok $? "Bloque 'Host *' (llavero) presente una sola vez"

# --- asserts: IdentityFile por cuenta --------------------------------------
grep -q "IdentityFile $HOME/.ssh/id_ed25519$"          "$CFG"; ok $? "IdentityFile personal correcto"
grep -q "IdentityFile $HOME/.ssh/id_ed25519_trabajo$"  "$CFG"; ok $? "IdentityFile trabajo correcto"
grep -q "IdentityFile $HOME/.ssh/id_ed25519_client-x$" "$CFG"; ok $? "IdentityFile client-x correcto"

# --- asserts: HostName por cuenta (Enterprise vs github.com) ---------------
grep -A1 '^Host github\.com$'      "$CFG" | grep -q 'HostName github.com';        ok $? "personal -> HostName github.com"
grep -A1 '^Host github-trabajo$'   "$CFG" | grep -q 'HostName github.empresa.com'; ok $? "trabajo (Enterprise) -> HostName github.empresa.com"
grep -A1 '^Host github-client-x$'  "$CFG" | grep -q 'HostName github.com';        ok $? "client-x -> HostName github.com"

# --- asserts: claves generadas ---------------------------------------------
[ -f "$HOME/.ssh/id_ed25519" ] && [ -f "$HOME/.ssh/id_ed25519.pub" ];               ok $? "Clave personal creada"
[ -f "$HOME/.ssh/id_ed25519_trabajo.pub" ];                                          ok $? "Clave trabajo creada"
[ -f "$HOME/.ssh/id_ed25519_client-x.pub" ];                                         ok $? "Clave client-x creada"

# --- asserts: gh ssh-key add llamado una vez por cuenta (3) ----------------
[ "$(wc -l < "$GH_LOG" | tr -d ' ')" = "3" ];  ok $? "gh ssh-key add llamado 3 veces (una por cuenta)"

# --- idempotencia: re-configurar la cuenta personal no duplica el Host -----
setup_github_account "personal" "$HOME/.ssh/id_ed25519" "github.com" >/dev/null 2>&1 <<'INPUT'
n
1
y
INPUT
[ "$(grep -cE '^Host github\.com$' "$CFG")" = "1" ]; ok $? "Idempotente: Host github.com sigue una sola vez"

# --- clean_ssh_config: elimina github.* pero conserva lo demás -------------
printf '\nHost miservidor\n    HostName 10.0.0.1\n    User dev\n' >> "$CFG"
clean_ssh_config >/dev/null 2>&1
[ "$(grep -c '^Host github' "$CFG")" = "0" ]; ok $? "Uninstall: sin bloques Host github*"
grep -q '^Host \*$'        "$CFG"; ok $? "Uninstall: conserva 'Host *'"
grep -q '^Host miservidor$' "$CFG"; ok $? "Uninstall: conserva el Host propio del usuario"

printf "\n%s--- Resultado ---%s\n" "$CYAN" "$NC"
printf "%sPasaron: %s%s\n" "$GREEN" "$passed" "$NC"
printf "%sFallaron: %s%s\n" "$RED" "$failed" "$NC"
[ "$failed" -eq 0 ] && { printf "%sTodo correcto.%s\n" "$GREEN" "$NC"; exit 0; } || { printf "%sHay fallos.%s\n" "$RED" "$NC"; exit 1; }
