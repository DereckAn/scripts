#!/bin/bash
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No color

echo "${YELLOW}Descargando el script de configuración para macOS...${NC}"
curl -fsSL https://github.com/DereckAn/scripts/releases/latest/download/setup_macos -o setup_macos
if [ $? -ne 0 ]; then
    echo "${RED}Error descargando el binario.${NC}"
    exit 1
fi

echo "${YELLOW}Haciendo el binario ejecutable...${NC}"
chmod +x setup_macos

echo "${YELLOW}Ejecutando el script...${NC}"
./setup_macos
if [ $? -ne 0 ]; then
    echo "${RED}Error ejecutando el script.${NC}"
    exit 1
fi

echo "${YELLOW}Limpiando...${NC}"
rm setup_macos
echo "${GREEN}¡Ejecución completada!${NC}"