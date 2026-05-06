#!/usr/bin/env bash

echo "========================================"
echo "1) Plain echo with single quotes (wrong)"
echo "========================================"
RED_WRONG='\033[0;31m'
GREEN_WRONG='\033[0;32m'
NC_WRONG='\033[0m'
echo "${RED_WRONG}This should be red but won't be${NC_WRONG}"
echo "${GREEN_WRONG}This should be green but won't be${NC_WRONG}"

echo ""
echo "========================================"
echo "2) echo -e with single quotes"
echo "========================================"
echo -e "${RED_WRONG}This IS red (echo -e)${NC_WRONG}"
echo -e "${GREEN_WRONG}This IS green (echo -e)${NC_WRONG}"

echo ""
echo "========================================"
echo "3) \$'...' syntax with plain echo (bash)"
echo "========================================"
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[1;36m'
BLUE=$'\033[1;34m'
NC=$'\033[0m'
echo "${RED}This IS red (\$'...' syntax)${NC}"
echo "${GREEN}This IS green (\$'...' syntax)${NC}"
echo "${YELLOW}This IS yellow (\$'...' syntax)${NC}"
echo "${CYAN}This IS cyan (\$'...' syntax)${NC}"
echo "${BLUE}This IS blue (\$'...' syntax)${NC}"

echo ""
echo "========================================"
echo "4) printf (always works, most portable)"
echo "========================================"
printf '\033[0;31mThis IS red (printf)\033[0m\n'
printf '\033[0;32mThis IS green (printf)\033[0m\n'
printf '\033[1;33mThis IS yellow (printf)\033[0m\n'
printf '\033[1;36mThis IS cyan (printf)\033[0m\n'
printf '\033[1;34mThis IS blue (printf)\033[0m\n'

echo ""
echo "========================================"
echo "Shell info"
echo "========================================"
echo "Running as: $0"
echo "Shell: $SHELL"
echo "Bash version: $BASH_VERSION"
