//! Step 3 demo: live install log with streamed output + progress gauge.
//!
//! Run it from the workspace root:
//!     cargo run -p setup_core --example install_log_demo
//!
//! A worker thread runs a fake multi-step job (with real `sleep`s so you can see
//! output stream in, and one deliberately failing step to show the ✗ path). The
//! UI thread drains events each frame, animates the spinner, and fills the
//! progress bar. Press [q]/[Esc]/[Enter] once it reports completion.

use std::sync::mpsc;
use std::thread;

use setup_core::model::InstallEvent;
use setup_core::{runner, tui, ui};

fn main() -> anyhow::Result<()> {
    tui::install_panic_hook();
    let mut terminal = tui::init()?;

    let (tx, rx) = mpsc::channel();

    // Fake job: (step description, shell command). `2>&1` is added by the runner.
    let worker = thread::spawn(move || {
        let steps: Vec<(&str, &str)> = vec![
            ("Verificando Homebrew", "sleep 0.3; echo 'Homebrew 4.x detectado'"),
            ("Verificando Git", "sleep 0.2; echo 'git version 2.x'"),
            (
                "Instalando Visual Studio Code",
                "for i in 1 2 3 4; do echo \"  descargando capa $i/4\"; sleep 0.25; done",
            ),
            ("Instalando eza", "echo '  pouring eza'; sleep 0.4; echo '  linking binaries'"),
            (
                "Instalando paquete-roto",
                "echo '  resolviendo dependencias'; sleep 0.3; echo 'Error: No such formula' >&2; exit 1",
            ),
            ("Instalando zoxide", "echo '  pouring zoxide'; sleep 0.3; echo '  done'"),
        ];

        let total = steps.len();
        for (i, (desc, cmd)) in steps.iter().enumerate() {
            tx.send(InstallEvent::StepStarted {
                index: i + 1,
                total,
                desc: (*desc).to_string(),
            })
            .ok();
            let ok = runner::stream_command(cmd, &tx);
            tx.send(InstallEvent::StepFinished { ok }).ok();
        }
        tx.send(InstallEvent::Done).ok();
    });

    let result = ui::run_log(&mut terminal, &rx, "Instalando");

    let _ = worker.join();
    tui::restore(&mut terminal)?;
    result?;

    println!("Install-log demo finished.");
    Ok(())
}
