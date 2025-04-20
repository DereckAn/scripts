use console::{style, Term};
use dialoguer::{Confirm, Input};
use indicatif::{ProgressBar, ProgressStyle};
use prettytable::{row, Table};
use std::collections::HashMap;
use std::fs::{create_dir_all, OpenOptions};
use std::io::Write;
use std::path::Path;
use std::process::Command;

#[derive(Clone)]
struct App {
    name: String,
    command: String,
    cask: bool,
    path: Option<String>,
    executable: Option<String>,
}

fn run_command(cmd: &str, desc: &str) -> bool {
    let pb = ProgressBar::new(100);
    pb.set_style(
        ProgressStyle::default_bar()
            .template("{prefix:.yellow} {msg} [{bar:40.cyan/blue}] {percent}%")
            .unwrap()
            .progress_chars("##-"),
    );
    pb.set_prefix("Ejecutando");
    pb.set_message(desc.to_string()); // Convertir desc a String
    pb.inc(10);

    let status = Command::new("sh")
        .arg("-c")
        .arg(cmd)
        .status()
        .expect("Error ejecutando comando");
    pb.inc(90);
    pb.finish_with_message(format!("{}", style("Hecho").green()));

    status.success()
}

fn check_brew() -> bool {
    println!("{}", style("Verificando Homebrew...").yellow());
    if !Command::new("which")
        .arg("brew")
        .status()
        .expect("Error verificando brew")
        .success()
    {
        println!("{}", style("Homebrew no encontrado. Instalando...").yellow());
        run_command(
            "/bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"",
            "Instalando Homebrew",
        )
    } else {
        println!("{}", style("Homebrew encontrado.").green());
        true
    }
}

fn check_git() -> bool {
    println!("{}", style("Verificando Git...").yellow());
    if !Command::new("which")
        .arg("git")
        .status()
        .expect("Error verificando git")
        .success()
    {
        println!("{}", style("Git no encontrado. Instalando...").yellow());
        run_command("brew install git", "Instalando Git")
    } else {
        println!("{}", style("Git encontrado.").green());
        true
    }
}

fn install_oh_my_zsh() -> bool {
    println!("{}", style("Configurando Oh My Zsh...").yellow());
    if Path::new(&format!("{}/.oh-my-zsh", std::env::var("HOME").unwrap())).exists() {
        println!("{}", style("Oh My Zsh ya instalado.").green());
    } else {
        println!("{}", style("Instalando Oh My Zsh...").yellow());
        if !run_command(
            "sh -c \"$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)\" --unattended",
            "Instalando Oh My Zsh",
        ) {
            println!("{}", style("Error instalando Oh My Zsh.").red());
            return false;
        }
    }

    println!("{}", style("Instalando Powerlevel10k...").yellow());
    run_command(
        "git clone --depth=1 https://github.com/romkatv/powerlevel10k.git $HOME/.oh-my-zsh/custom/themes/powerlevel10k",
        "Instalando Powerlevel10k",
    );
    run_command(
        "sed -i '' 's/ZSH_THEME=\"robbyrussell\"/ZSH_THEME=\"powerlevel10k\\/powerlevel10k\"/' ~/.zshrc",
        "Configurando Powerlevel10k",
    );

    println!("{}", style("Instalando plugins de Zsh...").yellow());
    run_command(
        "git clone https://github.com/zsh-users/zsh-autosuggestions $HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions",
        "Instalando zsh-autosuggestions",
    );
    run_command(
        "git clone https://github.com/zsh-users/zsh-history-substring-search $HOME/.oh-my-zsh/custom/plugins/zsh-history-substring-search",
        "Instalando zsh-history-substring-search",
    );
    run_command(
        "git clone https://github.com/zsh-users/zsh-syntax-highlighting $HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting",
        "Instalando zsh-syntax-highlighting",
    );
    run_command(
        "sed -i '' 's/plugins=(git)/plugins=(git jump zsh-autosuggestions zsh-history-substring-search jsontools zsh-syntax-highlighting zsh-interactive-cd)/' ~/.zshrc",
        "Configurando plugins",
    );
    true
}

