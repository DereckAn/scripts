//! Step 2 demo: main menu + two-panel app selection.
//!
//! Run it from the workspace root:
//!     cargo run -p setup_core --example select_demo
//!
//! Navigation: [↑↓] move, [Tab] switch panel, [Space] toggle, [A] select-all,
//! [Enter] confirm, [Esc/Q] back, [q] quit from the menu. On confirm it prints
//! the chosen action and the ticked apps — proving selection state is correct.

use setup_core::model::{AppEntry, Category, CheckKind, InstallSpec};
use setup_core::tui;
use setup_core::ui::{self, App, Screen};

fn cask(name: &str, token: &str, installed: bool) -> AppEntry {
    AppEntry::new(
        name,
        InstallSpec::Cask {
            token: token.into(),
        },
    )
    .installed(installed)
}

fn brew(name: &str, formula: &str, installed: bool) -> AppEntry {
    AppEntry::new(
        name,
        InstallSpec::Brew {
            formula: formula.into(),
        },
    )
    .with_check(CheckKind::Executable(formula.into()))
    .installed(installed)
}

/// A hardcoded subset of the macOS catalog (real catalog lands in `apps.rs`).
fn sample_catalog() -> Vec<Category> {
    vec![
        Category::new(
            "IDEs y Editores",
            vec![
                cask("Visual Studio Code", "visual-studio-code", true),
                cask("Cursor", "cursor", false),
                cask("IntelliJ IDEA", "intellij-idea", false),
                cask("WebStorm", "webstorm", false),
            ],
        ),
        Category::new(
            "Navegadores",
            vec![
                cask("Google Chrome", "google-chrome", true),
                cask("Brave", "brave-browser", false),
                cask("Firefox", "firefox", false),
            ],
        ),
        Category::new(
            "Lenguajes",
            vec![
                brew("Python", "python", true),
                brew("Go", "go", false),
                brew("Rust", "rust", false),
                brew("Ruby", "ruby", false),
            ],
        ),
        Category::new(
            "Herramientas CLI",
            vec![
                brew("eza", "eza", false),
                brew("zoxide", "zoxide", false),
                brew("btop", "btop", false),
                brew("fzf", "fzf", false),
            ],
        ),
    ]
}

fn main() -> anyhow::Result<()> {
    tui::install_panic_hook();
    let mut terminal = tui::init()?;
    let mut app = App::new(sample_catalog());

    let result = ui::run(&mut terminal, &mut app);

    tui::restore(&mut terminal)?;
    result?;

    match app.screen {
        Screen::Confirmed => {
            let selected = app.selected_apps();
            println!("Action: {:?}", app.action);
            println!("Confirmed {} app(s):", selected.len());
            for a in selected {
                println!("  - {}", a.name);
            }
        }
        _ => println!("Cancelled — nothing to do."),
    }
    Ok(())
}
