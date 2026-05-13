//! Ratatui screens and the screen state machine.
//!
//! Step 2 implements the main menu and the two-panel selection screen with full
//! keyboard navigation. No installs happen yet — [`run`] returns once the user
//! confirms a selection ([`Screen::Confirmed`]) or quits ([`Screen::Quit`]),
//! and the caller inspects [`App::action`] and [`App::selected_apps`].

use std::sync::mpsc::{Receiver, RecvTimeoutError, TryRecvError};
use std::time::Duration;

use anyhow::Result;
use crossterm::event::{self, Event, KeyCode, KeyEventKind};
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Gauge, List, ListItem, ListState, Paragraph},
    Frame,
};

use crate::model::{AppEntry, Category, InstallEvent};
use crate::prompt::{Answer, Prompt, PromptRequest};
use crate::tui::Tui;

/// Which screen is currently shown / the loop's exit states.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Screen {
    MainMenu,
    Selection,
    /// User pressed Enter on the selection screen — caller takes over.
    Confirmed,
    /// User chose to exit.
    Quit,
}

/// What the user picked on the main menu.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MenuAction {
    Install,
    Uninstall,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Panel {
    Categories,
    Apps,
}

const MENU_ITEMS: [&str; 3] = ["Instalar y configurar", "Desinstalar", "Salir"];

/// All UI state for the menu + selection screens.
pub struct App {
    pub categories: Vec<Category>,
    pub screen: Screen,
    /// Set when the user picks Install/Uninstall on the main menu.
    pub action: Option<MenuAction>,
    menu_index: usize,
    focus: Panel,
    cat_state: ListState,
    app_state: ListState,
}

impl App {
    pub fn new(categories: Vec<Category>) -> Self {
        let mut cat_state = ListState::default();
        cat_state.select(Some(0));
        let mut app_state = ListState::default();
        app_state.select(Some(0));
        Self {
            categories,
            screen: Screen::MainMenu,
            action: None,
            menu_index: 0,
            focus: Panel::Categories,
            cat_state,
            app_state,
        }
    }

    /// Every app the user has ticked, across all categories.
    pub fn selected_apps(&self) -> Vec<&AppEntry> {
        self.categories
            .iter()
            .flat_map(|c| c.apps.iter())
            .filter(|a| a.selected)
            .collect()
    }

    fn current_cat(&self) -> usize {
        self.cat_state.selected().unwrap_or(0)
    }
}

