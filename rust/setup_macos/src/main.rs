use console::{style, Term};
use dialoguer::{Confirm, Input, Select};
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
    pb.set_message(desc.to_string());
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

fn home() -> String {
    std::env::var("HOME").unwrap()
}

// Convierte una etiqueta libre en un slug seguro para nombre de archivo/host
fn slugify(label: &str) -> String {
    let s: String = label
        .to_lowercase()
        .replace(' ', "-")
        .chars()
        .filter(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == '-')
        .collect();
    if s.is_empty() { "cuenta".to_string() } else { s }
}

// ¿Existe ya un bloque "Host <alias>" en el contenido de ~/.ssh/config?
fn has_host_block(config: &str, alias: &str) -> bool {
    config.lines().any(|l| {
        let mut parts = l.split_whitespace();
        parts.next() == Some("Host") && parts.next() == Some(alias)
    })
}

fn append_to_ssh_config(content: &str) {
    let path = format!("{}/.ssh/config", home());
    let mut file = OpenOptions::new().create(true).append(true).open(&path).unwrap();
    file.write_all(content.as_bytes()).unwrap();
    use std::os::unix::fs::PermissionsExt;
    let _ = std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600));
}

// Configurar una o varias claves SSH para GitHub (tantas cuentas como quieras)
fn configure_ssh_key() -> bool {
    println!("{}", style("Configurando clave(s) SSH para GitHub...").yellow());
    if !Confirm::new()
        .with_prompt("¿Configurar clave(s) SSH para GitHub?")
        .default(true)
        .interact()
        .unwrap_or(false)
    {
        println!("{}", style("Saltando configuración de clave SSH.").yellow());
        return true;
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

    // Opciones globales de SSH en macOS (persistir claves en el llavero)
    create_dir_all(format!("{}/.ssh", home())).unwrap();
    let existing = std::fs::read_to_string(format!("{}/.ssh/config", home())).unwrap_or_default();
    if !existing.lines().any(|l| l.trim_end() == "Host *") {
        append_to_ssh_config("Host *\n    AddKeysToAgent yes\n    UseKeychain yes\n\n");
    }

    // Cuenta 1: personal (host por defecto github.com -> clonas como git@github.com:...)
    println!("\n{}", style("=== Cuenta 1: personal (host: github.com) ===").cyan());
    setup_github_account(
        "personal",
        &format!("{}/.ssh/id_ed25519", home()),
        "github.com",
        "github.com",
    );

    // Cuentas adicionales, en bucle (trabajo, clientes, GitHub Enterprise, etc.)
    let mut n = 2;
    while Confirm::new()
        .with_prompt("¿Configurar otra clave SSH para otra cuenta de GitHub?")
        .default(false)
        .interact()
        .unwrap_or(false)
    {
        let default_label = if n == 2 { "trabajo".to_string() } else { format!("cuenta{}", n) };
        let label: String = Input::new()
            .with_prompt("Etiqueta para esta cuenta (e.g., trabajo, cliente1)")
            .default(default_label)
            .interact_text()
            .unwrap_or_default();
        let safe = slugify(&label);

        // ¿github.com o GitHub Enterprise (otra URL)?
        let mut gh_host = "github.com".to_string();
        let choice = Select::new()
            .with_prompt("¿Esta cuenta es de github.com o de GitHub Enterprise con URL propia?")
            .items(&[
                "github.com (incluye cuentas gestionadas/EMU con login por SSO)",
                "GitHub Enterprise Server o data residency (otra URL, e.g. github.miempresa.com)",
            ])
            .default(0)
            .interact()
            .unwrap_or(0);
        if choice == 1 {
            let ent: String = Input::new()
                .with_prompt("Host de GitHub Enterprise (sin https://, e.g. github.miempresa.com)")
                .allow_empty(true)
                .interact_text()
                .unwrap_or_default();
            let ent = ent.trim().trim_start_matches("https://").trim_start_matches("http://");
            let ent = ent.split('/').next().unwrap_or("");
            if !ent.is_empty() {
                gh_host = ent.to_string();
            }
        }

        let alias = format!("github-{}", safe);
        println!(
            "\n{}",
            style(format!("=== Cuenta {}: {} (host alias: {} -> {}) ===", n, label, alias, gh_host)).cyan()
        );
        println!(
            "{}",
            style(format!("Para clonar repos de esta cuenta usa: git clone git@{}:org/repo.git", alias)).cyan()
        );
        setup_github_account(&label, &format!("{}/.ssh/id_ed25519_{}", home(), safe), &alias, &gh_host);
        n += 1;
    }

    println!(
        "{}",
        style(format!("Configuración de claves SSH completada ({} cuenta(s)).", n - 1)).green()
    );
    true
}

// Generar una clave ed25519 pidiendo el correo de la cuenta
fn generate_key(key_file: &str, label: &str) -> bool {
    let email: String = Input::new()
        .with_prompt(format!("Correo de GitHub para la cuenta '{}' (e.g., juan@example.com)", label))
        .allow_empty(true)
        .interact_text()
        .unwrap_or_default();
    if email.is_empty() {
        println!("{}", style(format!("No se proporcionó correo. Saltando cuenta '{}'.", label)).yellow());
        return false;
    }
    let ok = Command::new("ssh-keygen")
        .args(["-t", "ed25519", "-C", &email, "-f", key_file, "-N", ""])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);
    if ok {
        println!("{}", style(format!("Clave ed25519 generada para '{}'.", label)).green());
    } else {
        println!("{}", style("Error generando clave SSH.").red());
    }
    ok
}

