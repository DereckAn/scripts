//! Modal prompts that replace the bash `read` calls.
//!
//! The install worker runs on its own thread, so it cannot read stdin while the
//! UI owns the terminal in raw mode. Instead the worker holds a [`Prompter`]:
//! each `text` / `yes_no` / `choose` call ships a [`PromptRequest`] (with a
//! one-shot reply channel) to the UI thread and **blocks** until the UI sends
//! the answer back. The UI side renders the modal and replies (see
//! `ui::serve_prompts`).
//!
//! Every helper returns an `Option`: `None` means the user cancelled (Esc) or
//! the UI hung up — callers map that to "skip this step", mirroring how the
//! bash treats an empty answer.

use std::sync::mpsc::Sender;

/// A question to show the user.
#[derive(Debug, Clone)]
pub enum Prompt {
    /// Free-text entry (git name, email, enterprise host…).
    Text { label: String, initial: String },
    /// Yes/no confirmation with a default highlighted choice.
    YesNo { label: String, default_yes: bool },
    /// Pick one of several options (e.g. the gh account `[1/2/3]` menu).
    Choice { label: String, options: Vec<String> },
}

/// The user's reply to a [`Prompt`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Answer {
    Text(String),
    Bool(bool),
    Choice(usize),
}

/// A prompt plus the channel the UI uses to reply (`None` = cancelled).
pub struct PromptRequest {
    pub prompt: Prompt,
    pub reply: Sender<Option<Answer>>,
}

/// Worker-side handle for asking the UI questions. Cloneable and `Send`.
#[derive(Clone)]
pub struct Prompter {
    tx: Sender<PromptRequest>,
}

impl Prompter {
    pub fn new(tx: Sender<PromptRequest>) -> Self {
        Self { tx }
    }

    /// Send `prompt` to the UI and block until it replies. `None` if cancelled
    /// or the UI dropped the channel.
    fn ask(&self, prompt: Prompt) -> Option<Answer> {
        let (reply, rx) = std::sync::mpsc::channel();
        self.tx.send(PromptRequest { prompt, reply }).ok()?;
        // Outer Option: recv error (UI gone). Inner Option: user cancelled.
        rx.recv().ok()?
    }

    /// Ask for free text. Returns the entered string (may be empty).
    pub fn text(&self, label: impl Into<String>) -> Option<String> {
        match self.ask(Prompt::Text {
            label: label.into(),
            initial: String::new(),
        })? {
            Answer::Text(s) => Some(s),
            _ => None,
        }
    }

    /// Ask a yes/no question with the given default highlighted.
    pub fn yes_no(&self, label: impl Into<String>, default_yes: bool) -> Option<bool> {
        match self.ask(Prompt::YesNo {
            label: label.into(),
            default_yes,
        })? {
            Answer::Bool(b) => Some(b),
            _ => None,
        }
    }

    /// Ask the user to pick one option; returns the chosen index.
    pub fn choose(&self, label: impl Into<String>, options: Vec<String>) -> Option<usize> {
        match self.ask(Prompt::Choice {
            label: label.into(),
            options,
        })? {
            Answer::Choice(i) => Some(i),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;
    use std::thread;

    #[test]
    fn round_trips_each_prompt_kind_and_cancel() {
        let (tx, rx) = mpsc::channel::<PromptRequest>();
        let p = Prompter::new(tx);

        // Stand-in UI thread: reply to each request with a canned answer.
        let ui = thread::spawn(move || {
            rx.recv().unwrap().reply.send(Some(Answer::Text("Ada".into()))).unwrap();
            rx.recv().unwrap().reply.send(Some(Answer::Bool(true))).unwrap();
            rx.recv().unwrap().reply.send(Some(Answer::Choice(2))).unwrap();
            rx.recv().unwrap().reply.send(None).unwrap(); // cancelled
        });

        assert_eq!(p.text("name"), Some("Ada".to_string()));
        assert_eq!(p.yes_no("ok?", false), Some(true));
        assert_eq!(
            p.choose("pick", vec!["a".into(), "b".into(), "c".into()]),
            Some(2)
        );
        assert_eq!(p.text("cancel me"), None);

        ui.join().unwrap();
    }

    #[test]
    fn ask_returns_none_when_ui_hung_up() {
        let (tx, rx) = mpsc::channel::<PromptRequest>();
        let p = Prompter::new(tx);
        // Drop the receiver immediately: the reply channel can never answer.
        drop(rx);
        assert_eq!(p.text("anybody?"), None);
    }
}
