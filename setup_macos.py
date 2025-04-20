#!/usr/bin/env python3

import subprocess
import os
import sys
import time
from typing import List, Dict

# Verificar e instalar rich
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.progress import Progress
except ImportError:
    print("Instalando la biblioteca 'rich'...")
    subprocess.run([sys.executable, "-m", "pip", "install", "rich"], check=True)
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt
    from rich.progress import Progress

console = Console()

# Definición de categorías y aplicaciones
APPS_BY_CATEGORY = {
    "Gestores de Paquetes": [
        {"name": "pnpm", "command": "brew install pnpm", "cask": False},
        {"name": "Bun", "command": "brew install oven-sh/bun/bun", "cask": False},
        {"name": "Yarn", "command": "brew install yarn", "cask": False},
        {"name": "npm", "command": "brew install node", "cask": False},
    ],
    "Herramientas de Contenedores": [
        {"name": "Docker", "command": "brew install --cask docker", "cask": True},
        {"name": "kubectl", "command": "brew install kubectl", "cask": False},
        {"name": "Minikube", "command": "brew install minikube", "cask": False},
    ],
    "IDEs y Editores": [
        {"name": "Visual Studio Code", "command": "brew install --cask visual-studio-code", "cask": True},
        {"name": "Cursor", "command": "brew install --cask cursor", "cask": True},
        {"name": "IntelliJ IDEA", "command": "brew install --cask intellij-idea", "cask": True},
        {"name": "WebStorm", "command": "brew install --cask webstorm", "cask": True},
    ],
    "Navegadores": [
        {"name": "Google Chrome", "command": "brew install --cask google-chrome", "cask": True},
        {"name": "Brave", "command": "brew install --cask brave-browser", "cask": True},
        {"name": "Opera", "command": "brew install --cask opera", "cask": True},
        {"name": "Firefox", "command": "brew install --cask firefox", "cask": True},
    ],
    "Terminales": [
        {"name": "iTerm2", "command": "brew install --cask iterm2", "cask": True},
        {"name": "Warp", "command": "brew install --cask warp", "cask": True},
    ],
    "Lenguajes de Programación": [
        {"name": "Python", "command": "brew install python", "cask": False, "path": "/opt/homebrew/bin", "executable": "python3"},
        {"name": "Java", "command": "brew install java", "cask": False, "path": "/opt/homebrew/opt/openjdk/bin", "executable": "java"},
        {"name": "Rust", "command": "brew install rust", "cask": False, "path": "/opt/homebrew/bin", "executable": "rustc"},
        {"name": "C++ (clang)", "command": "brew install llvm", "cask": False, "path": "/opt/homebrew/opt/llvm/bin", "executable": "clang++"},
        {"name": "C# (Mono)", "command": "brew install mono", "cask": False, "path": "/opt/homebrew/bin", "executable": "mono"},
        {"name": "Go", "command": "brew install go", "cask": False, "path": "/opt/homebrew/bin", "executable": "go"},
        {"name": "Ruby", "command": "brew install ruby", "cask": False, "path": "/opt/homebrew/bin", "executable": "ruby"},
        {"name": "PHP", "command": "brew install php", "cask": False, "path": "/opt/homebrew/bin", "executable": "php"},
        {"name": "TypeScript", "command": "brew install typescript", "cask": False, "path": "/opt/homebrew/bin", "executable": "tsc"},
    ],
    "Bases de Datos": [
        {"name": "PostgreSQL", "command": "brew install postgresql", "cask": False},
        {"name": "MySQL", "command": "brew install mysql", "cask": False},
        {"name": "MongoDB", "command": "brew install mongodb-community", "cask": False},
    ],
    "Otros": [
        {"name": "Raycast", "command": "brew install raycast", "cask": False},
        {"name": "Telegram", "command": "brew install --cask telegram", "cask": True},
        {"name": "Slack", "command": "brew install --cask slack", "cask": True},
        {"name": "Tailscale", "command": "brew install tailscale", "cask": False},
        {"name": "fzf", "command": "brew install fzf", "cask": False},
        {"name": "GitHub CLI (gh)", "command": "brew install gh", "cask": False},
        {"name": "Obsidian", "command": "brew install --cask obsidian", "cask": True},
        {"name": "Notion", "command": "brew install --cask notion", "cask": True},
    ],
}