// Generar/usar una clave SSH y vincularla a una cuenta de GitHub
//   host_alias — alias del Host en ~/.ssh/config (e.g. "github.com" o "github-trabajo")
fn setup_github_account(label: &str, key_file: &str, host_alias: &str, github_host: &str) {
    create_dir_all(format!("{}/.ssh", home())).unwrap();

    // Clave: reutilizar la existente o (re)generar
    if Path::new(key_file).exists() {
        println!("{}", style(format!("Ya existe una clave en {}.", key_file)).green());
        if Confirm::new()
            .with_prompt("¿Generar una nueva (sobrescribe la existente)?")
            .default(false)
            .interact()
            .unwrap_or(false)
        {
            let _ = std::fs::remove_file(key_file);
            let _ = std::fs::remove_file(format!("{}.pub", key_file));
            if !generate_key(key_file, label) {
                return;
            }
        } else {
            println!("{}", style(format!("Usando la clave existente para '{}'.", label)).yellow());
        }
    } else if !generate_key(key_file, label) {
        return;
    }

    // Añadir al agente, persistiendo en el llavero de macOS
    if Command::new("ssh-add")
        .args(["--apple-use-keychain", key_file])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
    {
        println!("{}", style("Clave añadida al agente (llavero de macOS).").green());
    } else {
        println!("{}", style("Advertencia: no se pudo añadir la clave al agente.").yellow());
    }

    // Bloque Host en ~/.ssh/config (idempotente)
    let existing = std::fs::read_to_string(format!("{}/.ssh/config", home())).unwrap_or_default();
    if has_host_block(&existing, host_alias) {
        println!("{}", style(format!("El host '{}' ya existe en ~/.ssh/config.", host_alias)).green());
    } else {
        append_to_ssh_config(&format!(
            "\nHost {}\n    HostName {}\n    User git\n    IdentityFile {}\n    IdentitiesOnly yes\n",
            host_alias, github_host, key_file
        ));
        println!(
            "{}",
            style(format!("Bloque Host '{}' (HostName {}) añadido a ~/.ssh/config.", host_alias, github_host)).green()
        );
    }

    add_ssh_key_to_github(key_file, host_alias, label, github_host);
}

// Login de la cuenta activa de gh para un host ("" si no hay sesión)
fn gh_active_login(host: &str) -> String {
    Command::new("gh")
        .args(["api", "user", "--jq", ".login"])
        .env("GH_HOST", host)
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_default()
}

fn gh_interactive(args: &[&str]) -> bool {
    Command::new("gh").args(args).status().map(|s| s.success()).unwrap_or(false)
}