fn configure_git_global() -> bool {
    println!("{}", style("Configurando credenciales de Git...").yellow());
    if Confirm::new()
        .with_prompt("¿Configurar credenciales globales de Git?")
        .default(true)
        .interact()
        .unwrap_or(false)
    {
        let current_user = Command::new("git")
            .args(["config", "--global", "user.name"])
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
            .unwrap_or_default();
        let current_email = Command::new("git")
            .args(["config", "--global", "user.email"])
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
            .unwrap_or_default();

        if !current_user.is_empty() && !current_email.is_empty() {
            println!(
                "{}",
                style(format!(
                    "Credenciales ya configuradas: {} <{}>",
                    current_user, current_email
                ))
                .green()
            );
            if !Confirm::new()
                .with_prompt("¿Sobrescribir credenciales existentes?")
                .default(false)
                .interact()
                .unwrap_or(false)
            {
                return true;
            }
        }

        let user_name: String = Input::new()
            .with_prompt("Ingresa tu nombre para Git (e.g., Juan Pérez)")
            .allow_empty(true)
            .interact_text()
            .unwrap_or_default();
        let user_email: String = Input::new()
            .with_prompt("Ingresa tu correo para Git (e.g., juan@example.com)")
            .allow_empty(true)
            .interact_text()
            .unwrap_or_default();

        if !user_name.is_empty() && !user_email.is_empty() {
            run_command(
                &format!("git config --global user.name \"{}\"", user_name),
                "Configurando nombre de Git",
            );
            run_command(
                &format!("git config --global user.email \"{}\"", user_email),
                "Configurando correo de Git",
            );
            println!(
                "{}",
                style(format!(
                    "Credenciales configuradas: {} <{}>",
                    user_name, user_email
                ))
                .green()
            );
        } else {
            println!(
                "{}",
                style("No se proporcionaron credenciales válidas. Saltando...").yellow()
            );
        }
    } else {
        println!(
            "{}",
            style("Saltando configuración de credenciales de Git.").yellow()
        );
    }
    true
}

fn configure_ssh_key() -> bool {
    println!("{}", style("Configurando clave SSH para GitHub...").yellow());
    if Confirm::new()
        .with_prompt("¿Configurar una clave SSH para GitHub?")
        .default(true)
        .interact()
        .unwrap_or(false)
    {
        let ssh_key_path = format!("{}/.ssh/id_ed25519", std::env::var("HOME").unwrap());
        if Path::new(&ssh_key_path).exists() {
            println!(
                "{}",
                style("Clave SSH ya existe en ~/.ssh/id_ed25519.").green()
            );
            if !Confirm::new()
                .with_prompt("¿Generar nueva clave (sobrescribirá la existente)?")
                .default(false)
                .interact()
                .unwrap_or(false)
            {
                println!("{}", style("Usando clave existente.").yellow());
                add_ssh_key_to_github(&ssh_key_path);
                return true;
            }
        }

        if !Command::new("which")
            .arg("gh")
            .status()
            .expect("Error verificando gh")
            .success()
        {
            println!("{}", style("GitHub CLI no encontrado. Instalando...").yellow());
            run_command("brew install gh", "Instalando GitHub CLI");
        }

        let email: String = Input::new()
            .with_prompt("Ingresa tu correo para SSH (e.g., juan@example.com)")
            .allow_empty(true)
            .interact_text()
            .unwrap_or_default();

        if email.is_empty() {
            println!(
                "{}",
                style("No se proporcionó correo válido. Saltando...").yellow()
            );
            return true;
        }

        println!("{}", style("Generando clave SSH (ed25519)...").yellow());
        if !run_command(
            &format!(
                "ssh-keygen -t ed25519 -C \"{}\" -f {} -N \"\"",
                email, ssh_key_path
            ),
            "Generando clave SSH",
        ) {
            println!("{}", style("Error generando clave SSH.").red());
            return false;
        }

        run_command("eval $(ssh-agent -s)", "Iniciando ssh-agent");
        run_command(
            &format!("ssh-add {}", ssh_key_path),
            "Añadiendo clave SSH al agente",
        );

        let ssh_config_path = format!("{}/.ssh/config", std::env::var("HOME").unwrap());
        let ssh_config_content = "Host github.com\n    HostName github.com\n    User git\n    IdentityFile ~/.ssh/id_ed25519\n    IdentitiesOnly yes\n";
        create_dir_all(format!("{}/.ssh", std::env::var("HOME").unwrap())).unwrap();
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&ssh_config_path)
            .unwrap();
        if !std::fs::read_to_string(&ssh_config_path)
            .unwrap_or_default()
            .contains("Host github.com")
        {
            file.write_all(ssh_config_content.as_bytes()).unwrap();
        }
        run_command(
            &format!("chmod 600 {}", ssh_config_path),
            "Configurando permisos de ~/.ssh/config",
        );

        add_ssh_key_to_github(&ssh_key_path);
    } else {
        println!(
            "{}",
            style("Saltando configuración de clave SSH.").yellow()
        );
    }
    true
}