/// Drive the menu/selection loop until the user confirms or quits.
pub fn run(terminal: &mut Tui, app: &mut App) -> Result<()> {
    while app.screen != Screen::Quit && app.screen != Screen::Confirmed {
        terminal.draw(|f| draw(f, app))?;
        if event::poll(Duration::from_millis(100))? {
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press {
                    handle_key(app, key.code);
                }
            }
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Input handling
// ---------------------------------------------------------------------------

fn handle_key(app: &mut App, code: KeyCode) {
    match app.screen {
        Screen::MainMenu => menu_key(app, code),
        Screen::Selection => selection_key(app, code),
        Screen::Confirmed | Screen::Quit => {}
    }
}

fn menu_key(app: &mut App, code: KeyCode) {
    match code {
        KeyCode::Up | KeyCode::Char('k') => {
            app.menu_index = if app.menu_index == 0 {
                MENU_ITEMS.len() - 1
            } else {
                app.menu_index - 1
            };
        }
        KeyCode::Down | KeyCode::Char('j') => {
            app.menu_index = (app.menu_index + 1) % MENU_ITEMS.len();
        }
        KeyCode::Enter => match app.menu_index {
            0 => {
                app.action = Some(MenuAction::Install);
                app.screen = Screen::Selection;
            }
            1 => {
                app.action = Some(MenuAction::Uninstall);
                app.screen = Screen::Selection;
            }
            _ => app.screen = Screen::Quit,
        },
        KeyCode::Char('q') | KeyCode::Esc => app.screen = Screen::Quit,
        _ => {}
    }
}

fn selection_key(app: &mut App, code: KeyCode) {
    match code {
        KeyCode::Esc | KeyCode::Char('q') => app.screen = Screen::MainMenu,
        KeyCode::Tab => {
            app.focus = match app.focus {
                Panel::Categories => Panel::Apps,
                Panel::Apps => Panel::Categories,
            };
        }
        KeyCode::Up | KeyCode::Char('k') => move_cursor(app, -1),
        KeyCode::Down | KeyCode::Char('j') => move_cursor(app, 1),
        KeyCode::Char(' ') => toggle_current(app),
        KeyCode::Char('a') | KeyCode::Char('A') => toggle_all_in_category(app),
        KeyCode::Enter => app.screen = Screen::Confirmed,
        _ => {}
    }
}

/// Move the active panel's cursor by `delta` (-1 up, +1 down), wrapping.
fn move_cursor(app: &mut App, delta: isize) {
    match app.focus {
        Panel::Categories => {
            let len = app.categories.len();
            if len == 0 {
                return;
            }
            let i = app.current_cat();
            app.cat_state.select(Some(wrap(i, delta, len)));
            // Reset the apps cursor when the category changes.
            app.app_state.select(Some(0));
        }
        Panel::Apps => {
            let len = app
                .categories
                .get(app.current_cat())
                .map(|c| c.apps.len())
                .unwrap_or(0);
            if len == 0 {
                return;
            }
            let i = app.app_state.selected().unwrap_or(0);
            app.app_state.select(Some(wrap(i, delta, len)));
        }
    }
}

/// Wrap `i + delta` into `0..len`.
fn wrap(i: usize, delta: isize, len: usize) -> usize {
    let n = len as isize;
    (((i as isize + delta) % n + n) % n) as usize
}

fn toggle_current(app: &mut App) {
    let c = app.current_cat();
    if let Some(a) = app.app_state.selected() {
        if let Some(entry) = app.categories.get_mut(c).and_then(|cat| cat.apps.get_mut(a)) {
            entry.selected = !entry.selected;
        }
    }
}

fn toggle_all_in_category(app: &mut App) {
    let c = app.current_cat();
    if let Some(cat) = app.categories.get_mut(c) {
        // If everything is already selected, clear; otherwise select all.
        let all = !cat.apps.is_empty() && cat.apps.iter().all(|a| a.selected);
        for a in &mut cat.apps {
            a.selected = !all;
        }
    }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

fn draw(f: &mut Frame, app: &mut App) {
    match app.screen {
        Screen::MainMenu => draw_menu(f, app),
        Screen::Selection => draw_selection(f, app),
        Screen::Confirmed | Screen::Quit => {}
    }
}

fn draw_menu(f: &mut Frame, app: &App) {
    let area = centered_rect(54, 11, f.area());
    let mut lines = vec![
        Line::from(Span::styled(
            "Setup — Development Environment",
            Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
    ];
    for (i, item) in MENU_ITEMS.iter().enumerate() {
        let selected = i == app.menu_index;
        let prefix = if selected { "> " } else { "  " };
        let style = if selected {
            Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD)
        } else {
            Style::default()
        };
        lines.push(Line::from(Span::styled(
            format!("{prefix}[{}] {item}", i + 1),
            style,
        )));
    }
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "[↑↓] mover   [Enter] elegir   [q] salir",
        Style::default().fg(Color::DarkGray),
    )));

    f.render_widget(
        Paragraph::new(lines)
            .alignment(Alignment::Left)
            .block(Block::default().borders(Borders::ALL).title(" Setup ")),
        area,
    );
}

fn draw_selection(f: &mut Frame, app: &mut App) {
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(2)])
        .split(f.area());

    let panes = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(32), Constraint::Percentage(68)])
        .split(rows[0]);

    let cat_idx = app.current_cat();
    let cats_focused = app.focus == Panel::Categories;
    let apps_focused = !cats_focused;

    // --- Categories panel (with per-category selected counts) ---
    let cat_items: Vec<ListItem> = app
        .categories
        .iter()
        .map(|c| {
            let total = c.apps.len();
            let sel = c.apps.iter().filter(|a| a.selected).count();
            ListItem::new(format!("{} ({sel}/{total})", c.title))
        })
        .collect();
    let cat_list = List::new(cat_items)
        .block(panel_block("Categorías", cats_focused))
        .highlight_style(highlight_style(cats_focused))
        .highlight_symbol(if cats_focused { "> " } else { "  " });
    f.render_stateful_widget(cat_list, panes[0], &mut app.cat_state);

    // --- Apps panel for the current category ---
    let app_items: Vec<ListItem> = app
        .categories
        .get(cat_idx)
        .map(|c| c.apps.iter().map(app_list_item).collect())
        .unwrap_or_default();
    let apps_title = app
        .categories
        .get(cat_idx)
        .map(|c| c.title.clone())
        .unwrap_or_else(|| "Apps".to_string());
    let app_list = List::new(app_items)
        .block(panel_block(&apps_title, apps_focused))
        .highlight_style(highlight_style(apps_focused))
        .highlight_symbol(if apps_focused { "> " } else { "  " });
    f.render_stateful_widget(app_list, panes[1], &mut app.app_state);

    // --- Help / status line ---
    let total_sel = app.selected_apps().len();
    let help = Paragraph::new(vec![
        Line::from("[↑↓] navegar   [Tab] cambiar panel   [Space] seleccionar   [A] todo"),
        Line::from(format!(
            "[Enter] confirmar ({total_sel} sel.)   [Esc/Q] volver"
        )),
    ])
    .style(Style::default().fg(Color::DarkGray));
    f.render_widget(help, rows[1]);
}