// Obliga a ELEGIR la cuenta destino (no asume la activa) y pide confirmación
// final, por defecto NO, para no añadir la clave a la cuenta equivocada.
fn ensure_gh_account(label: &str, host: &str) -> bool {
    let active = gh_active_login(host);
    println!(
        "{}",
        style(format!("--- Cuenta de GitHub para la clave de '{}' (host: {}) ---", label, host)).cyan()
    );
    let first = if active.is_empty() {
        "Usar la cuenta activa (no hay ninguna: iniciará sesión)".to_string()
    } else {
        format!("Usar la cuenta activa ({})", active)
    };
    let choice = Select::new()
        .with_prompt("¿A qué cuenta de GitHub quieres AÑADIR esta clave?")
        .items(&[
            first.as_str(),
            "Cambiar a otra cuenta ya autenticada (gh auth switch)",
            "Iniciar sesión en otra cuenta (gh auth login)",
        ])
        .default(0)
        .interact()
        .unwrap_or(0);

    // --skip-ssh-key: que gh no suba id_ed25519 por su cuenta; la clave correcta la sube este script
    let login = ["auth", "login", "--hostname", host, "--git-protocol", "ssh", "--skip-ssh-key", "--scopes", "admin:public_key"];
    let ok = match choice {
        1 => gh_interactive(&["auth", "switch", "-h", host]),
        2 => gh_interactive(&login),
        _ if active.is_empty() => gh_interactive(&login),
        _ => true,
    };
    if !ok {
        println!("{}", style("No se pudo cambiar/iniciar sesión en GitHub CLI.").red());
        return false;
    }

    let active = gh_active_login(host);
    let shown = if active.is_empty() { "desconocida" } else { active.as_str() };
    Confirm::new()
        .with_prompt(format!(
            "La clave de '{}' se añadirá a la cuenta {} (host: {}). ¿Es la cuenta correcta?",
            label, shown, host
        ))
        .default(false)
        .interact()
        .unwrap_or(false)
}

// Asegurar el scope admin:public_key (necesario para `gh ssh-key add`)
fn ensure_gh_scope(host: &str) -> bool {
    let has_scope = Command::new("gh")
        .args(["auth", "status", "-h", host])
        .output()
        .map(|o| {
            String::from_utf8_lossy(&o.stdout).contains("admin:public_key")
                || String::from_utf8_lossy(&o.stderr).contains("admin:public_key")
        })
        .unwrap_or(false);
    has_scope || gh_interactive(&["auth", "refresh", "-h", host, "-s", "admin:public_key"])
}

// Añadir una clave SSH a la cuenta de GitHub elegida y probar la conexión por su alias
fn add_ssh_key_to_github(key_file: &str, host_alias: &str, label: &str, github_host: &str) -> bool {
    let public_key_path = format!("{}.pub", key_file);
    if !Path::new(&public_key_path).exists() {
        println!("{}", style(format!("No se encontró la clave pública SSH: {}", public_key_path)).red());
        return false;
    }

    if !ensure_gh_account(label, github_host) || !ensure_gh_scope(github_host) {
        println!("{}", style(format!("No se añadió la clave de '{}'.", label)).yellow());
        show_ssh_key_instructions(&public_key_path);
        return false;
    }

    let hostname = Command::new("hostname")
        .arg("-s")
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_else(|_| "MacBook".to_string());
    let title = format!("{}_{}_{}", hostname, host_alias, chrono::Local::now().format("%Y%m%d"));
    println!("{}", style(format!("Añadiendo clave SSH con título '{}'...", title)).yellow());
    let out = Command::new("gh")
        .args(["ssh-key", "add", &public_key_path, "--title", &title, "--type", "authentication"])
        .env("GH_HOST", github_host)
        .output()
        .expect("Error ejecutando gh");
    let msg = format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    if out.status.success() {
        println!("{}", style("Clave SSH añadida a GitHub.").green());
    } else if msg.to_lowercase().contains("already") {
        println!("{}", style("La clave ya estaba registrada en la cuenta. OK.").green());
    } else {
        println!("{}", style(format!("No se pudo añadir la clave: {}", msg.trim())).red());
        show_ssh_key_instructions(&public_key_path);
        return false;
    }

    println!("{}", style(format!("Probando conexión SSH (git@{})...", host_alias)).yellow());
    let output = Command::new("ssh")
        .args(["-T", "-o", "StrictHostKeyChecking=accept-new", &format!("git@{}", host_alias)])
        .output()
        .expect("Error probando SSH");
    let stderr = String::from_utf8_lossy(&output.stderr);
    if stderr.contains("successfully authenticated") {
        println!("{}", style(format!("Conexión verificada: {}", stderr.lines().next().unwrap_or("").trim())).green());
    } else {
        println!("{}", style("No se pudo verificar la conexión todavía. Revisa la clave en GitHub.").yellow());
    }
    true
}

