//! Managing the user's `.zshrc` — a faithful port of the bash shell logic.
//!
//! Mirrors `apps/setup_macos.sh`:
//! - `resolve_user_zshrc` → [`resolve_zshrc`] (Terax / VS Code `$ZDOTDIR`).
//! - the idempotent managed block (`# >>> setup … >>>`) → [`write_managed_block`]
//!   / [`remove_managed_block`].
//! - `write_to_zshrc` / `add_to_path` → [`append_line_once`] / [`ensure_path_export`].
//! - `clean_zshrc` heredity sweep → [`clean`].
//!
//! All the real logic lives in pure string functions (tested below); the public
//! functions are thin `std::fs` wrappers. No `sed`, so it is portable and
//! testable without spawning a shell.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

/// Canonical managed-block markers written by this tool.
const BLOCK_START: &str = "# >>> setup (Oh My Zsh + Powerlevel10k) >>>";
const BLOCK_END: &str = "# <<< setup (Oh My Zsh + Powerlevel10k) <<<";

// ---------------------------------------------------------------------------
// Resolving the real .zshrc
// ---------------------------------------------------------------------------

/// Resolve the user's real `.zshrc` from the process environment.
///
/// See [`resolve_from`] for the rules; this just feeds it `std::env`.
pub fn resolve_zshrc() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_default();
    resolve_from(&|k| std::env::var(k).ok(), &home)
}

/// Pure core of [`resolve_zshrc`]: pick the rc path from an env getter + `$HOME`.
///
/// Most terminals don't touch `$ZDOTDIR`, so the rc is `~/.zshrc`. Terax and the
/// VS Code/Cursor/Trae integrated terminals redirect `$ZDOTDIR` to an ephemeral
/// dir and point at the real rc via `TERAX_USER_ZDOTDIR` / `USER_ZDOTDIR`.
fn resolve_from(get: &dyn Fn(&str) -> Option<String>, home: &str) -> PathBuf {
    let nonempty = |k: &str| get(k).filter(|s| !s.is_empty());
    let is_set = |k: &str| nonempty(k).is_some();

    let zdot = nonempty("ZDOTDIR").unwrap_or_else(|| home.to_string());

    // Normal case: $ZDOTDIR not redirected.
    if zdot == home {
        return rc_in(home);
    }

    // Terax → TERAX_USER_ZDOTDIR (fallback $HOME).
    if is_set("TERAX_TERMINAL") || zdot.contains("/terax/") {
        let base = nonempty("TERAX_USER_ZDOTDIR").unwrap_or_else(|| home.to_string());
        return rc_in(&base);
    }

    // VS Code / Cursor / Trae and forks → USER_ZDOTDIR (fallback $HOME).
    let term = get("TERM_PROGRAM").unwrap_or_default();
    if is_set("USER_ZDOTDIR")
        || is_set("VSCODE_INJECTION")
        || matches!(term.as_str(), "vscode" | "cursor" | "trae")
    {
        let base = nonempty("USER_ZDOTDIR").unwrap_or_else(|| home.to_string());
        return rc_in(&base);
    }

    // A $ZDOTDIR the user set deliberately → respect it.
    rc_in(&zdot)
}

fn rc_in(dir: &str) -> PathBuf {
    Path::new(dir).join(".zshrc")
}

// ---------------------------------------------------------------------------
// Managed block (idempotent)
// ---------------------------------------------------------------------------

/// (Re)write the managed Oh My Zsh + Powerlevel10k block in `rc`, idempotently.
pub fn write_managed_block(rc: &Path, plugins_line: &str) -> io::Result<()> {
    let existing = fs::read_to_string(rc).unwrap_or_default();
    fs::write(rc, build_managed_block(&existing, plugins_line))
}

/// Remove the managed block from `rc` (no-op if the file or block is absent).
pub fn remove_managed_block(rc: &Path) -> io::Result<()> {
    if !rc.exists() {
        return Ok(());
    }
    let content = fs::read_to_string(rc)?;
    fs::write(rc, strip_block(&content))
}