fn add_ssh_key_to_github(ssh_key_path: &str) -> bool {
    let public_key_path = format!("{}.pub", ssh_key_path);
    if !Path::new(&public_key_path).exists() {
        println!(
            "{}",
            style("No se encontró la clave pública SSH.").red()
        );
        return false;
    }

    println!(
        "{}",
        style("Verificando autenticación en GitHub CLI...").yellow()
    );
    if !Command::new("gh")
        .arg("auth")
        .arg("status")
        .status()
        .expect("Error verificando gh auth")
        .success()
    {
        println!("{}", style("Autenticando en GitHub CLI...").yellow());
        if !run_command("gh auth login", "Autenticando en GitHub CLI") {
            show_ssh_key_instructions(&public_key_path);
            return false;
        }
    }

    println!("{}", style("Añadiendo clave SSH a GitHub...").yellow());
    let title = format!("MacBook_{}", chrono::Local::now().format("%Y%m%d"));
    if run_command(
        &format!(
            "gh ssh-key add {} --title \"{}\" --type authentication",
            public_key_path, title
        ),
        "Añadiendo clave SSH a GitHub",
    ) {
        println!(
            "{}",
            style("Clave SSH añadida a GitHub correctamente.").green()
        );
    } else {
        println!(
            "{}",
            style("Error añadiendo clave SSH a GitHub.").red()
        );
        show_ssh_key_instructions(&public_key_path);
        return false;
    }

    println!(
        "{}",
        style("Probando conexión SSH con GitHub...").yellow()
    );
    let output = Command::new("ssh")
        .args(["-T", "git@github.com"])
        .output()
        .expect("Error probando SSH");
    if String::from_utf8_lossy(&output.stderr).contains("successfully authenticated") {
        println!(
            "{}",
            style("Conexión SSH verificada correctamente.").green()
        );
    } else {
        println!(
            "{}",
            style("No se pudo verificar la conexión con GitHub.").yellow()
        );
    }
    true
}

fn show_ssh_key_instructions(public_key_path: &str) {
    if let Ok(public_key) = std::fs::read_to_string(public_key_path) {
        println!(
            "{}",
            style("Clave pública SSH:").cyan()
        );
        println!("{}", public_key.trim());
        println!(
            "{}",
            style("\nInstrucciones:").cyan()
        );
        println!("1. Copia la clave pública arriba.");
        println!("2. Ve a https://github.com/settings/keys");
        println!("3. Haz clic en 'New SSH key' o 'Add SSH key'.");
        println!("4. Pega la clave en el campo 'Key' y dale un título (e.g., 'MacBook').");
        println!("5. Haz clic en 'Add SSH key'.");
    } else {
        println!(
            "{}",
            style("No se encontró la clave pública SSH.").red()
        );
    }
}

