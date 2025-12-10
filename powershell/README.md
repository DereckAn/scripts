# 🎨 Oh My Posh - Instalador Automático para PowerShell

Este script automatiza la instalación y configuración de Oh My Posh en PowerShell, incluyendo fuentes, temas y módulos útiles.

## ⚡ Instalación Rápida

### Opción 1: Instalación Interactiva (Recomendada)

Copia y pega este comando en PowerShell:

```powershell
irm https://raw.githubusercontent.com/DereckAn/scripts/main/powershell/install-oh-my-posh.ps1 | iex
```

### Opción 2: Instalación Rápida (Sin Preguntas)

Con tema `montys` y fuente `FiraCode` por defecto:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/DereckAn/scripts/main/powershell/install-oh-my-posh.ps1))) -Quick
```

### Opción 3: Instalación Personalizada

Especifica tu tema y fuente preferidos:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/DereckAn/scripts/main/powershell/install-oh-my-posh.ps1))) -Quick -Theme "dracula" -Font "CascadiaCode"
```

## 📦 ¿Qué Incluye?

### Oh My Posh

- Prompts hermosos y personalizables
- Información de Git en tiempo real
- Indicadores de duración de comandos
- Temas variados

### Fuentes Nerd Font Disponibles

| Fuente          | Descripción                              |
| --------------- | ---------------------------------------- |
| `FiraCode`      | Popular para programación, con ligaduras |
| `CascadiaCode`  | De Microsoft, muy legible                |
| `JetBrainsMono` | Moderna y clara                          |
| `Hack`          | Clásica y limpia                         |
| `SourceCodePro` | De Adobe                                 |
| `Meslo`         | Basada en Menlo de Apple                 |

### Módulos Instalados

| Módulo             | Descripción                                   |
| ------------------ | --------------------------------------------- |
| **PSReadLine**     | Autocompletado predictivo basado en historial |
| **Terminal-Icons** | Iconos para archivos y carpetas en `ls`       |
| **z**              | Navegación rápida entre directorios visitados |
| **posh-git**       | Integración con Git (branch, status, etc.)    |

## 🎭 Temas Disponibles

El script ofrece selección interactiva de temas populares:

| Tema                    | Estilo                       |
| ----------------------- | ---------------------------- |
| `montys`                | Minimalista y limpio         |
| `agnoster`              | Clásico y popular            |
| `paradox`               | Moderno con información Git  |
| `dracula`               | Tema oscuro elegante         |
| `catppuccin`            | Paleta de colores suave      |
| `tokyo`                 | Inspirado en Tokyo Night     |
| `night-owl`             | Para amantes del modo oscuro |
| `atomic`                | Colorido y llamativo         |
| `powerlevel10k_rainbow` | Estilo Powerlevel10k         |

Ver todos los temas: https://ohmyposh.dev/docs/themes

## ⌨️ Atajos de Teclado Configurados

| Atajo     | Acción                       |
| --------- | ---------------------------- |
| `Tab`     | Menú de autocompletado       |
| `↑` / `↓` | Navegar historial (búsqueda) |
| `Ctrl+D`  | Eliminar carácter            |

## 🛠️ Aliases y Funciones Incluidas

```powershell
# Aliases
g       # git
ll      # Get-ChildItem (ls detallado)
touch   # New-Item
vim     # nvim (si está instalado)

# Funciones
which <comando>  # Encuentra la ubicación de un comando
mkcd <carpeta>   # Crea y entra a una carpeta
reload           # Recarga el perfil de PowerShell
```

## 📝 Pasos Post-Instalación

### 1. Cambiar la Fuente de la Terminal

#### Windows Terminal

1. Abre Windows Terminal
2. Ve a `Configuración` (Ctrl+,)
3. Selecciona tu perfil de PowerShell
4. Ve a `Apariencia` → `Fuente`
5. Selecciona `FiraCode Nerd Font` o la fuente que instalaste

#### VS Code

1. Abre Configuración (Ctrl+,)
2. Busca `Terminal Font Family`
3. Escribe: `FiraCode Nerd Font, Consolas, monospace`

#### PowerShell ISE

1. Ve a `Herramientas` → `Opciones`
2. En `Apariencia`, cambia la fuente

### 2. Reiniciar la Terminal

Cierra y abre la terminal para ver los cambios.

## 🔧 Configuración Manual

Si prefieres hacer la instalación paso a paso:

### 1. Instalar Oh My Posh

```powershell
winget install JanDeDobbeleer.OhMyPosh --source winget
```

### 2. Instalar Fuente

```powershell
oh-my-posh font install FiraCode
```

### 3. Crear/Editar Perfil

```powershell
# Ver ubicación del perfil
$PROFILE

# Crear si no existe
if (!(Test-Path -Path $PROFILE)) {
    New-Item -Path $PROFILE -Type File -Force
}

# Editar
notepad $PROFILE
```

### 4. Agregar al Perfil

```powershell
oh-my-posh init pwsh --config ~/montys.omp.json | Invoke-Expression
```

### 5. Instalar Módulos

```powershell
Install-Module -Name PSReadLine -Scope CurrentUser -Force
Install-Module -Name Terminal-Icons -Scope CurrentUser -Force
Install-Module -Name z -Scope CurrentUser -Force
Install-Module -Name posh-git -Scope CurrentUser -Force
```

## 🐛 Solución de Problemas

### "El archivo de perfil no existe"

```powershell
New-Item -Path $PROFILE -Type File -Force
```

### "Caracteres extraños en lugar de iconos"

La fuente Nerd Font no está configurada en la terminal. Sigue los pasos de post-instalación.

### "oh-my-posh no reconocido"

Reinicia la terminal o actualiza el PATH:

```powershell
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
```

### "Error al ejecutar scripts"

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 📚 Recursos

- [Oh My Posh Documentation](https://ohmyposh.dev/)
- [Nerd Fonts](https://www.nerdfonts.com/)
- [Windows Terminal](https://aka.ms/terminal)
- [PSReadLine Documentation](https://docs.microsoft.com/en-us/powershell/module/psreadline/)

## 📄 Licencia

MIT License - Usa, modifica y comparte libremente.

---

_Creado con ❤️ por DereckAn_
