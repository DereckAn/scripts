//! Step 1 smoke test for `setup_core::tui`.
//!
//! Run it from the workspace root:
//!     cargo run -p setup_core --example tui_smoke
//!
//! Proves three things end to end:
//!   1. The terminal enters/leaves the alternate screen cleanly.
//!   2. `suspend()` hands the real terminal to an interactive child (`less`)
//!      and restores the TUI afterwards — the mechanism `gh auth login` and
//!      `p10k configure` will use later.
//!   3. The panic hook leaves the terminal usable even on a forced panic ([p]).

use std::process::Command;
use std::time::Duration;

use crossterm::event::{self, Event, KeyCode};
use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
};
use setup_core::tui;

fn main() -> anyhow::Result<()> {
    tui::install_panic_hook();
    let mut terminal = tui::init()?;

    let mut suspends = 0u32;
    loop {
        terminal.draw(|f| {
            let body = vec![
                Line::from(Span::styled(
                    "setup_core — Step 1 TUI smoke test",
                    Style::default()
                        .fg(Color::Cyan)
                        .add_modifier(Modifier::BOLD),
                )),
                Line::from(""),
                Line::from("[s] suspend → open `less` on a directory listing, then return"),
                Line::from("[p] force a panic (the terminal must still be usable after)"),
                Line::from("[q] / [Esc] quit"),
                Line::from(""),
                Line::from(format!("suspend() round-trips so far: {suspends}")),
            ];
            f.render_widget(
                Paragraph::new(body)
                    .block(Block::default().borders(Borders::ALL).title(" Step 1 ")),
                f.area(),
            );
        })?;

        if event::poll(Duration::from_millis(100))? {
            if let Event::Key(key) = event::read()? {
                match key.code {
                    KeyCode::Char('q') | KeyCode::Esc => break,
                    KeyCode::Char('p') => panic!("forced panic to test the restore hook"),
                    KeyCode::Char('s') => {
                        tui::suspend(&mut terminal, || {
                            let _ = Command::new("sh")
                                .arg("-c")
                                .arg("echo 'Suspended into a child process. Press q to exit less.'; ls -la | less")
                                .status();
                        })?;
                        suspends += 1;
                    }
                    _ => {}
                }
            }
        }
    }

    tui::restore(&mut terminal)?;
    println!("TUI restored cleanly after {suspends} suspend round-trip(s).");
    Ok(())
}