fn show_ssh_key_instructions(public_key_path: &str) {
    if let Ok(public_key) = std::fs::read_to_string(public_key_path) {
        println!("{}", style("Clave pública SSH:").cyan());
        println!("{}", public_key.trim());
        println!("{}", style("\nInstrucciones:").cyan());
        println!("1. Copia la clave pública arriba.");
        println!("2. Ve a https://github.com/settings/keys");
        println!("3. Haz clic en 'New SSH key' o 'Add SSH key'.");
        println!("4. Pega la clave en el campo 'Key' y dale un título (e.g., 'MacBook').");
        println!("5. Haz clic en 'Add SSH key'.");
    } else {
        println!("{}", style("No se encontró la clave pública SSH.").red());
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
    let (Some(path_to_add), Some(executable)) = (&app.path, &app.executable) else {
        return;
    };

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

fn write_to_zshrc(description: &str, line: &str) {
    let zshrc_path = format!("{}/.zshrc", std::env::var("HOME").unwrap());
    let contents = std::fs::read_to_string(&zshrc_path).unwrap_or_default();
    if contents.contains(line) {
        println!(
            "{}",
            style(format!("{} ya está en ~/.zshrc.", description)).green()
        );
        return;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&zshrc_path)
        .unwrap();
    writeln!(file, "# Añadido por setup_macos - {}\n{}", description, line).unwrap();
    println!(
        "{}",
        style(format!("{} añadido a ~/.zshrc.", description)).green()
    );
}

fn post_install_config(name: &str) {
    match name {
        "eza" => {
            println!(
                "{}",
                style("Instalando FiraCode Nerd Font Mono...").yellow()
            );
            if !is_app_installed("font-fira-code-nerd-font", true) {
                run_command(
                    "brew install --cask font-fira-code-nerd-font",
                    "Instalando FiraCode Nerd Font Mono",
                );
            } else {
                println!("{}", style("FiraCode Nerd Font Mono ya instalada.").green());
            }
            write_to_zshrc("eza alias ls", "alias ls=\"eza --color=auto --icons\"");
            write_to_zshrc("eza alias ll", "alias ll=\"eza -lh --icons --git\"");
            write_to_zshrc("eza alias la", "alias la=\"eza -lah --icons --git\"");
            write_to_zshrc("eza alias lt", "alias lt=\"eza --tree --icons\"");
            println!(
                "{}",
                style("Nota: configura tu terminal para usar 'FiraCode Nerd Font Mono'.").cyan()
            );
        }
        "zoxide" => {
            write_to_zshrc("zoxide init", "eval \"$(zoxide init zsh)\"");
        }
        "mactop" => {
            println!(
                "{}",
                style("Nota: mactop requiere permisos elevados: sudo mactop").cyan()
            );
        }
        _ => {}
    }
}

fn build_categories() -> Vec<(String, Vec<App>)> {
    let mut categories: HashMap<String, Vec<App>> = HashMap::new();

    categories.insert(
        "Gestores de Paquetes".to_string(),
        vec![
            App { name: "pnpm".to_string(), command: "brew install pnpm".to_string(), cask: false, path: None, executable: None },
            App { name: "Bun".to_string(), command: "brew install oven-sh/bun/bun".to_string(), cask: false, path: None, executable: None },
            App { name: "Yarn".to_string(), command: "brew install yarn".to_string(), cask: false, path: None, executable: None },
            App { name: "Node".to_string(), command: "brew install node".to_string(), cask: false, path: None, executable: None },
        ],
    );
    categories.insert(
        "Herramientas de Contenedores".to_string(),
        vec![
            App { name: "Docker".to_string(), command: "brew install --cask docker".to_string(), cask: true, path: None, executable: None },
            App { name: "kubectl".to_string(), command: "brew install kubectl".to_string(), cask: false, path: None, executable: None },
            App { name: "Minikube".to_string(), command: "brew install minikube".to_string(), cask: false, path: None, executable: None },
        ],
    );
    categories.insert(
        "IDEs y Editores".to_string(),
        vec![
            App { name: "Visual Studio Code".to_string(), command: "brew install --cask visual-studio-code".to_string(), cask: true, path: None, executable: None },
            App { name: "Cursor".to_string(), command: "brew install --cask cursor".to_string(), cask: true, path: None, executable: None },
            App { name: "IntelliJ IDEA".to_string(), command: "brew install --cask intellij-idea".to_string(), cask: true, path: None, executable: None },
            App { name: "WebStorm".to_string(), command: "brew install --cask webstorm".to_string(), cask: true, path: None, executable: None },
        ],
    );
    categories.insert(
        "Navegadores".to_string(),
        vec![
            App { name: "Google Chrome".to_string(), command: "brew install --cask google-chrome".to_string(), cask: true, path: None, executable: None },
            App { name: "Brave".to_string(), command: "brew install --cask brave-browser".to_string(), cask: true, path: None, executable: None },
            App { name: "Opera".to_string(), command: "brew install --cask opera".to_string(), cask: true, path: None, executable: None },
            App { name: "Firefox".to_string(), command: "brew install --cask firefox".to_string(), cask: true, path: None, executable: None },
        ],
    );
    categories.insert(
        "Terminales".to_string(),
        vec![
            App { name: "iTerm2".to_string(), command: "brew install --cask iterm2".to_string(), cask: true, path: None, executable: None },
            App { name: "Warp".to_string(), command: "brew install --cask warp".to_string(), cask: true, path: None, executable: None },
        ],
    );
    categories.insert(
        "Lenguajes de Programación".to_string(),
        vec![
            App { name: "Python".to_string(), command: "brew install python".to_string(), cask: false, path: Some("/opt/homebrew/bin".to_string()), executable: Some("python3".to_string()) },
            App { name: "Java".to_string(), command: "brew install java".to_string(), cask: false, path: Some("/opt/homebrew/opt/openjdk/bin".to_string()), executable: Some("java".to_string()) },
            App { name: "Rust".to_string(), command: "brew install rust".to_string(), cask: false, path: Some("/opt/homebrew/bin".to_string()), executable: Some("rustc".to_string()) },
            App { name: "C++ (clang)".to_string(), command: "brew install llvm".to_string(), cask: false, path: Some("/opt/homebrew/opt/llvm/bin".to_string()), executable: Some("clang++".to_string()) },
            App { name: "C# (Mono)".to_string(), command: "brew install mono".to_string(), cask: false, path: Some("/opt/homebrew/bin".to_string()), executable: Some("mono".to_string()) },
            App { name: "Go".to_string(), command: "brew install go".to_string(), cask: false, path: Some("/opt/homebrew/bin".to_string()), executable: Some("go".to_string()) },
            App { name: "Ruby".to_string(), command: "brew install ruby".to_string(), cask: false, path: Some("/opt/homebrew/bin".to_string()), executable: Some("ruby".to_string()) },
            App { name: "PHP".to_string(), command: "brew install php".to_string(), cask: false, path: Some("/opt/homebrew/bin".to_string()), executable: Some("php".to_string()) },
            App { name: "TypeScript".to_string(), command: "brew install typescript".to_string(), cask: false, path: Some("/opt/homebrew/bin".to_string()), executable: Some("tsc".to_string()) },
        ],
    );
    categories.insert(
        "Bases de Datos".to_string(),
        vec![
            App { name: "PostgreSQL".to_string(), command: "brew install postgresql".to_string(), cask: false, path: None, executable: None },
            App { name: "MySQL".to_string(), command: "brew install mysql".to_string(), cask: false, path: None, executable: None },
            App { name: "MongoDB".to_string(), command: "brew install mongodb-community".to_string(), cask: false, path: None, executable: None },
        ],
    );
    categories.insert(
        "Herramientas CLI".to_string(),
        vec![
            App { name: "eza".to_string(), command: "brew install eza".to_string(), cask: false, path: None, executable: None },
            App { name: "mactop".to_string(), command: "brew install mactop".to_string(), cask: false, path: None, executable: None },
            App { name: "zoxide".to_string(), command: "brew install zoxide".to_string(), cask: false, path: None, executable: None },
            App { name: "btop".to_string(), command: "brew install btop".to_string(), cask: false, path: None, executable: None },
            App { name: "ranger".to_string(), command: "brew install ranger".to_string(), cask: false, path: None, executable: None },
            App { name: "fzf".to_string(), command: "brew install fzf".to_string(), cask: false, path: None, executable: None },
        ],
    );
    categories.insert(
        "Otros".to_string(),
        vec![
            App { name: "Raycast".to_string(), command: "brew install raycast".to_string(), cask: false, path: None, executable: None },
            App { name: "Telegram".to_string(), command: "brew install --cask telegram".to_string(), cask: true, path: None, executable: None },
            App { name: "Slack".to_string(), command: "brew install --cask slack".to_string(), cask: true, path: None, executable: None },
            App { name: "Tailscale".to_string(), command: "brew install tailscale".to_string(), cask: false, path: None, executable: None },
            App { name: "GitHub CLI (gh)".to_string(), command: "brew install gh".to_string(), cask: false, path: None, executable: None },
            App { name: "Obsidian".to_string(), command: "brew install --cask obsidian".to_string(), cask: true, path: None, executable: None },
            App { name: "Notion".to_string(), command: "brew install --cask notion".to_string(), cask: true, path: None, executable: None },
        ],
    );

    // Sort categories for consistent ordering
    let mut sorted: Vec<(String, Vec<App>)> = categories.into_iter().collect();
    sorted.sort_by(|a, b| a.0.cmp(&b.0));
    sorted
}

fn select_apps() -> Vec<App> {
    let categories = build_categories();
    let mut selected_apps = vec![];
    println!(
        "{}",
        style("Selecciona las aplicaciones a instalar por categoría:").cyan()
    );

    for (category, apps) in &categories {
        println!("\n{}", style(format!("Categoría: {}", category)).blue());
        let mut table = Table::new();
        table.add_row(row!["ID", "Aplicación", "Estado"]);
        for (i, app) in apps.iter().enumerate() {
            let package_name = app.command.split_whitespace().last().unwrap_or("");
            let status = if is_app_installed(package_name, app.cask) {
                style("instalado").green().to_string()
            } else {
                String::new()
            };
            table.add_row(row![format!("[{}]", i + 1), app.name, status]);
        }
        table.printstd();

        let choices: String = Input::<String>::new()
            .with_prompt("Ingresa los números (ej. 1,3,5), 'all', '0' o 'n' para omitir")
            .allow_empty(true)
            .interact_text()
            .unwrap_or_default()
            .to_lowercase();

        if choices == "all" {
            selected_apps.extend(apps.clone());
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
        println!("{}", style("No se seleccionaron aplicaciones.").yellow());
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
        let package_name = app.command.split_whitespace().last().unwrap_or("");
        if is_app_installed(package_name, app.cask) {
            println!(
                "{}",
                style(format!("{} ya está instalado.", app.name)).green()
            );
            add_to_path(app);
            post_install_config(&app.name);
            continue;
        }
        println!("{}", style(format!("Instalando {}...", app.name)).yellow());
        if run_command(&app.command, &format!("Instalando {}", app.name)) {
            add_to_path(app);
            post_install_config(&app.name);
        } else {
            println!(
                "{}",
                style(format!("Error instalando {}.", app.name)).red()
            );
        }
    }
}

fn clean_zshrc() {
    let zshrc_path = format!("{}/.zshrc", std::env::var("HOME").unwrap());
    run_command(
        &format!("sed -i '' '/# Añadido por setup_macos/{{ N; d; }}' {}", zshrc_path),
        "Limpiando entradas de ~/.zshrc",
    );
    run_command(
        "sed -i '' 's/ZSH_THEME=\"powerlevel10k\\/powerlevel10k\"/ZSH_THEME=\"robbyrussell\"/' ~/.zshrc",
        "Restaurando ZSH_THEME",
    );
    run_command(
        "sed -i '' 's/plugins=(git jump zsh-autosuggestions zsh-history-substring-search jsontools zsh-syntax-highlighting zsh-interactive-cd)/plugins=(git)/' ~/.zshrc",
        "Restaurando plugins",
    );
    println!("{}", style("~/.zshrc limpiado.").green());
}

fn clean_ssh_config() {
    let ssh_config = format!("{}/.ssh/config", std::env::var("HOME").unwrap());
    if Path::new(&ssh_config).exists() {
        // Elimina bloques "Host github.com" y cualquier "Host github-*" (5 líneas cada uno)
        run_command(
            &format!(
                "sed -i '' -e '/^Host github\\.com$/{{N;N;N;N;d;}}' -e '/^Host github-/{{N;N;N;N;d;}}' {}",
                ssh_config
            ),
            "Eliminando entradas de GitHub en ~/.ssh/config",
        );
        println!("{}", style("Entradas de GitHub eliminadas de ~/.ssh/config.").green());
    }
}

fn uninstall() {
    println!("{}", style("Modo de desinstalación").cyan());

    if Confirm::new()
        .with_prompt("¿Desinstalar Oh My Zsh, Powerlevel10k y plugins?")
        .default(true)
        .interact()
        .unwrap_or(false)
    {
        let omz_path = format!("{}/.oh-my-zsh", std::env::var("HOME").unwrap());
        if Path::new(&omz_path).exists() {
            run_command(&format!("rm -rf {}", omz_path), "Eliminando Oh My Zsh");
            println!("{}", style("Oh My Zsh eliminado.").green());
        } else {
            println!("{}", style("Oh My Zsh no está instalado.").yellow());
        }
        let p10k = format!("{}/.p10k.zsh", std::env::var("HOME").unwrap());
        run_command(&format!("rm -f {}", p10k), "Eliminando configuración de Powerlevel10k");
        clean_zshrc();
    }

    if Confirm::new()
        .with_prompt("¿Eliminar claves SSH de GitHub (~/.ssh/id_ed25519*)?")
        .default(false)
        .interact()
        .unwrap_or(false)
    {
        let home = std::env::var("HOME").unwrap();
        run_command(
            &format!("rm -f {}/.ssh/id_ed25519 {}/.ssh/id_ed25519.pub {}/.ssh/id_ed25519_*", home, home, home),
            "Eliminando clave SSH",
        );
        clean_ssh_config();
        println!("{}", style("Clave SSH eliminada.").green());
    }

    if Confirm::new()
        .with_prompt("¿Eliminar el cheatsheet generado (~/.cheatsheet_macos_setup.md)?")
        .default(true)
        .interact()
        .unwrap_or(false)
    {
        let cheatsheet = format!("{}/cheatsheet_macos_setup.md", std::env::var("HOME").unwrap());
        run_command(&format!("rm -f {}", cheatsheet), "Eliminando cheatsheet");
    }

    if Confirm::new()
        .with_prompt("¿Desinstalar aplicaciones instaladas por este script?")
        .default(true)
        .interact()
        .unwrap_or(false)
    {
        let selected_apps = select_apps();
        for app in &selected_apps {
            let package_name = app.command.split_whitespace().last().unwrap_or("");
            let cmd = if app.cask {
                format!("brew uninstall --cask {}", package_name)
            } else {
                format!("brew uninstall {}", package_name)
            };
            if !run_command(&cmd, &format!("Desinstalando {}", app.name)) {
                println!(
                    "{}",
                    style(format!("No se pudo desinstalar {}.", app.name)).yellow()
                );
            }
        }
    }

    println!("{}", style("Desinstalación completada.").green());
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
        println!("{}", style("El Dock permanecerá visible.").green());
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
    println!();

    let options = vec!["Instalar y configurar", "Desinstalar"];
    let selection = Select::new()
        .with_prompt("¿Qué deseas hacer?")
        .items(&options)
        .default(0)
        .interact()
        .unwrap_or(0);

    match selection {
        1 => {
            uninstall();
        }
        _ => {
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
                style("¡Configuración completada! Los cambios en la terminal requieren reiniciar.")
                    .green()
            );
            restart_terminal();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ssh_helpers() {
        assert_eq!(slugify("Mi Trabajo!"), "mi-trabajo");
        assert_eq!(slugify("***"), "cuenta");
        let cfg = "Host github.com\n    HostName github.com\nHost github-work\n";
        assert!(has_host_block(cfg, "github-work"));
        assert!(!has_host_block(cfg, "github-wor"));
        assert!(!has_host_block(cfg, "github-trabajo"));
    }
}