fn app_list_item(a: &AppEntry) -> ListItem<'static> {
    let (check, check_style) = if a.selected {
        ("[x]", Style::default().fg(Color::Green))
    } else {
        ("[ ]", Style::default())
    };
    let mut spans = vec![
        Span::styled(check, check_style),
        Span::raw(" "),
        Span::raw(a.name.clone()),
    ];
    if a.installed {
        spans.push(Span::styled(
            "  (instalado)",
            Style::default().fg(Color::Green).add_modifier(Modifier::DIM),
        ));
    }
    ListItem::new(Line::from(spans))
}

fn panel_block(title: &str, focused: bool) -> Block<'static> {
    let border = if focused {
        Style::default().fg(Color::Cyan)
    } else {
        Style::default().fg(Color::DarkGray)
    };
    Block::default()
        .borders(Borders::ALL)
        .title(Line::from(format!(" {title} ")))
        .border_style(border)
}

fn highlight_style(focused: bool) -> Style {
    if focused {
        Style::default().add_modifier(Modifier::REVERSED | Modifier::BOLD)
    } else {
        Style::default().add_modifier(Modifier::DIM)
    }
}

/// A `width`×`height` rectangle centered inside `area` (clamped to fit).
fn centered_rect(width: u16, height: u16, area: Rect) -> Rect {
    let x = area.x + area.width.saturating_sub(width) / 2;
    let y = area.y + area.height.saturating_sub(height) / 2;
    Rect {
        x,
        y,
        width: width.min(area.width),
        height: height.min(area.height),
    }
}

// ===========================================================================
// Install log screen (Step 3)
// ===========================================================================

const SPINNER: [&str; 10] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

#[derive(Clone, Copy, PartialEq, Eq)]
enum Status {
    Running,
    Ok,
    Fail,
    Info,
}

struct Entry {
    status: Status,
    text: String,
}

/// State for the live install-log screen, fed by [`InstallEvent`]s.
pub struct LogState {
    title: String,
    entries: Vec<Entry>,
    /// Index into `entries` of the step currently running, if any.
    current: Option<usize>,
    total: usize,
    completed: usize,
    spinner: usize,
    /// True once the job is finished (or the channel hung up).
    pub done: bool,
}

impl LogState {
    fn new(title: &str) -> Self {
        Self {
            title: title.to_string(),
            entries: Vec::new(),
            current: None,
            total: 0,
            completed: 0,
            spinner: 0,
            done: false,
        }
    }

    fn apply(&mut self, ev: InstallEvent) {
        match ev {
            InstallEvent::StepStarted { total, desc, .. } => {
                self.total = total;
                self.current = Some(self.entries.len());
                self.entries.push(Entry {
                    status: Status::Running,
                    text: desc,
                });
            }
            InstallEvent::Line(text) => self.entries.push(Entry {
                status: Status::Info,
                text,
            }),
            InstallEvent::StepFinished { ok } => {
                if let Some(i) = self.current.take() {
                    self.entries[i].status = if ok { Status::Ok } else { Status::Fail };
                }
                self.completed += 1;
            }
            InstallEvent::Done => {
                self.done = true;
                self.current = None;
            }
        }
    }