fn is_app_installed(package_name: &str, cask: bool) -> bool {
    let cmd = if cask { "brew list --cask" } else { "brew list" };
    let output = Command::new("sh")
        .arg("-c")
        .arg(cmd)
        .output()
        .expect("Error verificando brew list");
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .any(|line| line.trim() == package_name)
}

fn add_to_path(app: &App) {
    if app.path.is_none() || app.executable.is_none() {
        return;
    }
    let executable = app.executable.as_ref().unwrap();
    let path_to_add = app.path.as_ref().unwrap();

    if Command::new("which")
        .arg(executable)
        .status()
        .expect("Error verificando executable")
        .success()
    {
        println!(
            "{}",
            style(format!("{} ya está en el PATH.", executable)).green()
        );
        return;
    }

    let zshrc_path = format!("{}/.zshrc", std::env::var("HOME").unwrap());
    let export_line = format!("export PATH=\"{}:$PATH\"", path_to_add);
    if std::fs::read_to_string(&zshrc_path)
        .unwrap_or_default()
        .contains(&export_line)
    {
        println!(
            "{}",
            style(format!("Ruta {} ya está en ~/.zshrc.", path_to_add)).green()
        );
        return;
    }

    println!(
        "{}",
        style(format!("Añadiendo {} al PATH en ~/.zshrc...", path_to_add)).yellow()
    );
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&zshrc_path)
        .unwrap();
    writeln!(file, "# Añadido por setup_macos\n{}", export_line).unwrap();
    println!(
        "{}",
        style(format!("Ruta para {} añadida al PATH.", app.name)).green()
    );
}

