//! `setup_core` — shared TUI and setup logic for the per-OS setup binaries.
//!
//! - [`tui`] — terminal lifecycle: init/restore, panic hook, and `suspend()` for
//!   interactive subprocesses (`gh auth login`, `p10k configure`, `exec zsh`).
//! - [`model`] — the app catalog data model (replaces the bash `:`-delimited
//!   strings).
//! - [`ui`] — Ratatui screens + state machine (main menu, two-panel selection,
//!   live install log).
//! - [`runner`] — run install commands while streaming their output to the UI.
//! - [`prompt`] — modal prompts (Text/YesNo/Choice) that replace bash `read`,
//!   round-tripped from the worker thread to the UI over channels.
//!
//! Later steps add `shell`, `ssh`, and the `platform` trait that the per-OS
//! binaries implement.

pub mod model;
pub mod prompt;
pub mod runner;
pub mod tui;
pub mod ui;
