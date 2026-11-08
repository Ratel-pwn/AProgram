#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod platform;
mod process;
mod state;
mod tray;
mod ui;

use std::{
    collections::{HashMap, HashSet},
    fs::{File, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::{
        Arc, Mutex, OnceLock,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};

use gpui::{
    App, AppContext, Application, Bounds, Context, PathPromptOptions, PromptLevel, RenderImage,
    Task, TitlebarOptions, Window, WindowBounds, WindowOptions, point, px, size,
};
use process::Command;
use state::{AppEntry, Group, State, WindowState};

struct Launcher {
    tray: tray::Tray,
    _instance: tray::Instance,
    state_path: PathBuf,
    state: State,
    load_error: Option<String>,
    auto_start_pending: bool,
    legacy_dir: Option<PathBuf>,
    running: HashSet<PathBuf>,
    icons: HashMap<PathBuf, Option<Arc<RenderImage>>>,
    refresh: Option<Task<()>>,
    pending_click: Option<(PathBuf, Task<()>)>,
    hidden: bool,
    busy: bool,
    cancel_operation: Option<Arc<AtomicBool>>,
    quitting: bool,
    settings_open: bool,
    status: String,
    failures: Vec<String>,
    forceable: Vec<PathBuf>,
}

#[derive(Clone)]
enum NameAction {
    New,
    Rename(String),
    Copy(String),
}

fn main() {
    if let Err(error) = start() {
        platform::show_error(&format!("{error:#}"));
    }
}

fn start() -> anyhow::Result<()> {
    let Some(instance) = tray::acquire_instance()? else {
        return Ok(());
    };
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let hidden = args.iter().any(|arg| arg == "--tray");
    let state_path = std::env::var_os("APROGRAM_STATE_PATH")
        .map(PathBuf::from)
        .map_or_else(state::state_path, Ok)?;
    let (mut state, load_error) = match state::load(&state_path) {
        Ok(state) => (state, None),
        Err(error) => (State::default(), Some(format!("读取配置失败：{error:#}"))),
    };
    if !state
        .groups
        .iter()
        .any(|group| Some(&group.name) == state.selected.as_ref())
    {
        state.selected = state.groups.first().map(|group| group.name.clone());
    }
    let legacy_dir = std::env::current_exe()?.parent().and_then(|dir| {
        dir.join("software_groups.json")
            .is_file()
            .then(|| dir.to_owned())
    });
    let (tx, rx) = async_channel::unbounded();
    let tray = tray::Tray::new(move |event| {
        let _ = tx.try_send(event);
    })?;
    let auto_start_enabled = platform::auto_start_enabled();
    let auto_start_pending = state.settings.auto_start && !auto_start_enabled;
    state.settings.auto_start |= auto_start_enabled;
    let launcher = Launcher {
        tray,
        _instance: instance,
        state_path,
        state,
        load_error,
        auto_start_pending,
        legacy_dir,
        running: HashSet::new(),
        icons: HashMap::new(),
        refresh: None,
        pending_click: None,
        hidden,
        busy: false,
        cancel_operation: None,
        quitting: false,
        settings_open: false,
        status: String::new(),
        failures: Vec::new(),
        forceable: Vec::new(),
    };
    Application::new().run(move |cx: &mut App| {
        let bounds = launcher
            .state
            .window
            .as_ref()
            .filter(|window| {
                [window.x, window.y, window.width, window.height]
                    .iter()
                    .all(|n| n.is_finite())
            })
            .map(|window| {
                Bounds::new(
                    point(px(window.x), px(window.y)),
                    size(px(window.width.max(660.)), px(window.height.max(430.))),
                )
            })
            .unwrap_or_else(|| Bounds::centered(None, size(px(920.), px(580.)), cx));
        let opened = cx.open_window(
            WindowOptions {
                window_bounds: Some(WindowBounds::Windowed(bounds)),
                titlebar: Some(TitlebarOptions {
                    title: Some("AProgram".into()),
                    ..Default::default()
                }),
                window_min_size: Some(size(px(660.), px(430.))),
                show: !hidden,
                focus: !hidden,
                ..Default::default()
            },
            move |window, cx| {
                cx.new(|cx| {
                    let mut launcher = launcher;
                    launcher.connect(window, rx, cx);
                    launcher
                })
            },
        );
        if let Err(error) = opened {
            platform::show_error(&format!("无法打开 AProgram：{error:#}"));
            cx.quit();
        }
    });
    Ok(())
}

impl Launcher {
    fn connect(
        &mut self,
        window: &mut Window,
        rx: async_channel::Receiver<tray::Event>,
        cx: &mut Context<Self>,
    ) {
        self.update_tray();
        let weak = cx.weak_entity();
        window.on_window_should_close(cx, move |window, cx| {
            let _ = weak.update(cx, |this, cx| {
                this.remember_window(window);
                if this.state.settings.minimize_to_tray {
                    this.hidden = true;
                    this.refresh = None;
                    this.finish_pending_click(cx);
                    if let Ok(hwnd) = platform::hwnd(window) {
                        platform::hide(hwnd);
                    }
                    trace("hidden");
                } else {
                    this.quit(cx);
                }
            });
            false
        });
        let handle = window
            .window_handle()
            .downcast::<Self>()
            .expect("launcher window");
        cx.spawn(async move |_, cx| {
            while let Ok(event) = rx.recv().await {
                let result = handle.update(cx, |this, window, cx| match event {
                    tray::Event::Show => this.show(window, cx),
                    tray::Event::Switch(name) => this.switch(&name, Some(window), cx),
                    tray::Event::Quit => {
                        if !this.hidden {
                            this.remember_window(window);
                        }
                        this.quit(cx);
                    }
                });
                if result.is_err() {
                    break;
                }
            }
        })
        .detach();
        self.refresh_status(window, cx);
    }

    fn show(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        let started = Instant::now();
        let restore = self.hidden;
        self.hidden = false;
        if let Ok(hwnd) = platform::hwnd(window) {
            platform::show(hwnd);
        }
        if restore {
            window.on_next_frame(move |_, _| {
                trace(&format!("restore_frame_ms {:.3}", ms(started.elapsed())))
            });
        }
        self.refresh_status(window, cx);
        cx.notify();
    }

    fn quit(&mut self, cx: &mut Context<Self>) {
        if self.quitting {
            return;
        }
        self.refresh = None;
        self.finish_pending_click(cx);
        self.quitting = true;
        if let Some(cancelled) = self.cancel_operation.clone() {
            let deadline = cx.background_executor().timer(Duration::from_secs(6));
            cx.spawn(async move |this, cx| {
                deadline.await;
                cancelled.store(true, Ordering::Release);
                let _ = this.update(cx, |_, cx| cx.quit());
            })
            .detach();
        } else {
            cx.quit();
        }
    }

    fn remember_window(&mut self, window: &Window) {
        let bounds = window.bounds();
        self.state.window = Some(WindowState {
            x: bounds.origin.x.into(),
            y: bounds.origin.y.into(),
            width: bounds.size.width.into(),
            height: bounds.size.height.into(),
        });
        self.persist();
    }

    fn selected(&self) -> Option<&Group> {
        let name = self.state.selected.as_ref()?;
        self.state.groups.iter().find(|group| &group.name == name)
    }

    fn update_tray(&self) {
        let names: Vec<_> = self.state.groups.iter().map(|g| g.name.clone()).collect();
        let active = self.state.active.as_ref().map(|a| a.group.clone());
        self.tray.update(names, active, self.busy);
    }

    fn persist(&mut self) {
        if self.load_error.is_some() {
            self.status = "当前编辑尚未保存，请先恢复配置。".into();
        } else if let Err(error) = state::save(&self.state_path, &self.state) {
            self.status = format!("保存失败：{error:#}");
        }
    }

    fn save_recovered(&mut self, state: &State) -> anyhow::Result<()> {
        if self.load_error.is_some() {
            let stamp = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)?
                .as_millis();
            std::fs::copy(
                &self.state_path,
                self.state_path
                    .with_extension(format!("invalid-{stamp}.json")),
            )?;
        }
        state::save(&self.state_path, state)?;
        self.load_error = None;
        Ok(())
    }

    fn recover(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        let answer = window.prompt(
            PromptLevel::Warning,
            "备份损坏的配置并保存当前列表？",
            None,
            &["取消", "备份并保存"],
            cx,
        );
        cx.spawn(async move |this, cx| {
            if answer.await.ok() != Some(1) {
                return;
            }
            let _ = this.update(cx, |this, cx| {
                this.status = match this.save_recovered(&this.state.clone()) {
                    Ok(()) => "已备份损坏的文件并保存当前配置".into(),
                    Err(error) => format!("恢复失败：{error:#}"),
                };
                cx.notify();
            });
        })
        .detach();
    }

    fn refresh_status(&mut self, window: &Window, cx: &mut Context<Self>) {
        if self.hidden || self.busy || self.quitting {
            return;
        }
        let Ok(hwnd) = platform::hwnd(window) else {
            return;
        };
        let hwnd = hwnd.0 as isize;
        let executor = cx.background_executor().clone();
        self.refresh = Some(cx.spawn(async move |this, cx| {
            loop {
                let paths = this.update(cx, |this, _| {
                    let visible = platform::visible(windows::Win32::Foundation::HWND(hwnd as _));
                    if !visible {
                        return None;
                    }
                    let group = this.selected()?;
                    let paths: Vec<_> = group.apps.iter().map(|app| app.path.clone()).collect();
                    let missing: Vec<_> = paths
                        .iter()
                        .filter(|path| !this.icons.contains_key(*path))
                        .cloned()
                        .collect();
                    Some((paths, missing))
                });
                if let Ok(Some((paths, missing))) = paths
                    && !paths.is_empty()
                {
                    let (running, icons) = executor
                        .spawn(async move {
                            trace("scan");
                            let running = process::running_paths(&paths);
                            let icons = platform::app_icons(missing);
                            (running, icons)
                        })
                        .await;
                    if this
                        .update(cx, |this, cx| {
                            let has_icons = !icons.is_empty();
                            this.icons.extend(icons);
                            let changed = if let Ok(running) = running {
                                let changed = this.running != running;
                                this.running = running;
                                changed
                            } else {
                                false
                            };
                            if has_icons || changed {
                                cx.notify();
                            }
                        })
                        .is_err()
                    {
                        break;
                    }
                }
                executor.timer(Duration::from_secs(2)).await;
            }
        }));
    }

    fn switch(&mut self, name: &str, window: Option<&Window>, cx: &mut Context<Self>) {
        if let Some(group) = self
            .state
            .groups
            .iter()
            .find(|group| group.name == name)
            .cloned()
        {
            let label = format!("正在切换到 {name}…");
            self.run(
                Command::Switch {
                    group,
                    previous: self.state.active.clone(),
                },
                label,
                window,
                cx,
            );
        }
    }

    fn run(
        &mut self,
        command: Command,
        label: String,
        window: Option<&Window>,
        cx: &mut Context<Self>,
    ) {
        if self.busy || self.quitting {
            return;
        }
        let started = Instant::now();
        self.busy = true;
        let cancelled = Arc::new(AtomicBool::new(false));
        self.cancel_operation = Some(cancelled.clone());
        self.refresh = None;
        self.status = label;
        self.failures.clear();
        self.forceable.clear();
        self.update_tray();
        cx.notify();
        let executor = cx.background_executor().clone();
        let handle = window.and_then(|window| window.window_handle().downcast::<Self>());
        cx.spawn(async move |this, cx| {
            let outcome = executor
                .spawn(async move {
                    let queue_time = started.elapsed();
                    trace("command");
                    let outcome = process::run_with_cancel(command, &cancelled);
                    trace(&format!(
                        "dispatch_ms {:.3}",
                        ms(outcome
                            .first_request_after
                            .map_or_else(|| started.elapsed(), |time| queue_time + time))
                    ));
                    outcome
                })
                .await;
            let _ = this.update(cx, |this, cx| {
                this.busy = false;
                this.cancel_operation = None;
                this.status = outcome.summary;
                this.failures = outcome.failures;
                this.forceable = outcome.forceable;
                if let Some(applied) = outcome.applied {
                    this.state.active = Some(applied);
                    this.persist();
                }
                this.update_tray();
                if this.hidden {
                    this.tray.notify("AProgram", &this.status);
                }
                if this.quitting {
                    cx.quit();
                }
                cx.notify();
            });
            if let Some(handle) = handle {
                let _ = handle.update(cx, |this, window, cx| this.refresh_status(window, cx));
            }
        })
        .detach();
    }

    fn add_paths(&mut self, paths: &[PathBuf], window: &Window, cx: &mut Context<Self>) {
        let Some(name) = &self.state.selected else {
            return;
        };
        let Some(group) = self.state.groups.iter_mut().find(|g| &g.name == name) else {
            return;
        };
        let mut rejected = 0;
        for path in paths {
            let allowed = path
                .extension()
                .and_then(|ext| ext.to_str())
                .is_some_and(|ext| {
                    ext.eq_ignore_ascii_case("exe") || ext.eq_ignore_ascii_case("lnk")
                });
            if !allowed || !path.is_file() {
                rejected += 1;
                continue;
            }
            if !group.apps.iter().any(|app| app.path == *path) {
                group.apps.push(AppEntry {
                    path: path.clone(),
                    enabled: true,
                });
            }
        }
        if rejected > 0 {
            self.status = format!("{rejected} 个文件未添加，请选择 EXE 或快捷方式");
        }
        self.persist();
        self.refresh_status(window, cx);
        cx.notify();
    }

    fn select_paths(&mut self, window: &Window, cx: &mut Context<Self>) {
        let response = cx.prompt_for_paths(PathPromptOptions {
            files: true,
            directories: false,
            multiple: true,
            prompt: Some("添加应用".into()),
        });
        let handle = window.window_handle().downcast::<Self>().unwrap();
        let group = self.state.selected.clone();
        cx.spawn(async move |_, cx| {
            if let Ok(Ok(Some(paths))) = response.await {
                let _ = handle.update(cx, |this, window, cx| {
                    if this.state.selected == group {
                        this.add_paths(&paths, window, cx);
                    }
                });
            }
        })
        .detach();
    }

    fn import(&mut self, directory: Option<PathBuf>, window: &mut Window, cx: &mut Context<Self>) {
        let confirm = (!self.state.groups.is_empty()).then(|| {
            window.prompt(
                PromptLevel::Warning,
                "导入旧版配置？",
                Some("导入的软件组将替换当前列表。"),
                &["取消", "导入"],
                cx,
            )
        });
        let executor = cx.background_executor().clone();
        let handle = window.window_handle().downcast::<Self>().unwrap();
        cx.spawn(async move |_, cx| {
            if let Some(confirm) = confirm
                && confirm.await.ok() != Some(1)
            {
                return;
            }
            let directory = match directory {
                Some(path) => Some(path),
                None => {
                    let response = cx.update(|app| {
                        app.prompt_for_paths(PathPromptOptions {
                            files: false,
                            directories: true,
                            multiple: false,
                            prompt: Some("选择旧版 AProgram 所在目录".into()),
                        })
                    });
                    match response {
                        Ok(response) => match response.await {
                            Ok(Ok(Some(paths))) => paths.into_iter().next(),
                            _ => None,
                        },
                        Err(_) => None,
                    }
                }
            };
            let Some(directory) = directory else { return };
            let imported = executor
                .spawn(async move { state::import_legacy(&directory) })
                .await;
            let _ = handle.update(cx, |this, window, cx| {
                match imported {
                    Ok(mut state) => {
                        if this.busy {
                            this.status = "请等待当前操作完成后再导入".into();
                            cx.notify();
                            return;
                        }
                        state.selected = state.groups.first().map(|group| group.name.clone());
                        state.window = this.state.window.clone();
                        let auto_start_enabled = platform::auto_start_enabled();
                        let auto_start_pending = state.settings.auto_start && !auto_start_enabled;
                        state.settings.auto_start |= auto_start_enabled;
                        match this.save_recovered(&state) {
                            Ok(()) => {
                                this.state = state;
                                this.auto_start_pending = auto_start_pending;
                                this.legacy_dir = None;
                                this.status = "已导入旧版配置".into();
                                this.update_tray();
                                this.refresh_status(window, cx);
                            }
                            Err(error) => this.status = format!("保存导入结果失败：{error:#}"),
                        }
                    }
                    Err(error) => this.status = format!("导入失败：{error:#}"),
                }
                cx.notify();
            });
        })
        .detach();
    }

    fn edit_name(&mut self, action: NameAction, window: &Window, cx: &mut Context<Self>) {
        let Ok(hwnd) = platform::hwnd(window) else {
            return;
        };
        let owner = hwnd.0 as isize;
        let (title, initial) = match &action {
            NameAction::New => ("新建软件组", String::new()),
            NameAction::Rename(name) => ("重命名软件组", name.clone()),
            NameAction::Copy(name) => ("复制软件组", format!("{name} 副本")),
        };
        let executor = cx.background_executor().clone();
        cx.spawn(async move |this, cx| {
            let result = executor
                .spawn(async move { platform::group_name(owner, title, &initial) })
                .await;
            let _ = this.update(cx, |this, cx| match result {
                Ok(Some(name)) => this.apply_name(action, name.trim(), cx),
                Ok(None) => {}
                Err(error) => {
                    this.status = error.to_string();
                    cx.notify();
                }
            });
        })
        .detach();
    }

    fn apply_name(&mut self, action: NameAction, name: &str, cx: &mut Context<Self>) {
        if self.busy && matches!(&action, NameAction::Rename(_)) {
            self.status = "请等待当前切换完成后再重命名".into();
            cx.notify();
            return;
        }
        if matches!(&action, NameAction::Rename(old) if old == name) {
            return;
        }
        if name.is_empty() || self.state.groups.iter().any(|group| group.name == name) {
            self.status = if name.is_empty() {
                "请输入组名"
            } else {
                "组名已存在"
            }
            .into();
            cx.notify();
            return;
        }
        match action {
            NameAction::New => self.state.groups.push(Group {
                name: name.into(),
                apps: Vec::new(),
            }),
            NameAction::Copy(old) => {
                let Some(mut group) = self
                    .state
                    .groups
                    .iter()
                    .find(|group| group.name == old)
                    .cloned()
                else {
                    return;
                };
                group.name = name.into();
                for app in &mut group.apps {
                    app.enabled = true;
                }
                self.state.groups.push(group);
            }
            NameAction::Rename(old) => {
                let Some(group) = self.state.groups.iter_mut().find(|group| group.name == old)
                else {
                    return;
                };
                group.name = name.into();
                if let Some(active) = &mut self.state.active
                    && active.group == old
                {
                    active.group = name.into();
                }
            }
        }
        self.state.selected = Some(name.into());
        self.persist();
        self.update_tray();
        cx.notify();
    }

    fn delete_group(&mut self, name: String, window: &mut Window, cx: &mut Context<Self>) {
        let answer = window.prompt(
            PromptLevel::Warning,
            &format!("删除「{name}」？"),
            None,
            &["取消", "删除"],
            cx,
        );
        cx.spawn(async move |this, cx| {
            if answer.await.ok() != Some(1) {
                return;
            }
            let _ = this.update(cx, |this, cx| {
                if this.busy {
                    return;
                }
                this.state.groups.retain(|group| group.name != name);
                if this.state.selected.as_deref() == Some(&name) {
                    this.state.selected = this.state.groups.first().map(|group| group.name.clone());
                }
                this.persist();
                this.update_tray();
                cx.notify();
            });
        })
        .detach();
    }

    fn confirm_command(&mut self, command: Command, window: &mut Window, cx: &mut Context<Self>) {
        let (question, detail, label, progress) = match &command {
            Command::Close(group) => (
                format!("关闭「{}」中的应用？", group.name),
                "应用可能提示保存文件。",
                "关闭",
                "正在关闭软件组…",
            ),
            Command::Force(_) => (
                "强制结束这些应用？".into(),
                "未保存的更改可能丢失。",
                "强制结束",
                "正在结束应用…",
            ),
            _ => return,
        };
        let answer = window.prompt(
            PromptLevel::Warning,
            &question,
            Some(detail),
            &["取消", label],
            cx,
        );
        let handle = window.window_handle().downcast::<Self>().unwrap();
        cx.spawn(async move |_, cx| {
            if answer.await.ok() == Some(1) {
                let _ = handle.update(cx, |this, window, cx| {
                    this.run(command, progress.into(), Some(window), cx)
                });
            }
        })
        .detach();
    }

    fn toggle_app(&mut self, path: &Path, cx: &mut Context<Self>) {
        if let Some(app) = self
            .state
            .groups
            .iter_mut()
            .find(|group| Some(&group.name) == self.state.selected.as_ref())
            .and_then(|group| group.apps.iter_mut().find(|app| app.path == path))
        {
            app.enabled = !app.enabled;
            self.persist();
            cx.notify();
        }
    }

    fn finish_pending_click(&mut self, cx: &mut Context<Self>) {
        if let Some((path, _)) = self.pending_click.take() {
            self.toggle_app(&path, cx);
        }
    }

    fn app_click(&mut self, path: &Path, count: usize, window: &Window, cx: &mut Context<Self>) {
        if count == 2
            && self
                .pending_click
                .as_ref()
                .is_some_and(|(pending, _)| pending == path)
        {
            self.pending_click = None;
            self.run(
                Command::Open(path.to_owned()),
                "正在打开应用…".into(),
                Some(window),
                cx,
            );
        } else {
            self.finish_pending_click(cx);
            let timer = cx
                .background_executor()
                .timer(platform::double_click_time());
            let task = cx.spawn(async move |this, cx| {
                timer.await;
                let _ = this.update(cx, |this, cx| this.finish_pending_click(cx));
            });
            self.pending_click = Some((path.to_owned(), task));
        }
    }

    fn remove_app(&mut self, path: &Path, window: &Window, cx: &mut Context<Self>) {
        if let Some(group) = self
            .state
            .groups
            .iter_mut()
            .find(|group| Some(&group.name) == self.state.selected.as_ref())
        {
            group.apps.retain(|app| app.path != path);
            self.persist();
            self.refresh_status(window, cx);
            cx.notify();
        }
    }

    fn toggle_auto_start(&mut self, cx: &mut Context<Self>) {
        let enabled = self.auto_start_pending || !self.state.settings.auto_start;
        match platform::set_auto_start(enabled) {
            Ok(()) => {
                self.state.settings.auto_start = enabled;
                self.auto_start_pending = false;
                self.persist();
            }
            Err(error) => self.status = format!("更改开机自启失败：{error:#}"),
        }
        cx.notify();
    }
}

fn ms(time: Duration) -> f64 {
    time.as_secs_f64() * 1000.
}

fn trace(line: &str) {
    static LOG: OnceLock<Option<Mutex<File>>> = OnceLock::new();
    if let Some(file) = LOG.get_or_init(|| {
        let path = std::env::var_os("APROGRAM_TRACE")?;
        OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .ok()
            .map(Mutex::new)
    }) && let Ok(mut file) = file.lock()
    {
        let _ = writeln!(file, "{line}");
    }
}
