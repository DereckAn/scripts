//! Running install commands while streaming their output to the UI.
//!
//! [`stream_command`] runs a shell command, merges stdout+stderr, and forwards
//! every line as [`InstallEvent::Line`] over a channel. It is meant to run on a
//! dedicated worker thread (see the `install_log_demo` example) so the UI
//! thread stays responsive — it just drains the channel each frame.
//!
//! stderr is merged into stdout via the shell so a single pipe and a single
//! reader suffice, avoiding the two-pipe deadlock trap. The command is wrapped
//! in a brace group — `{ <cmd>\n} 2>&1` — so the redirect covers the *entire*
//! command list, not just its last simple command (a bare trailing `2>&1`
//! would miss stderr from earlier commands in `a; b >&2`).

use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::sync::mpsc::Sender;

use crate::model::InstallEvent;

/// Run `cmd` via `sh -c "<cmd> 2>&1"`, streaming each output line as an
/// [`InstallEvent::Line`]. Returns `true` if the command exited with status 0.
///
/// The reader runs in the calling thread; spawn this on the worker thread, not
/// the UI thread.
pub fn stream_command(cmd: &str, tx: &Sender<InstallEvent>) -> bool {
    let mut child = match Command::new("sh")
        .arg("-c")
        .arg(format!("{{ {cmd}\n}} 2>&1"))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .spawn()
    {
        Ok(child) => child,
        Err(e) => {
            let _ = tx.send(InstallEvent::Line(format!("no se pudo lanzar el comando: {e}")));
            return false;
        }
    };

    if let Some(stdout) = child.stdout.take() {
        for line in BufReader::new(stdout).lines() {
            match line {
                Ok(line) => {
                    // If the UI side hung up, stop reading.
                    if tx.send(InstallEvent::Line(line)).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    }

    matches!(child.wait(), Ok(status) if status.success())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;

    fn collect(cmd: &str) -> (bool, Vec<String>) {
        let (tx, rx) = mpsc::channel();
        let ok = stream_command(cmd, &tx);
        drop(tx);
        let lines = rx
            .into_iter()
            .map(|ev| match ev {
                InstallEvent::Line(l) => l,
                other => panic!("expected Line, got {other:?}"),
            })
            .collect();
        (ok, lines)
    }

    #[test]
    fn streams_lines_in_order_and_reports_success() {
        let (ok, lines) = collect("printf 'a\\nb\\nc\\n'");
        assert!(ok);
        assert_eq!(lines, vec!["a", "b", "c"]);
    }

    #[test]
    fn merges_stderr_into_the_stream() {
        let (_ok, lines) = collect("echo out; echo err 1>&2");
        assert!(lines.contains(&"out".to_string()));
        assert!(lines.contains(&"err".to_string()));
    }

    #[test]
    fn nonzero_exit_reports_failure() {
        let (ok, _lines) = collect("echo trying; exit 3");
        assert!(!ok);
    }
}
