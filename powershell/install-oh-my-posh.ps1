#Requires -Version 5.1
<#
.SYNOPSIS
    Script automatizado para instalar y configurar Oh My Posh en PowerShell.

.DESCRIPTION
    Este script automatiza la instalación de Oh My Posh, fuentes Nerd Fonts,
    temas personalizados y módulos útiles para mejorar tu terminal de PowerShell.

.NOTES
    Autor: DereckAn
    Versión: 1.0.0
    Repositorio: https://github.com/DereckAn/scripts
#>

# Configuración de colores para mensajes
$colors = @{
    Success = "Green"
    Warning = "Yellow"
    Error   = "Red"
    Info    = "Cyan"
    Header  = "Magenta"
}

function Write-ColorMessage {
    param(
        [string]$Message,
        [string]$Color = "White",
        [switch]$NoNewLine
    )
    if ($NoNewLine) {
        Write-Host $Message -ForegroundColor $Color -NoNewline
    } else {
        Write-Host $Message -ForegroundColor $Color
    }
}

function Write-Header {
    param([string]$Title)
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor $colors.Header
    Write-Host "  $Title" -ForegroundColor $colors.Header
    Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor $colors.Header
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host "  ▶ " -ForegroundColor $colors.Info -NoNewline
    Write-Host $Message
}

function Write-Success {
    param([string]$Message)
    Write-Host "  ✓ " -ForegroundColor $colors.Success -NoNewline
    Write-Host $Message -ForegroundColor $colors.Success
}

