//! Step 4 demo: modal prompts round-tripped from a worker thread.
//!
//! Run it from the workspace root:
//!     cargo run -p setup_core --example prompt_demo
//!
//! A worker thread asks a sequence mirroring the bash git/SSH flow (two text
//! fields, a yes/no, and the gh-account `[1/2/3]` choice). Each call blocks
//! until you answer the modal. Esc cancels a prompt (the worker gets `None`).
//! Answers are printed after the TUI is restored.

use std::sync::mpsc;
use std::thread;

use setup_core::prompt::{PromptRequest, Prompter};
use setup_core::{tui, ui};

fn main() -> anyhow::Result<()> {
    tui::install_panic_hook();
    let mut terminal = tui::init()?;

    let (tx, rx) = mpsc::channel::<PromptRequest>();

    let worker = thread::spawn(move || {
        let p = Prompter::new(tx);
        let name = p.text("Ingresa tu nombre para Git (e.g., Juan Pérez):");
        let email = p.text("Ingresa tu correo para Git (e.g., juan@example.com):");
        let overwrite = p.yes_no("Las credenciales ya existen. ¿Sobrescribir?", false);
        let account = p.choose(
            "¿A qué cuenta de GitHub quieres AÑADIR esta clave?",
            vec![
                "Usar la cuenta activa".into(),
                "Cambiar a otra cuenta ya autenticada (gh auth switch)".into(),
                "Iniciar sesión en otra cuenta (gh auth login)".into(),
            ],
        );
        (name, email, overwrite, account)
        // `p` (and its sender) drop here → serve_prompts sees Disconnected.
    });

    ui::serve_prompts(&mut terminal, &rx)?;
    let (name, email, overwrite, account) = worker.join().expect("worker panicked");

    tui::restore(&mut terminal)?;
    println!("Respuestas:");
    println!("  nombre      = {name:?}");
    println!("  correo      = {email:?}");
    println!("  sobrescribir = {overwrite:?}");
    println!("  cuenta (idx) = {account:?}");
    Ok(())
}