fn select_apps() -> Vec<App> {
    let mut categories: HashMap<String, Vec<App>> = HashMap::new();
    categories.insert(
        "Gestores de Paquetes".to_string(),
        vec![
            App {
                name: "pnpm".to_string(),
                command: "brew install pnpm".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
            App {
                name: "Bun".to_string(),
                command: "brew install oven-sh/bun/bun".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
            App {
                name: "Yarn".to_string(),
                command: "brew install yarn".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
            App {
                name: "Node".to_string(),
                command: "brew install node".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
        ],
    );
    categories.insert(
        "Herramientas de Contenedores".to_string(),
        vec![
            App {
                name: "Docker".to_string(),
                command: "brew install --cask docker".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
            App {
                name: "kubectl".to_string(),
                command: "brew install kubectl".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
            App {
                name: "Minikube".to_string(),
                command: "brew install minikube".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
        ],
    );
    categories.insert(
        "IDEs y Editores".to_string(),
        vec![
            App {
                name: "Visual Studio Code".to_string(),
                command: "brew install --cask visual-studio-code".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
            App {
                name: "Cursor".to_string(),
                command: "brew install --cask cursor".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
            App {
                name: "IntelliJ IDEA".to_string(),
                command: "brew install --cask intellij-idea".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
            App {
                name: "WebStorm".to_string(),
                command: "brew install --cask webstorm".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
        ],
    );
    categories.insert(
        "Navegadores".to_string(),
        vec![
            App {
                name: "Google Chrome".to_string(),
                command: "brew install --cask google-chrome".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
            App {
                name: "Brave".to_string(),
                command: "brew install --cask brave-browser".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
            App {
                name: "Opera".to_string(),
                command: "brew install --cask opera".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
            App {
                name: "Firefox".to_string(),
                command: "brew install --cask firefox".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
        ],
    );
    categories.insert(
        "Terminales".to_string(),
        vec![
            App {
                name: "iTerm2".to_string(),
                command: "brew install --cask iterm2".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
            App {
                name: "Warp".to_string(),
                command: "brew install --cask warp".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
        ],
    );
    categories.insert(
        "Lenguajes de Programación".to_string(),
        vec![
            App {
                name: "Python".to_string(),
                command: "brew install python".to_string(),
                cask: false,
                path: Some("/opt/homebrew/bin".to_string()),
                executable: Some("python3".to_string()),
            },
            App {
                name: "Java".to_string(),
                command: "brew install java".to_string(),
                cask: false,
                path: Some("/opt/homebrew/opt/openjdk/bin".to_string()),
                executable: Some("java".to_string()),
            },
            App {
                name: "Rust".to_string(),
                command: "brew install rust".to_string(),
                cask: false,
                path: Some("/opt/homebrew/bin".to_string()),
                executable: Some("rustc".to_string()),
            },
            App {
                name: "C++ (clang)".to_string(),
                command: "brew install llvm".to_string(),
                cask: false,
                path: Some("/opt/homebrew/opt/llvm/bin".to_string()),
                executable: Some("clang++".to_string()),
            },
            App {
                name: "C# (Mono)".to_string(),
                command: "brew install mono".to_string(),
                cask: false,
                path: Some("/opt/homebrew/bin".to_string()),
                executable: Some("mono".to_string()),
            },
            App {
                name: "Go".to_string(),
                command: "brew install go".to_string(),
                cask: false,
                path: Some("/opt/homebrew/bin".to_string()),
                executable: Some("go".to_string()),
            },
            App {
                name: "Ruby".to_string(),
                command: "brew install ruby".to_string(),
                cask: false,
                path: Some("/opt/homebrew/bin".to_string()),
                executable: Some("ruby".to_string()),
            },
            App {
                name: "PHP".to_string(),
                command: "brew install php".to_string(),
                cask: false,
                path: Some("/opt/homebrew/bin".to_string()),
                executable: Some("php".to_string()),
            },
            App {
                name: "TypeScript".to_string(),
                command: "brew install typescript".to_string(),
                cask: false,
                path: Some("/opt/homebrew/bin".to_string()),
                executable: Some("tsc".to_string()),
            },
        ],
    );
    categories.insert(
        "Bases de Datos".to_string(),
        vec![
            App {
                name: "PostgreSQL".to_string(),
                command: "brew install postgresql".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
            App {
                name: "MySQL".to_string(),
                command: "brew install mysql".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
            App {
                name: "MongoDB".to_string(),
                command: "brew install mongodb-community".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
        ],
    );
    categories.insert(
        "Otros".to_string(),
        vec![
            App {
                name: "Raycast".to_string(),
                command: "brew install raycast".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
            App {
                name: "Telegram".to_string(),
                command: "brew install --cask telegram".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
            App {
                name: "Slack".to_string(),
                command: "brew install --cask slack".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
            App {
                name: "Tailscale".to_string(),
                command: "brew install tailscale".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
            App {
                name: "fzf".to_string(),
                command: "brew install fzf".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
            App {
                name: "GitHub CLI (gh)".to_string(),
                command: "brew install gh".to_string(),
                cask: false,
                path: None,
                executable: None,
            },
            App {
                name: "Obsidian".to_string(),
                command: "brew install --cask obsidian".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
            App {
                name: "Notion".to_string(),
                command: "brew install --cask notion".to_string(),
                cask: true,
                path: None,
                executable: None,
            },
        ],
    );

    let mut selected_apps = vec![];
    println!(
        "{}",
        style("Selecciona las aplicaciones a instalar por categoría:").cyan()
    );

    for (category, apps) in categories {
        println!("\n{}", style(format!("Categoría: {}", category)).blue());
        let mut table = Table::new();
        table.add_row(row!["ID", "Aplicación"]);
        for (i, app) in apps.iter().enumerate() {
            table.add_row(row![format!("[{}]", i + 1), app.name]);
        }
        table.printstd();

        let choices: String = Input::<String>::new()
            .with_prompt(
                "Ingresa los números (ej. 1,3,5), 'all', '0' o 'n' para omitir",
            )
            .allow_empty(true)
            .interact_text()
            .unwrap_or_default()
            .to_lowercase();

        if choices == "all" {
            selected_apps.extend(apps);
        } else if choices == "0" || choices == "n" || choices.is_empty() {
            println!(
                "{}",
                style(format!("Omitiendo categoría {}.", category)).yellow()
            );
        } else {
            let indices: Vec<usize> = choices
                .split(',')
                .filter_map(|s| s.trim().parse::<usize>().ok())
                .filter(|&i| i > 0 && i <= apps.len())
                .map(|i| i - 1)
                .collect();
            for idx in indices {
                selected_apps.push(apps[idx].clone());
            }
        }
    }
    selected_apps
}

fn install_apps(apps: &[App]) {
    if apps.is_empty() {
        println!(
            "{}",
            style("No se seleccionaron aplicaciones.").yellow()
        );
        return;
    }

    println!("{}", style("Aplicaciones a instalar:").cyan());
    let mut table = Table::new();
    table.add_row(row!["Nombre"]);
    for app in apps {
        table.add_row(row![app.name]);
    }
    table.printstd();

    for app in apps {
        let package_name = app
            .command
            .split_whitespace()
            .last()
            .expect("Error extrayendo nombre del paquete");
        if is_app_installed(package_name, app.cask) {
            println!(
                "{}",
                style(format!("{} ya está instalado.", app.name)).green()
            );
            add_to_path(app);
            continue;
        }
        println!(
            "{}",
            style(format!("Instalando {}...", app.name)).yellow()
        );
        if run_command(&app.command, &format!("Instalando {}", app.name)) {
            add_to_path(app);
        } else {
            println!(
                "{}",
                style(format!("Error instalando {}.", app.name)).red()
            );
        }
    }
}

fn hide_dock() -> bool {
    if Confirm::new()
        .with_prompt("¿Ocultar el Dock de macOS?")
        .default(true)
        .interact()
        .unwrap_or(false)
    {
        println!("{}", style("Ocultando el Dock...").yellow());
        run_command(
            "defaults write com.apple.dock autohide -bool true && killall Dock",
            "Ocultando Dock",
        );
        println!("{}", style("Dock ocultado.").green());
    } else {
        println!(
            "{}",
            style("El Dock permanecerá visible.").green()
        );
    }
    true
}

fn restart_terminal() -> bool {
    if Confirm::new()
        .with_prompt("¿Reiniciar la terminal para aplicar cambios?")
        .default(true)
        .interact()
        .unwrap_or(false)
    {
        println!(
            "{}",
            style("Abriendo nueva ventana de terminal y cerrando la actual...").yellow()
        );
        run_command(
            "osascript -e 'tell application \"Terminal\" to do script \"\"' -e 'tell application \"Terminal\" to close (every window whose name contains \"bash\")'",
            "Reiniciando terminal",
        );
        std::process::exit(0);
    } else {
        println!(
            "{}",
            style("No se reinició la terminal. Reinicia manualmente para aplicar cambios.").yellow()
        );
    }
    true
}

fn main() {
    let term = Term::stdout();
    term.clear_screen().unwrap();
    println!(
        "{}",
        style("Script de Configuración para macOS").bold().green()
    );

    if !check_brew() || !check_git() {
        println!("{}", style("Error en la configuración inicial.").red());
        std::process::exit(1);
    }

    if !install_oh_my_zsh() {
        std::process::exit(1);
    }

    configure_git_global();
    configure_ssh_key();
    let selected_apps = select_apps();
    install_apps(&selected_apps);
    hide_dock();
    println!(
        "{}",
        style("¡Configuración completada! Los cambios en la terminal requieren reiniciar.").green()
    );
    restart_terminal();
}