def run_command(command: str, description: str) -> bool:
    """Ejecuta un comando y muestra una barra de progreso."""
    with Progress() as progress:
        task = progress.add_task(f"[cyan]{description}...", total=100)
        process = subprocess.run(command, shell=True, capture_output=True, text=True)
        progress.update(task, advance=100)
        return process.returncode == 0

def check_brew() -> bool:
    """Verifica e instala Homebrew si no está presente."""
    console.print(Panel("Verificando Homebrew...", style="yellow"))
    if subprocess.run("which brew", shell=True, capture_output=True).returncode != 0:
        console.print("[yellow]Homebrew no encontrado. Instalando...[/yellow]")
        return run_command(
            '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
            "Instalando Homebrew"
        )
    console.print("[green]Homebrew encontrado.[/green]")
    return True

def check_git() -> bool:
    """Verifica e instala Git si no está presente."""
    console.print(Panel("Verificando Git...", style="yellow"))
    if subprocess.run("which git", shell=True, capture_output=True).returncode != 0:
        console.print("[yellow]Git no encontrado. Instalando...[/yellow]")
        return run_command("brew install git", "Instalando Git")
    console.print("[green]Git encontrado.[/green]")
    return True

def install_oh_my_zsh() -> None:
    """Instala Oh My Zsh y Powerlevel10k con plugins."""
    console.print(Panel("Configurando ZSH y Oh My Zsh...", style="yellow"))
    if os.path.exists(os.path.expanduser("~/.oh-my-zsh")):
        console.print("[green]Oh My Zsh ya está instalado.[/green]")
    else:
        console.print("[yellow]Instalando Oh My Zsh...[/yellow]")
        if not run_command(
            'sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" --unattended',
            "Instalando Oh My Zsh"
        ):
            console.print("[red]Error instalando Oh My Zsh.[/red]")
            sys.exit(1)

    # Instalar Powerlevel10k
    console.print("[yellow]Instalando Powerlevel10k...[/yellow]")
    run_command(
        "git clone --depth=1 https://github.com/romkatv/powerlevel10k.git $HOME/.oh-my-zsh/custom/themes/powerlevel10k",
        "Instalando Powerlevel10k"
    )
    run_command(
        "sed -i '' 's#robbyrussell#powerlevel10k/powerlevel10k#g' ~/.zshrc",
        "Configurando Powerlevel10k"
    )

    # Instalar plugins
    console.print("[yellow]Instalando plugins de ZSH...[/yellow]")
    plugins = [
        ("zsh-autosuggestions", "https://github.com/zsh-users/zsh-autosuggestions"),
        ("zsh-history-substring-search", "https://github.com/zsh-users/zsh-history-substring-search"),
        ("zsh-syntax-highlighting", "https://github.com/zsh-users/zsh-syntax-highlighting"),
    ]
    for plugin, url in plugins:
        run_command(
            f"git clone {url} $HOME/.oh-my-zsh/custom/plugins/{plugin}",
            f"Instalando {plugin}"
        )
    run_command(
        "sed -i '' 's/plugins=(git)/plugins=(git jump zsh-autosuggestions zsh-history-substring-search jsontools zsh-syntax-highlighting zsh-interactive-cd)/g' ~/.zshrc",
        "Configurando plugins"
    )

def configure_git_global() -> None:
    """Configura el nombre y correo electrónico global de Git."""
    console.print(Panel("Configurando credenciales globales de Git...", style="yellow"))

    # Verificar si ya están configuradas
    current_user = subprocess.run("git config --global user.name", shell=True, capture_output=True, text=True).stdout.strip()
    current_email = subprocess.run("git config --global user.email", shell=True, capture_output=True, text=True).stdout.strip()

    if current_user and current_email:
        console.print(f"[green]Credenciales de Git ya configuradas: {current_user} <{current_email}>[/green]")
        if not Confirm.ask("¿Quieres sobrescribir las credenciales existentes?", default=False):
            return

    # Solicitar nuevas credenciales
    try:
        user_name = Prompt.ask("Ingresa tu nombre para Git (e.g., Juan Pérez)", default="")
        user_email = Prompt.ask("Ingresa tu correo electrónico para Git (e.g., juan@example.com)", default="")
    except EOFError:
        console.print("[yellow]Entrada interrumpida. Saltando configuración de Git.[/yellow]")
        return

    if user_name and user_email:
        run_command(f'git config --global user.name "{user_name}"', "Configurando nombre de Git")
        run_command(f'git config --global user.email "{user_email}"', "Configurando correo de Git")
        console.print(f"[green]Credenciales de Git configuradas: {user_name} <{user_email}>[/green]")
    else:
        console.print("[yellow]No se proporcionaron credenciales válidas. Saltando configuración de Git.[/yellow]")