    fn tick(&mut self) {
        self.spinner = (self.spinner + 1) % SPINNER.len();
    }
}

/// Drive the install-log screen until the job finishes and the user dismisses it.
///
/// Drains `rx` each frame (non-blocking), animates the spinner, and only lets
/// the user leave once the job is `done`. If the sender is dropped without a
/// `Done` event, the job is treated as finished.
pub fn run_log(terminal: &mut Tui, rx: &Receiver<InstallEvent>, title: &str) -> Result<()> {
    let mut state = LogState::new(title);
    loop {
        // Drain everything currently available without blocking.
        loop {
            match rx.try_recv() {
                Ok(ev) => state.apply(ev),
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => {
                    state.done = true;
                    break;
                }
            }
        }

        terminal.draw(|f| draw_log(f, &state))?;

        if event::poll(Duration::from_millis(80))? {
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press
                    && state.done
                    && matches!(key.code, KeyCode::Char('q') | KeyCode::Esc | KeyCode::Enter)
                {
                    break;
                }
            }
        }

        state.tick();
    }
    Ok(())
}

fn draw_log(f: &mut Frame, s: &LogState) {
    let rows = Layout::vertical([Constraint::Min(0), Constraint::Length(3)]).split(f.area());

    // Log pane — auto-scrolled to the tail that fits.
    let visible = rows[0].height.saturating_sub(2) as usize;
    let start = s.entries.len().saturating_sub(visible);
    let lines: Vec<Line> = s.entries[start..]
        .iter()
        .map(|e| entry_line(e, s.spinner))
        .collect();
    f.render_widget(
        Paragraph::new(lines).block(
            Block::default()
                .borders(Borders::ALL)
                .title(Line::from(format!(" {} ", s.title))),
        ),
        rows[0],
    );

    // Progress gauge.
    let ratio = if s.total == 0 {
        0.0
    } else {
        (s.completed as f64 / s.total as f64).clamp(0.0, 1.0)
    };
    let pct = (ratio * 100.0).round() as u16;
    let tail = if s.done {
        "   ✓ completado — [q] salir"
    } else {
        ""
    };
    f.render_widget(
        Gauge::default()
            .block(Block::default().borders(Borders::ALL))
            .gauge_style(Style::default().fg(Color::Green))
            .ratio(ratio)
            .label(format!("[{}/{}] {pct}%{tail}", s.completed, s.total)),
        rows[1],
    );
}

fn entry_line(e: &Entry, spinner: usize) -> Line<'static> {
    let glyph = |sym: &str, color: Color| {
        Span::styled(sym.to_string(), Style::default().fg(color).add_modifier(Modifier::BOLD))
    };
    match e.status {
        Status::Running => Line::from(vec![
            glyph(SPINNER[spinner], Color::Cyan),
            Span::raw(" "),
            Span::raw(e.text.clone()),
        ]),
        Status::Ok => Line::from(vec![
            glyph("✓", Color::Green),
            Span::raw(" "),
            Span::raw(e.text.clone()),
        ]),
        Status::Fail => Line::from(vec![
            glyph("✗", Color::Red),
            Span::raw(" "),
            Span::raw(e.text.clone()),
        ]),
        Status::Info => Line::from(Span::styled(
            format!("    {}", e.text),
            Style::default().fg(Color::DarkGray),
        )),
    }
}

// ===========================================================================
// Modal prompts (Step 4)
// ===========================================================================

/// What a key press did to the modal: still editing, submitted, or cancelled.
enum Outcome {
    Pending,
    Submit(Answer),
    Cancel,
}

/// Live editing state for a single modal prompt.
struct PromptState {
    prompt: Prompt,
    /// Text buffer (Text prompts).
    input: String,
    /// Highlighted index: 0/1 for YesNo (0 = Yes), 0..options for Choice.
    choice: usize,
}

impl PromptState {
    fn new(prompt: Prompt) -> Self {
        let (input, choice) = match &prompt {
            Prompt::Text { initial, .. } => (initial.clone(), 0),
            Prompt::YesNo { default_yes, .. } => (String::new(), usize::from(!*default_yes)),
            Prompt::Choice { .. } => (String::new(), 0),
        };
        Self {
            prompt,
            input,
            choice,
        }
    }

