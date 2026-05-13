//! Terminal lifecycle for the Ratatui UI.
//!
//! Responsibilities:
//! - [`init`] / [`restore`] — enter and leave the alternate screen + raw mode.
//! - [`install_panic_hook`] — guarantee the terminal is restored even on panic,
//!   so a crash never leaves the user stuck in a garbled raw-mode terminal.
//! - [`suspend`] — temporarily drop out of the TUI to hand the real terminal to
//!   an interactive child process, then restore the TUI. This is required for
//!   `gh auth login` (browser + prompts), `p10k configure` (full-screen wizard),
//!   and the final `exec zsh -l`, none of which can run inside raw mode.

use std::io::{self, Stdout};

use anyhow::Result;
use crossterm::{
    event::{DisableMouseCapture, EnableMouseCapture},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};

/// The concrete terminal type used throughout the UI.
pub type Tui = Terminal<CrosstermBackend<Stdout>>;

/// Enter raw mode + the alternate screen and return a ready-to-draw terminal.
pub fn init() -> Result<Tui> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    let mut terminal = Terminal::new(CrosstermBackend::new(stdout))?;
    terminal.clear()?;
    Ok(terminal)
}

/// Leave the alternate screen + raw mode and show the cursor again.
///
/// Call this on the normal exit path. The panic hook covers the crash path.
pub fn restore(terminal: &mut Tui) -> Result<()> {
    leave()?;
    terminal.show_cursor()?;
    Ok(())
}

/// Run an interactive child with the real terminal, then restore the TUI.
///
/// The closure runs with raw mode disabled and the alternate screen left, so a
/// child process spawned with inherited stdio owns the terminal normally. When
/// the closure returns, the TUI is re-entered and cleared.
pub fn suspend<F, T>(terminal: &mut Tui, f: F) -> Result<T>
where
    F: FnOnce() -> T,
{
    leave()?;
    terminal.show_cursor()?;

    let result = f();

    enable_raw_mode()?;
    execute!(terminal.backend_mut(), EnterAlternateScreen, EnableMouseCapture)?;
    terminal.clear()?;
    Ok(result)
}

/// Install a panic hook that restores the terminal before printing the panic.
///
/// Without this, a panic while in raw mode leaves the user's terminal unusable.
pub fn install_panic_hook() {
    let original = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        // Best-effort restore; ignore errors since we're already panicking.
        let _ = leave();
        original(info);
    }));
}

/// Shared teardown: disable raw mode and leave the alternate screen.
fn leave() -> Result<()> {
    disable_raw_mode()?;
    execute!(io::stdout(), LeaveAlternateScreen, DisableMouseCapture)?;
    Ok(())
}