def configure_ssh_key() -> None:
    """Genera una clave SSH segura y la configura para GitHub usando GitHub CLI."""
    console.print(Panel("Configurando clave SSH para GitHub...", style="yellow"))

    ssh_key_path = os.path.expanduser("~/.ssh/id_ed25519")
    if os.path.exists(ssh_key_path):
        console.print("[green]Clave SSH ya existe en ~/.ssh/id_ed25519.[/green]")
        if not Confirm.ask("¿Quieres generar una nueva clave SSH (sobrescribirá la existente)?", default=False):
            console.print("[yellow]Usando clave SSH existente.[/yellow]")
            add_ssh_key_to_github(ssh_key_path)
            return

    # Verificar si GitHub CLI está instalado
    if subprocess.run("which gh", shell=True, capture_output=True).returncode != 0:
        console.print("[yellow]GitHub CLI no encontrado. Instalando...[/yellow]")
        if not run_command("brew install gh", "Instalando GitHub CLI"):
            console.print("[red]Error instalando GitHub CLI. Configura la clave manualmente en GitHub.[/red]")
            show_ssh_key_instructions(ssh_key_path)
            return

    # Solicitar correo para la clave SSH
    try:
        email = Prompt.ask("Ingresa tu correo electrónico para la clave SSH (e.g., juan@example.com)", default="")
    except EOFError:
        console.print("[yellow]Entrada interrumpida. Saltando generación de clave SSH.[/yellow]")
        return

    if not email:
        console.print("[yellow]No se proporcionó un correo válido. Saltando generación de clave SSH.[/yellow]")
        return

    # Generar clave SSH
    console.print("[yellow]Generando clave SSH (ed25519)...[/yellow]")
    if not run_command(
        f'ssh-keygen -t ed25519 -C "{email}" -f {ssh_key_path} -N ""',
        "Generando clave SSH"
    ):
        console.print("[red]Error generando clave SSH.[/red]")
        return

    # Iniciar ssh-agent
    run_command("eval $(ssh-agent -s)", "Iniciando ssh-agent")
    run_command(f"ssh-add {ssh_key_path}", "Añadiendo clave SSH al agente")

    # Configurar ~/.ssh/config
    ssh_config_path = os.path.expanduser("~/.ssh/config")
    ssh_config_content = """
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
"""
    if not os.path.exists(os.path.dirname(ssh_config_path)):
        os.makedirs(os.path.dirname(ssh_config_path))
    with open(ssh_config_path, "a") as f:
        if ssh_config_content.strip() not in f.read():
            f.write(ssh_config_content)
    run_command(f"chmod 600 {ssh_config_path}", "Configurando permisos de ~/.ssh/config")

    # Añadir clave a GitHub usando GitHub CLI
    add_ssh_key_to_github(ssh_key_path)

def add_ssh_key_to_github(ssh_key_path: str) -> None:
    """Añade la clave pública SSH a GitHub usando GitHub CLI."""
    public_key_path = f"{ssh_key_path}.pub"
    if not os.path.exists(public_key_path):
        console.print("[red]No se encontró la clave pública SSH.[/red]")
        return

    # Verificar autenticación en GitHub CLI
    console.print("[yellow]Verificando autenticación en GitHub CLI...[/yellow]")
    if subprocess.run("gh auth status", shell=True, capture_output=True).returncode != 0:
        console.print("[yellow]Autenticando en GitHub CLI...[/yellow]")
        if not run_command("gh auth login", "Autenticando en GitHub CLI"):
            console.print("[red]Error autenticando en GitHub CLI. Configura la clave manualmente en GitHub.[/red]")
            show_ssh_key_instructions(ssh_key_path)
            return

    # Añadir la clave a GitHub
    console.print("[yellow]Añadiendo clave SSH a GitHub...[/yellow]")
    title = f"MacBook_{time.strftime('%Y%m%d')}"
    if run_command(
        f'gh ssh-key add {public_key_path} --title "{title}" --type authentication',
        "Añadiendo clave SSH a GitHub"
    ):
        console.print("[green]Clave SSH añadida a GitHub correctamente.[/green]")
    else:
        console.print("[red]Error añadiendo clave SSH a GitHub. Configura la clave manualmente.[/red]")
        show_ssh_key_instructions(ssh_key_path)

    # Probar conexión con GitHub
    console.print("[yellow]Probando conexión SSH con GitHub...[/yellow]")
    result = subprocess.run("ssh -T git@github.com", shell=True, capture_output=True, text=True)
    if "successfully authenticated" in result.stderr:
        console.print("[green]Conexión SSH con GitHub verificada correctamente.[/green]")
    else:
        console.print("[yellow]No se pudo verificar la conexión con GitHub. Asegúrate de que la clave está correctamente configurada.[/yellow]")

