//! The OS seam: everything platform-specific behind one trait.
//!
//! `setup_core` (UI, shell, ssh, runner) is OS-agnostic; each binary
//! (`setup_macos` / `setup_linux` / `setup_windows`) provides a `Platform` impl
//! plus an app catalog. The install worker runs on a background thread and only
//! holds a `&dyn Platform`, hence the `Send + Sync` bound.
//!
//! Implementations land per OS in later steps (macOS in Step 5c). This module
//! defines the contract.

use std::sync::mpsc::Sender;

use crate::model::{AppEntry, Category, InstallEvent};
use crate::prompt::Prompter;

pub trait Platform: Send + Sync {
    /// Human-readable name shown in the UI (e.g. "macOS").
    fn display_name(&self) -> &str;

    /// Ensure base prerequisites exist (Homebrew + Git on macOS; the package
    /// manager + zsh on Linux; winget/scoop on Windows). Streams progress and
    /// may prompt. Returns `false` to abort the run.
    fn ensure_prereqs(&self, tx: &Sender<InstallEvent>, prompter: &Prompter) -> bool;

    /// The full app catalog for this platform, grouped by category.
    fn catalog(&self) -> Vec<Category>;

    /// Mark `installed` on every app in `categories` (queries the package
    /// manager / `$PATH`). Done once up front so the selection screen is fast.
    fn refresh_installed(&self, categories: &mut [Category]);

    /// Install one app, streaming its output. Returns `true` on success.
    fn install(&self, app: &AppEntry, tx: &Sender<InstallEvent>) -> bool;

    /// Uninstall one app, streaming its output. Returns `true` on success.
    fn uninstall(&self, app: &AppEntry, tx: &Sender<InstallEvent>) -> bool;

    /// Per-tool post-install configuration (eza aliases, zoxide init, …).
    fn post_install(&self, app: &AppEntry, tx: &Sender<InstallEvent>);
}
