//! Core data model for the setup catalog.
//!
//! This replaces the `:`-delimited strings the bash scripts pass around
//! (`name:cmd:cask:path:executable`). Each binary's `apps.rs` builds a
//! `Vec<Category>` of these; the shared UI and installer consume them.
//!
//! Step 2 uses only the fields needed to render and select. `InstallSpec`
//! starts with the macOS (Homebrew) variants; Linux/Windows variants land in
//! their respective steps.

/// How an app is installed on a given platform.
#[derive(Debug, Clone)]
pub enum InstallSpec {
    /// Homebrew formula, e.g. `eza`.
    Brew { formula: String },
    /// Homebrew cask, e.g. `visual-studio-code`.
    Cask { token: String },
}

/// How to tell whether an app is already installed.
#[derive(Debug, Clone)]
pub enum CheckKind {
    /// Present in the package manager's installed list.
    Package,
    /// This executable resolves on `$PATH`.
    Executable(String),
}

/// A single installable application.
#[derive(Debug, Clone)]
pub struct AppEntry {
    pub name: String,
    pub install: InstallSpec,
    /// Optional `(path_to_add, executable)` to append to the shell rc `PATH`.
    pub path_export: Option<(String, String)>,
    pub check: CheckKind,
    /// Whether the user has ticked this app in the selection screen.
    pub selected: bool,
    /// Whether it is already installed (computed at startup by the platform;
    /// the Step 2 demo sets it by hand).
    pub installed: bool,
}

impl AppEntry {
    pub fn new(name: impl Into<String>, install: InstallSpec) -> Self {
        Self {
            name: name.into(),
            install,
            path_export: None,
            check: CheckKind::Package,
            selected: false,
            installed: false,
        }
    }

    pub fn with_check(mut self, check: CheckKind) -> Self {
        self.check = check;
        self
    }

    pub fn with_path(mut self, path: impl Into<String>, exe: impl Into<String>) -> Self {
        self.path_export = Some((path.into(), exe.into()));
        self
    }

    pub fn installed(mut self, yes: bool) -> Self {
        self.installed = yes;
        self
    }
}

/// Messages emitted by the install worker thread and consumed by the log UI.
///
/// The worker runs the job on its own thread and sends these over an
/// `mpsc::channel`; the UI thread drains them each tick to update the log and
/// progress bar without ever blocking on a subprocess.
#[derive(Debug, Clone)]
pub enum InstallEvent {
    /// A new step began. `index` is 1-based; `total` is the step count.
    StepStarted {
        index: usize,
        total: usize,
        desc: String,
    },
    /// One line of merged stdout/stderr from the running step.
    Line(String),
    /// The current step finished (`ok` = exit code 0).
    StepFinished { ok: bool },
    /// The whole job is complete.
    Done,
}

/// A named group of apps shown together in the selection screen.
#[derive(Debug, Clone)]
pub struct Category {
    pub title: String,
    pub apps: Vec<AppEntry>,
}

impl Category {
    pub fn new(title: impl Into<String>, apps: Vec<AppEntry>) -> Self {
        Self {
            title: title.into(),
            apps,
        }
    }
}