def show_ssh_key_instructions(ssh_key_path: str) -> None:
    """Muestra la clave pública SSH e instrucciones para añadirla a GitHub."""
    public_key_path = f"{ssh_key_path}.pub"
    if os.path.exists(public_key_path):
        with open(public_key_path, "r") as f:
            public_key = f.read().strip()
        console.print(Panel(
            f"[bold]Clave pública SSH:[/bold]\n{public_key}\n\n"
            "1. Copia la clave pública arriba.\n"
            "2. Ve a https://github.com/settings/keys\n"
            "3. Haz clic en 'New SSH key' o 'Add SSH key'.\n"
            "4. Pega la clave en el campo 'Key' y dale un título (e.g., 'MacBook').\n"
            "5. Haz clic en 'Add SSH key'.",
            title="Instrucciones para GitHub",
            style="cyan"
        ))
    else:
        console.print("[red]No se encontró la clave pública SSH.[/red]")

def add_to_path(app: Dict) -> None:
    """Añade la ruta de un lenguaje al PATH si no está presente."""
    if "path" not in app or "executable" not in app:
        return

    executable = app["executable"]
    path_to_add = app["path"]

    # Verificar si el ejecutable ya está en el PATH
    if subprocess.run(f"which {executable}", shell=True, capture_output=True).returncode == 0:
        console.print(f"[green]{executable} ya está en el PATH.[/green]")
        return

    # Añadir al PATH en ~/.zshrc
    zshrc_path = os.path.expanduser("~/.zshrc")
    export_line = f'export PATH="{path_to_add}:$PATH"'
    
    with open(zshrc_path, "r") as f:
        if export_line in f.read():
            console.print(f"[green]Ruta {path_to_add} ya está en ~/.zshrc.[/green]")
            return

    console.print(f"[yellow]Añadiendo {path_to_add} al PATH en ~/.zshrc...[/yellow]")
    with open(zshrc_path, "a") as f:
        f.write(f"\n# Añadido por setup_macos.py\n{export_line}\n")
    console.print(f"[green]Ruta para {executable} añadida al PATH.[/green]")

def is_app_installed(app: Dict) -> bool:
    """Verifica si una aplicación ya está instalada con Homebrew."""
    package_name = app["command"].split()[-1]  # Extrae el nombre del paquete (última palabra del comando)
    cmd = "brew list --cask" if app["cask"] else "brew list"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return package_name in result.stdout.split()

def select_apps() -> List[Dict]:
    """Muestra un menú interactivo por categorías para seleccionar aplicaciones."""
    console.print(Panel("Selecciona las aplicaciones a instalar por categoría:", style="cyan"))
    selected_apps = []

    for category, apps in APPS_BY_CATEGORY.items():
        console.print(Panel(f"Categoría: {category}", style="bold magenta"))

        # Mostrar tabla de aplicaciones en la categoría
        table = Table(title=f"Aplicaciones en {category}")
        table.add_column("Seleccionar", style="cyan")
        table.add_column("Nombre", style="green")
        for i, app in enumerate(apps, 1):
            table.add_row(f"[{i}]", app["name"])
        console.print(table)

        # Selección interactiva
        try:
            choices = Prompt.ask(
                f"Ingresa los números de las aplicaciones a instalar (ej. 1,3,5), 'all' para todas, '0' o 'n' para omitir",
                default="",
            )
            choices = choices.lower().strip()
            if choices == "all":
                selected_apps.extend(apps)
            elif choices in ("0", "n", ""):  # Omitir si es '0', 'n' o entrada vacía
                console.print(f"[yellow]Omitiendo categoría {category}.[/yellow]")
            else:
                try:
                    indices = [int(i) - 1 for i in choices.split(",") if i.strip()]
                    for idx in indices:
                        if 0 <= idx < len(apps):
                            selected_apps.append(apps[idx])
                except ValueError:
                    console.print(f"[yellow]Entrada inválida para {category}. Saltando...[/yellow]")
        except EOFError:
            console.print(f"[yellow]Entrada interrumpida para {category}. Saltando...[/yellow]")

    return selected_apps