/// Strip any managed block from `existing`, then append a fresh one.
fn build_managed_block(existing: &str, plugins_line: &str) -> String {
    // Normalize trailing newlines so rewriting is idempotent (stripping a prior
    // block leaves its separator blank line behind, which would otherwise
    // accumulate on every rewrite).
    let base = strip_block(existing);
    let base = base.trim_end_matches('\n');
    let mut out = String::new();
    if !base.is_empty() {
        out.push_str(base);
        out.push('\n'); // terminate the last user line
    }
    out.push('\n'); // blank separator before the managed block
    for line in [
        BLOCK_START,
        r#"export ZSH="$HOME/.oh-my-zsh""#,
        r#"ZSH_THEME="powerlevel10k/powerlevel10k""#,
        plugins_line,
        r#"source "$ZSH/oh-my-zsh.sh""#,
        r#"# `p10k configure` escribe la config en ${ZDOTDIR:-$HOME}/.p10k.zsh"#,
        r#"[[ ! -f "${ZDOTDIR:-$HOME}/.p10k.zsh" ]] || source "${ZDOTDIR:-$HOME}/.p10k.zsh""#,
        BLOCK_END,
    ] {
        out.push_str(line);
        out.push('\n');
    }
    out
}

/// Remove the lines between (and including) any `# >>> setup … >>>` /
/// `# <<< setup … <<<` markers. Matches blocks written by this tool *and* by
/// the legacy bash scripts (`setup_macos.sh` / `setup_linux.sh`).
fn strip_block(content: &str) -> String {
    let mut out = String::new();
    let mut in_block = false;
    for line in content.lines() {
        if line.starts_with("# >>> setup") && line.contains(">>>") {
            in_block = true;
            continue;
        }
        if line.starts_with("# <<< setup") && line.contains("<<<") {
            in_block = false;
            continue;
        }
        if !in_block {
            out.push_str(line);
            out.push('\n');
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Single-line helpers (write_to_zshrc / add_to_path)
// ---------------------------------------------------------------------------

/// Append `line` (preceded by a `# … {description}` comment) to `rc` unless it
/// is already present. Returns `true` if it was added.
pub fn append_line_once(rc: &Path, description: &str, line: &str) -> io::Result<bool> {
    let content = fs::read_to_string(rc).unwrap_or_default();
    let (new, added) = append_once(&content, description, line);
    if added {
        fs::write(rc, new)?;
    }
    Ok(added)
}

/// Append a `PATH` export for `path_to_add` to `rc` unless already present.
/// Returns `true` if it was added. (The caller checks `$PATH` first.)
pub fn ensure_path_export(rc: &Path, path_to_add: &str) -> io::Result<bool> {
    let line = path_export_line(path_to_add);
    append_line_once(rc, "PATH", &line)
}

fn path_export_line(path_to_add: &str) -> String {
    format!(r#"export PATH="{path_to_add}:$PATH""#)
}

/// Pure core: append `line` to `content` unless `content` already contains it.
fn append_once(content: &str, description: &str, line: &str) -> (String, bool) {
    if content.contains(line) {
        return (content.to_string(), false);
    }
    let mut out = content.to_string();
    if !out.is_empty() && !out.ends_with('\n') {
        out.push('\n');
    }
    out.push_str(&format!("# Añadido por setup - {description}\n"));
    out.push_str(line);
    out.push('\n');
    (out, true)
}

// ---------------------------------------------------------------------------
// Cleanup (clean_zshrc heredity sweep)
// ---------------------------------------------------------------------------

/// Clean every candidate rc file: remove the managed block and the stray
/// lines older versions of the script may have left behind.
pub fn clean(candidates: &[PathBuf]) -> io::Result<()> {
    for rc in candidates {
        if !rc.exists() {
            continue;
        }
        let content = fs::read_to_string(rc)?;
        fs::write(rc, clean_content(&content))?;
    }
    Ok(())
}

/// Pure core of [`clean`]: strip the managed block, the Powerlevel10k instant
/// prompt block, and the loose OMZ/p10k lines.
fn clean_content(content: &str) -> String {
    let without_block = strip_block(content);
    let mut out = String::new();
    let mut in_instant = false;
    for line in without_block.lines() {
        if line.starts_with("# Enable Powerlevel10k instant prompt") {
            in_instant = true;
            continue;
        }
        if in_instant {
            // The bash deletes through the closing `fi`.
            if line.trim() == "fi" {
                in_instant = false;
            }
            continue;
        }
        let trimmed = line.trim_start();
        let drop = trimmed.starts_with("export ZSH=")
            || trimmed.starts_with("ZSH_THEME=")
            || trimmed.starts_with("plugins=")
            || (trimmed.starts_with("source ") && line.contains("oh-my-zsh.sh"))
            || line.contains(".p10k.zsh")
            || line.contains("# Añadido por setup");
        if !drop {
            out.push_str(line);
            out.push('\n');
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn getter(pairs: &[(&str, &str)]) -> impl Fn(&str) -> Option<String> {
        let map: HashMap<String, String> = pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect();
        move |k: &str| map.get(k).cloned()
    }

    #[test]
    fn resolve_normal_terminal() {
        let g = getter(&[]);
        assert_eq!(resolve_from(&g, "/home/ada"), PathBuf::from("/home/ada/.zshrc"));
    }

    #[test]
    fn resolve_zdotdir_equal_home() {
        let g = getter(&[("ZDOTDIR", "/home/ada")]);
        assert_eq!(resolve_from(&g, "/home/ada"), PathBuf::from("/home/ada/.zshrc"));
    }

    #[test]
    fn resolve_vscode_uses_user_zdotdir() {
        let g = getter(&[
            ("ZDOTDIR", "/tmp/ephemeral"),
            ("TERM_PROGRAM", "vscode"),
            ("USER_ZDOTDIR", "/home/ada"),
        ]);
        assert_eq!(resolve_from(&g, "/home/ada"), PathBuf::from("/home/ada/.zshrc"));
    }

    #[test]
    fn resolve_terax_uses_terax_zdotdir() {
        let g = getter(&[
            ("ZDOTDIR", "/run/terax/abc"),
            ("TERAX_USER_ZDOTDIR", "/home/ada"),
        ]);
        assert_eq!(resolve_from(&g, "/home/ada"), PathBuf::from("/home/ada/.zshrc"));
    }

    #[test]
    fn resolve_custom_zdotdir_respected() {
        let g = getter(&[("ZDOTDIR", "/opt/zsh")]);
        assert_eq!(resolve_from(&g, "/home/ada"), PathBuf::from("/opt/zsh/.zshrc"));
    }

    #[test]
    fn managed_block_is_idempotent() {
        let plugins = "plugins=(git zsh-autosuggestions)";
        let once = build_managed_block("# user line\n", plugins);
        let twice = build_managed_block(&once, plugins);
        assert_eq!(once, twice, "rewriting must not duplicate the block");
        assert_eq!(twice.matches(BLOCK_START).count(), 1);
        assert_eq!(twice.matches(BLOCK_END).count(), 1);
        assert!(twice.contains(plugins));
        assert!(twice.contains(".p10k.zsh"));
        assert!(twice.starts_with("# user line"));
    }

    #[test]
    fn strip_block_removes_legacy_bash_markers() {
        let content = "keep me\n\
            # >>> setup_macos.sh (Oh My Zsh + Powerlevel10k) >>>\n\
            export ZSH=\"$HOME/.oh-my-zsh\"\n\
            # <<< setup_macos.sh (Oh My Zsh + Powerlevel10k) <<<\n\
            also keep\n";
        let out = strip_block(content);
        assert!(out.contains("keep me"));
        assert!(out.contains("also keep"));
        assert!(!out.contains("export ZSH"));
    }

    #[test]
    fn append_once_dedups() {
        let line = r#"eval "$(zoxide init zsh)""#;
        let (after_first, added1) = append_once("# base\n", "zoxide init", line);
        assert!(added1);
        let (after_second, added2) = append_once(&after_first, "zoxide init", line);
        assert!(!added2);
        assert_eq!(after_first, after_second);
        assert_eq!(after_second.matches(line).count(), 1);
    }

    #[test]
    fn clean_removes_block_and_heredity_but_keeps_user_lines() {
        let content = "\
# my own alias
alias g=git
# Enable Powerlevel10k instant prompt should be removed
if [[ -r foo ]]; then
  source bar
fi
export ZSH=\"$HOME/.oh-my-zsh\"
ZSH_THEME=\"powerlevel10k/powerlevel10k\"
plugins=(git)
source \"$ZSH/oh-my-zsh.sh\"
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh
# Añadido por setup - PATH
export PATH=\"/opt/bin:$PATH\"
# keep this trailing line
";
        let out = clean_content(content);
        assert!(out.contains("alias g=git"));
        assert!(out.contains("# keep this trailing line"));
        assert!(!out.contains("Powerlevel10k instant prompt"));
        assert!(!out.contains("export ZSH="));
        assert!(!out.contains("ZSH_THEME="));
        assert!(!out.contains("plugins="));
        assert!(!out.contains("oh-my-zsh.sh"));
        assert!(!out.contains(".p10k.zsh"));
        assert!(!out.contains("Añadido por setup"));
        // Parity with the bash `clean_zshrc`: it deletes the `# Añadido por…`
        // comment but NOT the `export PATH=` line beneath it, so that survives.
        // (We don't blanket-delete `export PATH=` lines — that would clobber a
        // user's own PATH edits.)
        assert!(out.contains("/opt/bin"));
    }
}