function Write-Warning {
    param([string]$Message)
    Write-Host "  ⚠ " -ForegroundColor $colors.Warning -NoNewline
    Write-Host $Message -ForegroundColor $colors.Warning
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "  ✗ " -ForegroundColor $colors.Error -NoNewline
    Write-Host $Message -ForegroundColor $colors.Error
}

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-WingetInstalled {
    try {
        $null = Get-Command winget -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Install-OhMyPosh {
    Write-Header "Instalando Oh My Posh"
    
    if (Test-WingetInstalled) {
        Write-Step "Winget detectado. Instalando Oh My Posh..."
        try {
            winget install JanDeDobbeleer.OhMyPosh --source winget --accept-source-agreements --accept-package-agreements
            Write-Success "Oh My Posh instalado correctamente"
            
            # Refrescar PATH
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            return $true
        } catch {
            Write-ErrorMsg "Error al instalar Oh My Posh: $_"
            return $false
        }
    } else {
        Write-Warning "Winget no está instalado. Intentando método alternativo..."
        try {
            Set-ExecutionPolicy Bypass -Scope Process -Force
            Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://ohmyposh.dev/install.ps1'))
            Write-Success "Oh My Posh instalado correctamente (método alternativo)"
            return $true
        } catch {
            Write-ErrorMsg "Error al instalar Oh My Posh: $_"
            return $false
        }
    }
}

function Install-NerdFont {
    param(
        [string]$FontName = "FiraCode"
    )
    
    Write-Header "Instalando Nerd Font: $FontName"
    
    try {
        # Verificar si oh-my-posh está disponible
        $ohMyPoshPath = Get-Command oh-my-posh -ErrorAction SilentlyContinue
        
        if ($ohMyPoshPath) {
            Write-Step "Instalando $FontName Nerd Font usando oh-my-posh..."
            oh-my-posh font install $FontName
            Write-Success "$FontName Nerd Font instalada correctamente"
            Write-Warning "IMPORTANTE: Debes cambiar la fuente en la configuración de tu terminal a '$FontName Nerd Font' o '$FontName Nerd Font Mono'"
            return $true
        } else {
            Write-ErrorMsg "oh-my-posh no encontrado en el PATH. Por favor, reinicia la terminal e intenta de nuevo."
            return $false
        }
    } catch {
        Write-ErrorMsg "Error al instalar la fuente: $_"
        return $false
    }
}

function Get-AvailableThemes {
    Write-Header "Temas Disponibles"
    
    $themesUrl = "https://api.github.com/repos/JanDeDobbeleer/oh-my-posh/contents/themes"
    
    try {
        $themes = Invoke-RestMethod -Uri $themesUrl -Method Get
        $themeNames = $themes | Where-Object { $_.name -like "*.omp.json" } | ForEach-Object { $_.name -replace ".omp.json", "" }
        
        Write-Host "  Temas populares recomendados:" -ForegroundColor $colors.Info
        $popularThemes = @("montys", "agnoster", "paradox", "powerline", "robbyrussell", "dracula", "catppuccin", "tokyo", "night-owl", "atomic")
        
        foreach ($theme in $popularThemes) {
            if ($themeNames -contains $theme) {
                Write-Host "    • $theme" -ForegroundColor White
            }
        }
        
        Write-Host ""
        Write-Host "  Para ver TODOS los temas disponibles, visita:" -ForegroundColor $colors.Info
        Write-Host "  https://ohmyposh.dev/docs/themes" -ForegroundColor $colors.Warning
        
        return $themeNames
    } catch {
        Write-Warning "No se pudieron obtener los temas. Usando lista predeterminada."
        return @("montys", "agnoster", "paradox", "powerline")
    }
}

function Install-Theme {
    param(
        [string]$ThemeName = "montys"
    )
    
    Write-Header "Configurando Tema: $ThemeName"
    
    $profileDir = Split-Path -Parent $PROFILE
    $themePath = Join-Path $profileDir "$ThemeName.omp.json"
    $themeUrl = "https://raw.githubusercontent.com/JanDeDobbeleer/oh-my-posh/main/themes/$ThemeName.omp.json"
    
    try {
        Write-Step "Descargando tema $ThemeName..."
        
        # Crear directorio si no existe
        if (-not (Test-Path $profileDir)) {
            New-Item -Path $profileDir -ItemType Directory -Force | Out-Null
        }
        
        Invoke-WebRequest -Uri $themeUrl -OutFile $themePath
        Write-Success "Tema descargado en: $themePath"
        return $themePath
    } catch {
        Write-ErrorMsg "Error al descargar el tema: $_"
        return $null
    }
}

function Initialize-PowerShellProfile {
    param(
        [string]$ThemePath
    )
    
    Write-Header "Configurando Perfil de PowerShell"
    
    $profileDir = Split-Path -Parent $PROFILE
    
    # Crear directorio del perfil si no existe
    if (-not (Test-Path $profileDir)) {
        Write-Step "Creando directorio del perfil..."
        New-Item -Path $profileDir -ItemType Directory -Force | Out-Null
    }
    
    # Crear archivo de perfil si no existe
    if (-not (Test-Path $PROFILE)) {
        Write-Step "Creando archivo de perfil..."
        New-Item -Path $PROFILE -ItemType File -Force | Out-Null
    }
    
    # Contenido del perfil
    $profileContent = @"
# ═══════════════════════════════════════════════════════════════
# PowerShell Profile - Configurado con Oh My Posh
# Generado automáticamente por install-oh-my-posh.ps1
# ═══════════════════════════════════════════════════════════════

# Inicializar Oh My Posh con tema personalizado
oh-my-posh init pwsh --config "$ThemePath" | Invoke-Expression

# ═══════════════════════════════════════════════════════════════
# MÓDULOS ÚTILES
# ═══════════════════════════════════════════════════════════════

# PSReadLine - Mejoras en la línea de comandos
if (Get-Module -ListAvailable -Name PSReadLine) {
    Import-Module PSReadLine
    
    # Autocompletado predictivo basado en historial
    Set-PSReadLineOption -PredictionSource History
    Set-PSReadLineOption -PredictionViewStyle ListView
    
    # Colores del historial predictivo
    Set-PSReadLineOption -Colors @{
        InlinePrediction = '#6c757d'
    }
    
    # Atajos de teclado útiles
    Set-PSReadLineKeyHandler -Key Tab -Function MenuComplete
    Set-PSReadLineKeyHandler -Key UpArrow -Function HistorySearchBackward
    Set-PSReadLineKeyHandler -Key DownArrow -Function HistorySearchForward
    Set-PSReadLineKeyHandler -Chord 'Ctrl+d' -Function DeleteChar
}

# Terminal-Icons - Iconos para archivos y carpetas
if (Get-Module -ListAvailable -Name Terminal-Icons) {
    Import-Module Terminal-Icons
}

# z - Navegación rápida entre directorios
if (Get-Module -ListAvailable -Name z) {
    Import-Module z
}

# posh-git - Integración con Git
if (Get-Module -ListAvailable -Name posh-git) {
    Import-Module posh-git
}

# ═══════════════════════════════════════════════════════════════
# ALIASES ÚTILES
# ═══════════════════════════════════════════════════════════════

# Git aliases
Set-Alias -Name g -Value git
Set-Alias -Name vim -Value nvim -ErrorAction SilentlyContinue
Set-Alias -Name ll -Value Get-ChildItem
Set-Alias -Name touch -Value New-Item

# Funciones útiles
function which (`$command) {
    Get-Command -Name `$command -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty Path -ErrorAction SilentlyContinue
}

function mkcd (`$path) {
    New-Item -Path `$path -ItemType Directory -Force
    Set-Location `$path
}

function reload {
    . `$PROFILE
    Write-Host "Perfil recargado!" -ForegroundColor Green
}

# ═══════════════════════════════════════════════════════════════
# INFORMACIÓN DEL SISTEMA AL INICIAR
# ═══════════════════════════════════════════════════════════════

# Descomenta las siguientes líneas si quieres ver info al iniciar
# Write-Host "PowerShell `$(`$PSVersionTable.PSVersion)" -ForegroundColor Cyan
# Write-Host "Usuario: `$env:USERNAME @ `$env:COMPUTERNAME" -ForegroundColor DarkGray

"@
    
    try {
        Write-Step "Escribiendo configuración en el perfil..."
        Set-Content -Path $PROFILE -Value $profileContent -Force
        Write-Success "Perfil configurado correctamente"
        Write-Host "  Ubicación: $PROFILE" -ForegroundColor DarkGray
        return $true
    } catch {
        Write-ErrorMsg "Error al configurar el perfil: $_"
        return $false
    }
}

function Install-PowerShellModules {
    Write-Header "Instalando Módulos de PowerShell"
    
    $modules = @(
        @{Name = "PSReadLine"; Description = "Mejoras en autocompletado e historial"},
        @{Name = "Terminal-Icons"; Description = "Iconos para archivos y carpetas"},
        @{Name = "z"; Description = "Navegación rápida entre directorios"},
        @{Name = "posh-git"; Description = "Integración con Git"}
    )
    
    # Configurar TLS 1.2 para descargas
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    
    foreach ($module in $modules) {
        Write-Step "Instalando $($module.Name) - $($module.Description)..."
        
        try {
            if (-not (Get-Module -ListAvailable -Name $module.Name)) {
                Install-Module -Name $module.Name -Scope CurrentUser -Force -AllowClobber -SkipPublisherCheck
                Write-Success "$($module.Name) instalado correctamente"
            } else {
                Write-Warning "$($module.Name) ya está instalado"
            }
        } catch {
            Write-ErrorMsg "Error al instalar $($module.Name): $_"
        }
    }
}

function Show-ThemeSelector {
    Write-Header "Seleccionar Tema"
    
    $themes = @(
        @{Number = 1; Name = "montys"; Description = "Minimalista y limpio"},
        @{Number = 2; Name = "agnoster"; Description = "Clásico y popular"},
        @{Number = 3; Name = "paradox"; Description = "Moderno con información Git"},
        @{Number = 4; Name = "dracula"; Description = "Tema oscuro elegante"},
        @{Number = 5; Name = "catppuccin"; Description = "Paleta de colores suave"},
        @{Number = 6; Name = "tokyo"; Description = "Inspirado en Tokyo Night"},
        @{Number = 7; Name = "night-owl"; Description = "Para amantes del modo oscuro"},
        @{Number = 8; Name = "atomic"; Description = "Colorido y llamativo"},
        @{Number = 9; Name = "powerlevel10k_rainbow"; Description = "Estilo Powerlevel10k"},
        @{Number = 0; Name = "custom"; Description = "Ingresa tu propio tema"}
    )
    
    Write-Host "  Selecciona un tema:" -ForegroundColor $colors.Info
    Write-Host ""
    
    foreach ($theme in $themes) {
        Write-Host "    [$($theme.Number)] " -ForegroundColor $colors.Warning -NoNewline
        Write-Host "$($theme.Name)" -ForegroundColor White -NoNewline
        Write-Host " - $($theme.Description)" -ForegroundColor DarkGray
    }
    
    Write-Host ""
    $selection = Read-Host "  Ingresa el número del tema (Enter para 'montys')"
    
    if ([string]::IsNullOrWhiteSpace($selection)) {
        return "montys"
    }
    
    $selectedTheme = $themes | Where-Object { $_.Number -eq [int]$selection }
    
    if ($selectedTheme) {
        if ($selectedTheme.Name -eq "custom") {
            $customTheme = Read-Host "  Ingresa el nombre del tema"
            return $customTheme
        }
        return $selectedTheme.Name
    }
    
    return "montys"
}

function Show-FontSelector {
    Write-Header "Seleccionar Fuente"
    
    $fonts = @(
        @{Number = 1; Name = "FiraCode"; Description = "Popular para programación"},
        @{Number = 2; Name = "CascadiaCode"; Description = "De Microsoft, muy legible"},
        @{Number = 3; Name = "JetBrainsMono"; Description = "Moderna y clara"},
        @{Number = 4; Name = "Hack"; Description = "Clásica y limpia"},
        @{Number = 5; Name = "SourceCodePro"; Description = "De Adobe"},
        @{Number = 6; Name = "Meslo"; Description = "Basada en Menlo de Apple"}
    )
    
    Write-Host "  Selecciona una fuente Nerd Font:" -ForegroundColor $colors.Info
    Write-Host ""
    
    foreach ($font in $fonts) {
        Write-Host "    [$($font.Number)] " -ForegroundColor $colors.Warning -NoNewline
        Write-Host "$($font.Name)" -ForegroundColor White -NoNewline
        Write-Host " - $($font.Description)" -ForegroundColor DarkGray
    }
    
    Write-Host ""
    $selection = Read-Host "  Ingresa el número de la fuente (Enter para 'FiraCode')"
    
    if ([string]::IsNullOrWhiteSpace($selection)) {
        return "FiraCode"
    }
    
    $selectedFont = $fonts | Where-Object { $_.Number -eq [int]$selection }
    
    if ($selectedFont) {
        return $selectedFont.Name
    }
    
    return "FiraCode"
}

function Show-Summary {
    param(
        [string]$ThemeName,
        [string]$FontName,
        [string]$ThemePath
    )
    
    Write-Header "¡Instalación Completada!"
    
    Write-Host "  Resumen de la instalación:" -ForegroundColor $colors.Info
    Write-Host ""
    Write-Host "    ✓ Oh My Posh instalado" -ForegroundColor $colors.Success
    Write-Host "    ✓ Tema: $ThemeName" -ForegroundColor $colors.Success
    Write-Host "    ✓ Fuente: $FontName Nerd Font" -ForegroundColor $colors.Success
    Write-Host "    ✓ Módulos instalados:" -ForegroundColor $colors.Success
    Write-Host "      • PSReadLine (autocompletado predictivo)" -ForegroundColor White
    Write-Host "      • Terminal-Icons (iconos de archivos)" -ForegroundColor White
    Write-Host "      • z (navegación rápida)" -ForegroundColor White
    Write-Host "      • posh-git (integración Git)" -ForegroundColor White
    Write-Host ""
    Write-Host "  ═══════════════════════════════════════════════════════════" -ForegroundColor $colors.Warning
    Write-Host "  PASOS FINALES IMPORTANTES:" -ForegroundColor $colors.Warning
    Write-Host "  ═══════════════════════════════════════════════════════════" -ForegroundColor $colors.Warning
    Write-Host ""
    Write-Host "  1. Cambia la fuente de tu terminal a:" -ForegroundColor White
    Write-Host "     '$FontName Nerd Font' o '$FontName Nerd Font Mono'" -ForegroundColor $colors.Info
    Write-Host ""
    Write-Host "     • Windows Terminal: Configuración → Perfiles → Apariencia → Fuente" -ForegroundColor DarkGray
    Write-Host "     • VS Code: Configuración → Terminal Font Family" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  2. Reinicia tu terminal para aplicar los cambios" -ForegroundColor White
    Write-Host ""
    Write-Host "  3. Archivos de configuración:" -ForegroundColor White
    Write-Host "     • Perfil: $PROFILE" -ForegroundColor DarkGray
    Write-Host "     • Tema: $ThemePath" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  ═══════════════════════════════════════════════════════════" -ForegroundColor $colors.Header
    Write-Host ""
}

# ═══════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ═══════════════════════════════════════════════════════════════

function Start-Installation {
    Clear-Host
    
    Write-Host ""
    Write-Host "  ╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor $colors.Header
    Write-Host "  ║                                                               ║" -ForegroundColor $colors.Header
    Write-Host "  ║   ✨ Oh My Posh - Instalador Automático para PowerShell ✨    ║" -ForegroundColor $colors.Header
    Write-Host "  ║                                                               ║" -ForegroundColor $colors.Header
    Write-Host "  ║   Este script instalará:                                      ║" -ForegroundColor $colors.Header
    Write-Host "  ║   • Oh My Posh                                                ║" -ForegroundColor $colors.Header
    Write-Host "  ║   • Nerd Fonts                                                ║" -ForegroundColor $colors.Header
    Write-Host "  ║   • Tema personalizado                                        ║" -ForegroundColor $colors.Header
    Write-Host "  ║   • Módulos útiles (PSReadLine, Terminal-Icons, z, posh-git)  ║" -ForegroundColor $colors.Header
    Write-Host "  ║                                                               ║" -ForegroundColor $colors.Header
    Write-Host "  ╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor $colors.Header
    Write-Host ""
    
    # Verificar administrador para instalar fuentes
    if (-not (Test-Administrator)) {
        Write-Warning "Se recomienda ejecutar como Administrador para instalar fuentes globalmente."
        Write-Host "  Continuando de todos modos..." -ForegroundColor DarkGray
    }
    
    # Selección de tema
    $selectedTheme = Show-ThemeSelector
    
    # Selección de fuente
    $selectedFont = Show-FontSelector
    
    Write-Host ""
    Write-Host "  Configuración seleccionada:" -ForegroundColor $colors.Info
    Write-Host "    • Tema: $selectedTheme" -ForegroundColor White
    Write-Host "    • Fuente: $selectedFont" -ForegroundColor White
    Write-Host ""
    
    $confirm = Read-Host "  ¿Continuar con la instalación? (S/n)"
    if ($confirm -eq "n" -or $confirm -eq "N") {
        Write-Host "  Instalación cancelada." -ForegroundColor $colors.Warning
        return
    }
    
    # 1. Instalar Oh My Posh
    $ohMyPoshInstalled = Install-OhMyPosh
    
    if (-not $ohMyPoshInstalled) {
        Write-ErrorMsg "No se pudo instalar Oh My Posh. Abortando."
        return
    }
    
    # 2. Instalar fuente
    Install-NerdFont -FontName $selectedFont
    
    # 3. Instalar tema
    $themePath = Install-Theme -ThemeName $selectedTheme
    
    if (-not $themePath) {
        Write-Warning "No se pudo descargar el tema. Usando tema por defecto."
        $themePath = "~/.poshthemes/montys.omp.json"
    }
    
    # 4. Instalar módulos
    Install-PowerShellModules
    
    # 5. Configurar perfil
    Initialize-PowerShellProfile -ThemePath $themePath
    
    # 6. Mostrar resumen
    Show-Summary -ThemeName $selectedTheme -FontName $selectedFont -ThemePath $themePath
}

# ═══════════════════════════════════════════════════════════════
# MODO RÁPIDO (sin preguntas)
# ═══════════════════════════════════════════════════════════════

function Start-QuickInstallation {
    param(
        [string]$Theme = "montys",
        [string]$Font = "FiraCode"
    )
    
    Clear-Host
    Write-Host ""
    Write-Host "  ⚡ Instalación rápida de Oh My Posh" -ForegroundColor $colors.Header
    Write-Host "  Tema: $Theme | Fuente: $Font" -ForegroundColor DarkGray
    Write-Host ""
    
    Install-OhMyPosh
    Install-NerdFont -FontName $Font
    $themePath = Install-Theme -ThemeName $Theme
    Install-PowerShellModules
    Initialize-PowerShellProfile -ThemePath $themePath
    Show-Summary -ThemeName $Theme -FontName $Font -ThemePath $themePath
}

# ═══════════════════════════════════════════════════════════════
# EJECUTAR
# ═══════════════════════════════════════════════════════════════

# Verificar parámetros
param(
    [switch]$Quick,
    [string]$Theme = "montys",
    [string]$Font = "FiraCode"
)

if ($Quick) {
    Start-QuickInstallation -Theme $Theme -Font $Font
} else {
    Start-Installation
}