def install_apps(selected_apps: List[Dict]) -> None:
    """Instala las aplicaciones seleccionadas y muestra un resumen."""
    if not selected_apps:
        console.print("[yellow]No se seleccionaron aplicaciones.[/yellow]")
        return

    # Mostrar tabla de aplicaciones seleccionadas
    table = Table(title="Aplicaciones a instalar")
    table.add_column("Nombre", style="cyan")
    for app in selected_apps:
        table.add_row(app["name"])
    console.print(table)

    # Instalar aplicaciones seleccionadas
    for app in selected_apps:
        if is_app_installed(app):
            console.print(f"[green]{app['name']} ya está instalado.[/green]")
            if "path" in app:
                add_to_path(app)
            continue
        console.print(f"[yellow]Instalando {app['name']}...[/yellow]")
        if run_command(app["command"], f"Instalando {app['name']}"):
            # Añadir al PATH si es un lenguaje
            if "path" in app:
                add_to_path(app)
        else:
            console.print(f"[red]Error instalando {app['name']}.[/red]")

def hide_dock() -> None:
    """Oculta el Dock de macOS si el usuario lo desea."""
    try:
        if Confirm.ask("¿Ocultar el Dock de macOS?", default=True):
            console.print("[yellow]Ocultando el Dock...[/yellow]")
            run_command(
                "defaults write com.apple.dock autohide -bool true; killall Dock",
                "Ocultando Dock"
            )
            console.print("[green]Dock ocultado.[/green]")
        else:
            console.print("[green]El Dock permanecerá visible.[/green]")
    except EOFError:
        console.print("[yellow]Entrada interrumpida. El Dock permanecerá visible.[/yellow]")

def restart_terminal() -> None:
    """Pregunta al usuario si desea reiniciar la terminal para aplicar cambios."""
    try:
        if Confirm.ask("¿Reiniciar la terminal ahora para aplicar los cambios (Oh My Zsh, PATH, etc.)?", default=True):
            console.print("[yellow]Abriendo una nueva ventana de terminal y cerrando la actual...[/yellow]")
            # Abrir nueva ventana de Terminal.app y cerrar la actual
            run_command(
                'osascript -e \'tell application "Terminal" to do script ""\' -e \'tell application "Terminal" to close (every window whose name contains "bash")\'',
                "Reiniciando terminal"
            )
            sys.exit(0)  # Salir del script tras reiniciar
        else:
            console.print("[yellow]No se reinició la terminal. Por favor, reinicia manualmente para aplicar los cambios.[/yellow]")
    except EOFError:
        console.print("[yellow]Entrada interrumpida. No se reinició la terminal. Por favor, reinicia manualmente.[/yellow]")

def main() -> None:
    console.print(Panel("Script de Configuración para macOS", style="bold green", expand=False))

    # Verificar Homebrew y Git
    if not check_brew() or not check_git():
        console.print("[red]Error en la configuración inicial.[/red]")
        sys.exit(1)

    # Configurar ZSH y Oh My Zsh
    install_oh_my_zsh()

    # Configurar credenciales de Git
    try:
        if Confirm.ask("¿Configurar credenciales globales de Git?", default=True):
            configure_git_global()
        else:
            console.print("[yellow]Saltando configuración de credenciales de Git.[/yellow]")
    except EOFError:
        console.print("[yellow]Entrada interrumpida. Saltando configuración de credenciales de Git.[/yellow]")

    # Configurar clave SSH para GitHub
    try:
        if Confirm.ask("¿Configurar una clave SSH para GitHub?", default=True):
            configure_ssh_key()
        else:
            console.print("[yellow]Saltando configuración de clave SSH.[/yellow]")
    except EOFError:
        console.print("[yellow]Entrada interrumpida. Saltando configuración de clave SSH.[/yellow]")

    # Seleccionar e instalar aplicaciones
    selected_apps = select_apps()
    install_apps(selected_apps)

    # Ocultar Dock
    hide_dock()

    # Resumen final
    console.print(Panel(
        "¡Configuración completada! Los cambios en la terminal (Oh My Zsh, PATH, etc.) requieren reiniciar la terminal.",
        style="bold green"
    ))

    # Preguntar si reiniciar la terminal
    restart_terminal()

if __name__ == "__main__":
    main()