    fn handle_key(&mut self, code: KeyCode) -> Outcome {
        match &self.prompt {
            Prompt::Text { .. } => match code {
                KeyCode::Esc => Outcome::Cancel,
                KeyCode::Enter => Outcome::Submit(Answer::Text(self.input.clone())),
                KeyCode::Backspace => {
                    self.input.pop();
                    Outcome::Pending
                }
                KeyCode::Char(c) => {
                    self.input.push(c);
                    Outcome::Pending
                }
                _ => Outcome::Pending,
            },
            Prompt::YesNo { .. } => match code {
                KeyCode::Esc => Outcome::Cancel,
                KeyCode::Left | KeyCode::Right | KeyCode::Tab => {
                    self.choice ^= 1;
                    Outcome::Pending
                }
                KeyCode::Char('y') | KeyCode::Char('Y') => Outcome::Submit(Answer::Bool(true)),
                KeyCode::Char('n') | KeyCode::Char('N') => Outcome::Submit(Answer::Bool(false)),
                KeyCode::Enter => Outcome::Submit(Answer::Bool(self.choice == 0)),
                _ => Outcome::Pending,
            },
            Prompt::Choice { options, .. } => {
                let len = options.len();
                match code {
                    KeyCode::Esc => Outcome::Cancel,
                    KeyCode::Up | KeyCode::Char('k') => {
                        if len > 0 {
                            self.choice = (self.choice + len - 1) % len;
                        }
                        Outcome::Pending
                    }
                    KeyCode::Down | KeyCode::Char('j') => {
                        if len > 0 {
                            self.choice = (self.choice + 1) % len;
                        }
                        Outcome::Pending
                    }
                    KeyCode::Enter => Outcome::Submit(Answer::Choice(self.choice)),
                    KeyCode::Char(c) if c.is_ascii_digit() => {
                        let n = c.to_digit(10).unwrap_or(0) as usize;
                        if n >= 1 && n <= len {
                            Outcome::Submit(Answer::Choice(n - 1))
                        } else {
                            Outcome::Pending
                        }
                    }
                    _ => Outcome::Pending,
                }
            }
        }
    }
}

/// Serve modal prompts from a worker thread until it drops the sender.
///
/// Each [`PromptRequest`] is rendered as a modal and run to completion; the
/// answer (or `None` on cancel) is sent back on the request's reply channel.
/// While idle it shows a "procesando" frame so the UI stays alive.
pub fn serve_prompts(terminal: &mut Tui, rx: &Receiver<PromptRequest>) -> Result<()> {
    loop {
        let request = match rx.recv_timeout(Duration::from_millis(100)) {
            Ok(req) => req,
            Err(RecvTimeoutError::Timeout) => {
                terminal.draw(draw_idle)?;
                continue;
            }
            Err(RecvTimeoutError::Disconnected) => break,
        };

        let answer = serve_one(terminal, request.prompt)?;
        // If the worker already hung up, nobody is listening — that's fine.
        let _ = request.reply.send(answer);
    }
    Ok(())
}

/// Render one modal and run its edit loop until submit or cancel.
fn serve_one(terminal: &mut Tui, prompt: Prompt) -> Result<Option<Answer>> {
    let mut state = PromptState::new(prompt);
    loop {
        terminal.draw(|f| draw_prompt(f, &state))?;
        if event::poll(Duration::from_millis(100))? {
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press {
                    match state.handle_key(key.code) {
                        Outcome::Pending => {}
                        Outcome::Submit(answer) => return Ok(Some(answer)),
                        Outcome::Cancel => return Ok(None),
                    }
                }
            }
        }
    }
}

fn draw_idle(f: &mut Frame) {
    let area = centered_rect(40, 3, f.area());
    f.render_widget(Clear, area);
    f.render_widget(
        Paragraph::new(Line::from(Span::styled(
            "procesando…",
            Style::default().fg(Color::DarkGray),
        )))
        .alignment(Alignment::Center)
        .block(Block::default().borders(Borders::ALL)),
        area,
    );
}

fn draw_prompt(f: &mut Frame, s: &PromptState) {
    let (mut content, hint) = prompt_body(s);
    content.push(Line::from(""));
    content.push(Line::from(Span::styled(
        hint,
        Style::default().fg(Color::DarkGray),
    )));

    let height = content.len() as u16 + 2;
    let area = centered_rect(66, height, f.area());
    f.render_widget(Clear, area);
    f.render_widget(
        Paragraph::new(content).block(
            Block::default()
                .borders(Borders::ALL)
                .title(Line::from(" Pregunta "))
                .border_style(Style::default().fg(Color::Cyan)),
        ),
        area,
    );
}

/// Build the body lines + key hint for the current prompt.
fn prompt_body(s: &PromptState) -> (Vec<Line<'static>>, &'static str) {
    let label = |text: &str| {
        Line::from(Span::styled(
            text.to_string(),
            Style::default().fg(Color::Yellow),
        ))
    };
    let cursor = Span::styled(" ", Style::default().add_modifier(Modifier::REVERSED));

    match &s.prompt {
        Prompt::Text { label: l, .. } => {
            let lines = vec![
                label(l),
                Line::from(""),
                Line::from(vec![Span::raw("> "), Span::raw(s.input.clone()), cursor]),
            ];
            (lines, "[Enter] aceptar    [Esc] cancelar")
        }
        Prompt::YesNo { label: l, .. } => {
            let opt = |text: &str, on: bool| {
                let style = if on {
                    Style::default().add_modifier(Modifier::REVERSED | Modifier::BOLD)
                } else {
                    Style::default()
                };
                Span::styled(format!("  {text}  "), style)
            };
            let lines = vec![
                label(l),
                Line::from(""),
                Line::from(vec![
                    opt("Sí", s.choice == 0),
                    Span::raw("   "),
                    opt("No", s.choice == 1),
                ]),
            ];
            (
                lines,
                "[←→] elegir   [y/n] directo   [Enter] aceptar   [Esc] cancelar",
            )
        }
        Prompt::Choice {
            label: l, options, ..
        } => {
            let mut lines = vec![label(l), Line::from("")];
            for (i, opt) in options.iter().enumerate() {
                let on = i == s.choice;
                let marker = if on { "> " } else { "  " };
                let style = if on {
                    Style::default().add_modifier(Modifier::REVERSED | Modifier::BOLD)
                } else {
                    Style::default()
                };
                lines.push(Line::from(Span::styled(
                    format!("{marker}[{}] {opt}", i + 1),
                    style,
                )));
            }
            (
                lines,
                "[↑↓] mover   [1-9] elegir   [Enter] aceptar   [Esc] cancelar",
            )
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn text_prompt_edits_and_submits() {
        let mut s = PromptState::new(Prompt::Text {
            label: "name".into(),
            initial: String::new(),
        });
        for c in "Ada".chars() {
            assert!(matches!(s.handle_key(KeyCode::Char(c)), Outcome::Pending));
        }
        assert!(matches!(s.handle_key(KeyCode::Backspace), Outcome::Pending));
        match s.handle_key(KeyCode::Enter) {
            Outcome::Submit(Answer::Text(t)) => assert_eq!(t, "Ad"),
            _ => panic!("expected Submit(Text)"),
        }
    }

    #[test]
    fn yesno_defaults_and_arrow_toggle() {
        // default_yes = false → starts highlighting "No" (index 1).
        let mut s = PromptState::new(Prompt::YesNo {
            label: "ok?".into(),
            default_yes: false,
        });
        assert_eq!(s.choice, 1);
        assert!(matches!(s.handle_key(KeyCode::Left), Outcome::Pending));
        assert_eq!(s.choice, 0);
        assert!(matches!(
            s.handle_key(KeyCode::Enter),
            Outcome::Submit(Answer::Bool(true))
        ));
    }

    #[test]
    fn choice_wraps_and_number_selects() {
        let mut s = PromptState::new(Prompt::Choice {
            label: "pick".into(),
            options: vec!["a".into(), "b".into(), "c".into()],
        });
        // Up from 0 wraps to last.
        s.handle_key(KeyCode::Up);
        assert_eq!(s.choice, 2);
        // Number key selects directly (1-based).
        assert!(matches!(
            s.handle_key(KeyCode::Char('2')),
            Outcome::Submit(Answer::Choice(1))
        ));
    }
}
