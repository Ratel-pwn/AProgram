use std::{
    collections::{HashMap, HashSet},
    ffi::{OsStr, OsString},
    fs,
    os::windows::ffi::{OsStrExt, OsStringExt},
    path::{Component, Path, PathBuf, Prefix},
    sync::atomic::{AtomicBool, Ordering},
    thread,
    time::{Duration, Instant},
};

use anyhow::{Context, Result, bail, ensure};
use windows::{
    Win32::{
        Foundation::{
            CloseHandle, CompareObjectHandles, ERROR_INVALID_PARAMETER, ERROR_NO_MORE_FILES,
            HANDLE, HWND, LPARAM, WAIT_OBJECT_0, WAIT_TIMEOUT, WPARAM,
        },
        Globalization::{CSTR_EQUAL, CompareStringOrdinal},
        System::{
            Com::{
                CLSCTX_INPROC_SERVER, COINIT_APARTMENTTHREADED, COINIT_DISABLE_OLE1DDE,
                CoCreateInstance, CoInitializeEx, CoUninitialize, IPersistFile, STGM_READ,
            },
            Diagnostics::ToolHelp::{
                CreateToolhelp32Snapshot, PROCESSENTRY32W, Process32FirstW, Process32NextW,
                TH32CS_SNAPPROCESS,
            },
            Threading::{
                GetCurrentProcessId, OpenProcess, PROCESS_NAME_WIN32,
                PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_SYNCHRONIZE, PROCESS_TERMINATE,
                QueryFullProcessImageNameW, TerminateProcess, WaitForSingleObject,
            },
        },
        UI::{
            Shell::{
                IShellLinkW, SEE_MASK_FLAG_NO_UI, SEE_MASK_NOASYNC, SHELLEXECUTEINFOW,
                ShellExecuteExW, ShellLink,
            },
            WindowsAndMessaging::{
                EnumWindows, GetWindowThreadProcessId, PostMessageW, SW_SHOWNORMAL, WM_CLOSE,
            },
        },
    },
    core::{BOOL, Error as WinError, Interface, PCWSTR, PWSTR},
};

use crate::state::{Applied, Group};

pub enum Command {
    Switch {
        group: Group,
        previous: Option<Applied>,
    },
    Launch(Group),
    Close(Group),
    Force(Vec<PathBuf>),
    Open(PathBuf),
}

pub struct Outcome {
    pub applied: Option<Applied>,
    pub summary: String,
    pub failures: Vec<String>,
    pub forceable: Vec<PathBuf>,
    pub first_request_after: Option<Duration>,
}

const CLOSE_TIMEOUT: Duration = Duration::from_secs(3);
const PROCESS_ACCESS: windows::Win32::System::Threading::PROCESS_ACCESS_RIGHTS =
    windows::Win32::System::Threading::PROCESS_ACCESS_RIGHTS(
        PROCESS_QUERY_LIMITED_INFORMATION.0 | PROCESS_SYNCHRONIZE.0,
    );

struct Apartment;

impl Apartment {
    fn initialize() -> Result<Self> {
        unsafe {
            CoInitializeEx(None, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE).ok()?;
        }
        Ok(Self)
    }
}

impl Drop for Apartment {
    fn drop(&mut self) {
        unsafe { CoUninitialize() }
    }
}

pub(crate) fn in_sta<T: Send>(operation: impl FnOnce() -> Result<T> + Send) -> Result<T> {
    if let Ok(_apartment) = Apartment::initialize() {
        return operation();
    }
    thread::scope(|scope| {
        thread::Builder::new()
            .name("aprogram-shell".to_owned())
            .spawn_scoped(scope, || {
                let _apartment = Apartment::initialize().context("无法初始化 Windows Shell")?;
                operation()
            })?
            .join()
            .map_err(|_| anyhow::anyhow!("Windows 操作线程异常退出"))?
    })
}

struct Handle(HANDLE);

impl Drop for Handle {
    fn drop(&mut self) {
        let _ = unsafe { CloseHandle(self.0) };
    }
}

#[derive(Clone)]
struct Image {
    target: PathBuf,
    canonical: PathBuf,
}

#[derive(Clone)]
struct Target {
    original: PathBuf,
    image: Result<Image, String>,
}

impl Target {
    fn resolve(original: &Path) -> Self {
        Self {
            original: original.to_owned(),
            image: resolve_image(original).map_err(|err| format!("{err:#}")),
        }
    }

    fn recorded(original: &Path) -> Self {
        let image = if original.is_absolute() && !has_extension(original, "lnk") {
            // Keep the recorded executable identity even if this path now points through a link.
            Ok(Image {
                target: original.to_owned(),
                canonical: original.to_owned(),
            })
        } else {
            Err("旧记录缺少可验证的可执行文件路径".to_owned())
        };
        Self {
            original: original.to_owned(),
            image,
        }
    }

    fn same_as(&self, other: &Self) -> bool {
        match (&self.image, &other.image) {
            (Ok(a), Ok(b)) => same_path(&a.canonical, &b.canonical),
            _ => same_name(self.original.as_os_str(), other.original.as_os_str()),
        }
    }
}

fn same_path(a: &Path, b: &Path) -> bool {
    if same_name(a.as_os_str(), b.as_os_str()) {
        return true;
    }
    // Process image names and older records can omit the canonical Win32 prefix.
    let (mut a, mut b) = (a.components(), b.components());
    let (Some(Component::Prefix(a_prefix)), Some(Component::Prefix(b_prefix))) =
        (a.next(), b.next())
    else {
        return false;
    };
    let equal_prefix = match (a_prefix.kind(), b_prefix.kind()) {
        (Prefix::Disk(a) | Prefix::VerbatimDisk(a), Prefix::Disk(b) | Prefix::VerbatimDisk(b)) => {
            a.eq_ignore_ascii_case(&b)
        }
        (
            Prefix::UNC(a_server, a_share) | Prefix::VerbatimUNC(a_server, a_share),
            Prefix::UNC(b_server, b_share) | Prefix::VerbatimUNC(b_server, b_share),
        ) => same_name(a_server, b_server) && same_name(a_share, b_share),
        _ => false,
    };
    equal_prefix
        && a.clone().count() == b.clone().count()
        && a.zip(b)
            .all(|(a, b)| same_name(a.as_os_str(), b.as_os_str()))
}

fn same_name(a: &OsStr, b: &OsStr) -> bool {
    if a == b {
        return true;
    }
    let a: Vec<u16> = a.encode_wide().collect();
    let b: Vec<u16> = b.encode_wide().collect();
    unsafe { CompareStringOrdinal(&a, &b, true) == CSTR_EQUAL }
}

fn unique<'a>(targets: impl IntoIterator<Item = &'a Target>) -> Vec<&'a Target> {
    let mut result: Vec<&Target> = Vec::new();
    for target in targets {
        if !result.iter().any(|other| target.same_as(other)) {
            result.push(target);
        }
    }
    result
}

fn switch_plan<'a>(
    desired: &'a [Target],
    previous: &'a [Target],
    failed_open: &'a [Target],
    failed_close: &'a [Target],
) -> (Vec<&'a Target>, Vec<&'a Target>) {
    let close = unique(
        previous
            .iter()
            .chain(failed_close)
            .filter(|old| !desired.iter().any(|target| target.same_as(old))),
    );
    let open = unique(desired.iter().filter(|target| {
        !previous.iter().any(|old| target.same_as(old))
            || failed_open.iter().any(|old| target.same_as(old))
    }));
    (close, open)
}

fn has_extension(path: &Path, extension: &str) -> bool {
    path.extension()
        .is_some_and(|actual| actual.eq_ignore_ascii_case(extension))
}

fn wide_string(path: &Path) -> Result<Vec<u16>> {
    let mut wide: Vec<u16> = path.as_os_str().encode_wide().collect();
    ensure!(!wide.contains(&0), "路径包含无效字符");
    wide.push(0);
    Ok(wide)
}

fn resolve_image(original: &Path) -> Result<Image> {
    ensure!(original.is_file(), "文件不存在或无法访问");
    let target = if has_extension(original, "lnk") {
        resolve_shortcut(original).context("无法解析快捷方式")?
    } else {
        original.to_owned()
    };
    ensure!(has_extension(&target, "exe"), "目标须为 .exe 程序");
    let canonical = fs::canonicalize(&target).context("无法访问程序目标")?;
    ensure!(canonical.is_file(), "程序目标须为文件");
    Ok(Image { target, canonical })
}

fn resolve_shortcut(path: &Path) -> Result<PathBuf> {
    let absolute = std::path::absolute(path)?;
    let path = wide_string(&absolute)?;
    let link: IShellLinkW = unsafe { CoCreateInstance(&ShellLink, None, CLSCTX_INPROC_SERVER)? };
    let file: IPersistFile = link.cast()?;
    unsafe { file.Load(PCWSTR(path.as_ptr()), STGM_READ)? };
    // GetPath can succeed with S_FALSE and leave an empty target.
    let mut target = [0; 260];
    unsafe { link.GetPath(&mut target, std::ptr::null_mut(), 0)? };
    let length = target
        .iter()
        .position(|&unit| unit == 0)
        .unwrap_or(target.len());
    ensure!(
        length > 0 && length < target.len(),
        "无法获取可执行文件路径"
    );
    Ok(PathBuf::from(OsString::from_wide(&target[..length])))
}

fn launch(path: &Path, request: &mut impl FnMut() -> Result<()>) -> Result<()> {
    let absolute = std::path::absolute(path)?;
    let file = wide_string(&absolute)?;
    let directory = absolute.parent().map(wide_string).transpose()?;
    let mut info = SHELLEXECUTEINFOW {
        cbSize: size_of::<SHELLEXECUTEINFOW>() as u32,
        fMask: SEE_MASK_FLAG_NO_UI | SEE_MASK_NOASYNC,
        lpFile: PCWSTR(file.as_ptr()),
        // For .lnk the Shell supplies the working directory stored in the link.
        lpDirectory: if has_extension(path, "lnk") {
            PCWSTR::null()
        } else {
            directory
                .as_ref()
                .map_or(PCWSTR::null(), |path| PCWSTR(path.as_ptr()))
        },
        nShow: SW_SHOWNORMAL.0,
        ..Default::default()
    };
    request()?;
    unsafe { ShellExecuteExW(&mut info) }.context("Windows Shell 启动失败")
}

struct Running {
    pid: u32,
    handle: Handle,
    canonical: PathBuf,
}

impl Running {
    fn open(pid: u32) -> Result<Option<Self>> {
        let handle = match unsafe { OpenProcess(PROCESS_ACCESS, false, pid) } {
            Ok(handle) => Handle(handle),
            Err(err) if err.code() == ERROR_INVALID_PARAMETER.to_hresult() => return Ok(None),
            Err(err) => return Err(err.into()),
        };
        if !still_running(&handle, 0)? {
            return Ok(None);
        }

        let image = match process_image(&handle) {
            Ok(path) => path,
            Err(_) if !still_running(&handle, 0)? => return Ok(None),
            Err(err) => return Err(err.into()),
        };
        let canonical = fs::canonicalize(&image).unwrap_or(image);
        Ok(Some(Self {
            pid,
            handle,
            canonical,
        }))
    }

    fn matches(&self, image: &Image) -> bool {
        same_path(&self.canonical, &image.canonical)
    }

    fn request_close(
        &self,
        windows: &[HWND],
        request: &mut impl FnMut() -> Result<()>,
    ) -> Result<()> {
        let mut posted = false;
        let mut error = None;
        for &window in windows {
            let mut owner = 0;
            let thread_id = unsafe { GetWindowThreadProcessId(window, Some(&mut owner)) };
            if thread_id == 0 || owner != self.pid {
                continue;
            }
            // A signaled snapshot handle identifies the old process even if Windows reused its PID.
            if !still_running(&self.handle, 0)? {
                return Ok(());
            }
            request()?;
            match unsafe { PostMessageW(Some(window), WM_CLOSE, WPARAM(0), LPARAM(0)) } {
                Ok(()) => posted = true,
                Err(err) => error = Some(err),
            }
        }

        if posted || !still_running(&self.handle, 0)? {
            return Ok(());
        }
        if let Some(err) = error {
            return Err(err).context("无法发送关闭请求");
        }
        bail!("进程没有可关闭的窗口")
    }

    fn force(&self, request: &mut impl FnMut() -> Result<()>) -> Result<()> {
        if !still_running(&self.handle, 0)? {
            return Ok(());
        }
        let handle = match unsafe { OpenProcess(PROCESS_TERMINATE, false, self.pid) } {
            Ok(handle) => Handle(handle),
            Err(_) if !still_running(&self.handle, 0)? => return Ok(()),
            Err(err) => return Err(err).context("无法获取进程的结束权限"),
        };
        if !unsafe { CompareObjectHandles(handle.0, self.handle.0) }.as_bool() {
            return Ok(());
        }
        request()?;
        match unsafe { TerminateProcess(handle.0, 1) } {
            Ok(()) => Ok(()),
            Err(_) if !still_running(&self.handle, 0)? => Ok(()),
            Err(err) => Err(err).context("无法强制结束进程"),
        }
    }
}

fn process_image(handle: &Handle) -> windows::core::Result<PathBuf> {
    let mut image = vec![0; 32_768];
    let mut length = image.len() as u32;
    unsafe {
        QueryFullProcessImageNameW(
            handle.0,
            PROCESS_NAME_WIN32,
            PWSTR(image.as_mut_ptr()),
            &mut length,
        )?
    };
    Ok(PathBuf::from(OsString::from_wide(
        &image[..length as usize],
    )))
}

fn still_running(handle: &Handle, timeout_ms: u32) -> Result<bool> {
    match unsafe { WaitForSingleObject(handle.0, timeout_ms) } {
        WAIT_TIMEOUT => Ok(true),
        WAIT_OBJECT_0 => Ok(false),
        _ => Err(WinError::from_win32()).context("无法检查进程状态"),
    }
}

#[derive(Default)]
struct Snapshot {
    processes: Vec<Running>,
    inaccessible: Vec<(OsString, String)>,
}

impl Snapshot {
    fn take<'a>(targets: impl IntoIterator<Item = &'a Target>) -> Result<Self> {
        let names: HashSet<_> = targets
            .into_iter()
            .filter_map(|target| target.image.as_ref().ok())
            .flat_map(|image| [image.target.file_name(), image.canonical.file_name()])
            .flatten()
            .collect();
        let mut result = Self::default();
        if names.is_empty() {
            return Ok(result);
        }

        let current_pid = unsafe { GetCurrentProcessId() };
        let handle = Handle(unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)? });
        let mut entry = PROCESSENTRY32W {
            dwSize: size_of::<PROCESSENTRY32W>() as u32,
            ..Default::default()
        };
        let mut next = unsafe { Process32FirstW(handle.0, &mut entry) };
        while next.is_ok() {
            let pid = entry.th32ProcessID;
            if pid != 0 && pid != current_pid {
                let length = entry
                    .szExeFile
                    .iter()
                    .position(|&unit| unit == 0)
                    .unwrap_or(entry.szExeFile.len());
                let name = OsString::from_wide(&entry.szExeFile[..length]);
                if names.iter().any(|candidate| same_name(&name, candidate)) {
                    match Running::open(pid) {
                        Ok(Some(process)) => result.processes.push(process),
                        Ok(None) => {}
                        Err(err) => result
                            .inaccessible
                            .push((name, format!("无法核对进程 {pid} 的路径（{err:#}）"))),
                    }
                }
            }
            next = unsafe { Process32NextW(handle.0, &mut entry) };
        }
        if let Err(err) = next
            && err.code() != ERROR_NO_MORE_FILES.to_hresult()
        {
            return Err(err).context("无法读取 Windows 进程快照");
        }
        Ok(result)
    }

    fn matching<'a>(&'a self, image: &'a Image) -> impl Iterator<Item = &'a Running> {
        self.processes
            .iter()
            .filter(|process| process.matches(image))
    }

    fn inaccessible(&self, image: &Image) -> impl Iterator<Item = &str> {
        self.inaccessible.iter().filter_map(|(name, error)| {
            [image.target.file_name(), image.canonical.file_name()]
                .into_iter()
                .flatten()
                .any(|candidate| same_name(name, candidate))
                .then_some(error.as_str())
        })
    }
}

fn process_windows() -> Result<HashMap<u32, Vec<HWND>>> {
    unsafe extern "system" fn collect(window: HWND, state: LPARAM) -> BOOL {
        let mut pid = 0;
        if unsafe { GetWindowThreadProcessId(window, Some(&mut pid)) } != 0 {
            // EnumWindows calls back synchronously with the map alive on this stack.
            let windows = unsafe { &mut *(state.0 as *mut HashMap<u32, Vec<HWND>>) };
            windows.entry(pid).or_default().push(window);
        }
        true.into()
    }

    let mut windows = HashMap::new();
    let data = &mut windows as *mut HashMap<u32, Vec<HWND>>;
    unsafe { EnumWindows(Some(collect), LPARAM(data as isize)) }.context("无法枚举应用窗口")?;
    Ok(windows)
}

struct CloseResult<'a> {
    target: &'a Target,
    processes: Vec<(&'a Running, Result<()>)>,
    errors: Vec<String>,
    running: bool,
}

impl<'a> CloseResult<'a> {
    fn dispatch(
        target: &'a Target,
        snapshot: &'a Result<Snapshot>,
        windows: &Result<HashMap<u32, Vec<HWND>>>,
        force: bool,
        request: &mut impl FnMut() -> Result<()>,
    ) -> Self {
        let mut result = Self {
            target,
            processes: Vec::new(),
            errors: Vec::new(),
            running: false,
        };
        let (image, snapshot) = match app_image(target, snapshot) {
            Ok(pair) => pair,
            Err(err) => {
                result.errors.push(err);
                return result;
            }
        };

        result
            .errors
            .extend(snapshot.inaccessible(image).map(str::to_owned));
        for process in snapshot.matching(image) {
            let operation = if force {
                process.force(request)
            } else {
                match windows {
                    Ok(windows) => process.request_close(
                        windows.get(&process.pid).map_or(&[], Vec::as_slice),
                        request,
                    ),
                    Err(err) => Err(anyhow::anyhow!("{err:#}")),
                }
            };
            result.processes.push((process, operation));
        }
        result
    }

    fn wait(&mut self, deadline: Instant) {
        for (process, operation) in &self.processes {
            let timeout = if operation.is_ok() {
                deadline
                    .saturating_duration_since(Instant::now())
                    .as_millis() as u32
            } else {
                0
            };
            match still_running(&process.handle, timeout) {
                Ok(true) => {
                    self.running = true;
                    let error = match operation {
                        Ok(()) => format!("进程 {} 在等待期限内仍在运行", process.pid),
                        Err(err) => format!("进程 {} 仍在运行（{err:#}）", process.pid),
                    };
                    self.errors.push(error);
                }
                Ok(false) => {}
                Err(err) => self.errors.push(format!("{err:#}")),
            }
        }
    }
}

fn app_image<'a>(
    target: &'a Target,
    snapshot: &'a Result<Snapshot>,
) -> Result<(&'a Image, &'a Snapshot), String> {
    let image = target.image.as_ref().map_err(String::clone)?;
    let snapshot = snapshot.as_ref().map_err(|err| format!("{err:#}"))?;
    Ok((image, snapshot))
}

fn open_if_needed(
    target: &Target,
    snapshot: &Result<Snapshot>,
    request: &mut impl FnMut() -> Result<()>,
) -> Result<(), String> {
    let (image, snapshot) = app_image(target, snapshot)?;
    for process in snapshot.matching(image) {
        if still_running(&process.handle, 0).map_err(|err| format!("{err:#}"))? {
            return Ok(());
        }
    }
    if let Some(error) = snapshot.inaccessible(image).next() {
        return Err(error.to_owned());
    }
    launch(&target.original, request).map_err(|err| format!("{err:#}"))
}

fn enabled(group: &Group) -> Vec<PathBuf> {
    group
        .apps
        .iter()
        .filter(|item| item.enabled)
        .map(|item| item.path.clone())
        .collect()
}

struct Batch {
    summary: String,
    opens: Vec<PathBuf>,
    closes: Vec<PathBuf>,
    retry_open: Vec<PathBuf>,
    retry_close: Vec<PathBuf>,
    applied: Option<Applied>,
    force: bool,
    single: bool,
}

impl Batch {
    fn new(summary: String) -> Self {
        Self {
            summary,
            opens: Vec::new(),
            closes: Vec::new(),
            retry_open: Vec::new(),
            retry_close: Vec::new(),
            applied: None,
            force: false,
            single: false,
        }
    }

    fn from_command(command: Command) -> Self {
        match command {
            Command::Switch { group, previous } => {
                let mut batch = Self::new(format!("已切换到 {}", group.name));
                batch.opens = enabled(&group);
                if let Some(previous) = previous {
                    batch.closes = previous.enabled;
                    batch.retry_close = previous.failed_close;
                    if previous.group == group.name {
                        batch.retry_open = previous.failed_open;
                    }
                }
                batch.applied = Some(Applied {
                    group: group.name,
                    enabled: Vec::new(),
                    failed_open: Vec::new(),
                    failed_close: Vec::new(),
                });
                batch
            }
            Command::Launch(group) => {
                let mut batch = Self::new(format!("已执行 {} 的启动操作", group.name));
                batch.opens = enabled(&group);
                batch
            }
            Command::Close(group) => {
                let mut batch = Self::new(format!("已执行 {} 的关闭操作", group.name));
                batch.closes = enabled(&group);
                batch
            }
            Command::Force(paths) => {
                let mut batch = Self::new("已执行强制结束操作".to_owned());
                batch.closes = paths;
                batch.force = true;
                batch
            }
            Command::Open(path) => {
                let mut batch = Self::new("已执行启动操作".to_owned());
                batch.opens = vec![path];
                batch.single = true;
                batch
            }
        }
    }
}

#[cfg(test)]
fn run(command: Command) -> Outcome {
    run_with_cancel(command, &AtomicBool::new(false))
}

pub fn run_with_cancel(command: Command, cancelled: &AtomicBool) -> Outcome {
    let started = Instant::now();
    let mut batch = Batch::from_command(command);
    let mut failures = Vec::new();
    let mut forceable = Vec::new();
    let mut first_request_after = None;

    match in_sta(|| {
        ensure!(!cancelled.load(Ordering::Acquire), "操作已取消");
        let mut request = || {
            ensure!(!cancelled.load(Ordering::Acquire), "操作已取消");
            first_request_after.get_or_insert_with(|| started.elapsed());
            Ok(())
        };
        run_batch(&mut batch, &mut request, &mut failures, &mut forceable);
        Ok(())
    }) {
        Ok(()) => {}
        Err(err) => {
            batch.applied = None;
            batch.summary = "操作中断".to_owned();
            failures.push(format!("{err:#}"));
        }
    }

    if !failures.is_empty() {
        batch
            .summary
            .push_str(&format!("（{} 项待处理）", failures.len()));
    }
    Outcome {
        applied: batch.applied,
        summary: batch.summary,
        failures,
        forceable,
        first_request_after,
    }
}

fn run_batch(
    batch: &mut Batch,
    request: &mut impl FnMut() -> Result<()>,
    failures: &mut Vec<String>,
    forceable: &mut Vec<PathBuf>,
) {
    let mut cache = HashMap::new();
    let mut resolve = |paths: &[PathBuf]| {
        paths
            .iter()
            .map(|path| {
                cache
                    .entry(path.clone())
                    .or_insert_with(|| Target::resolve(path))
                    .clone()
            })
            .collect::<Vec<_>>()
    };
    let desired = resolve(&batch.opens);
    let previous = if batch.applied.is_some() || batch.force {
        batch
            .closes
            .iter()
            .map(|path| Target::recorded(path))
            .collect()
    } else {
        resolve(&batch.closes)
    };
    let failed_open = resolve(&batch.retry_open);
    let failed_close: Vec<_> = batch
        .retry_close
        .iter()
        .map(|path| Target::recorded(path))
        .collect();
    let (close, open) = if let Some(applied) = batch.applied.as_mut() {
        applied.enabled = unique(&desired)
            .into_iter()
            .filter_map(|target| {
                target
                    .image
                    .as_ref()
                    .ok()
                    .map(|image| image.canonical.clone())
            })
            .collect();
        switch_plan(&desired, &previous, &failed_open, &failed_close)
    } else {
        (unique(&previous), unique(&desired))
    };

    let snapshot = if batch.single {
        Ok(Snapshot::default())
    } else {
        Snapshot::take(close.iter().chain(&open).copied()).context("无法扫描应用进程")
    };
    let windows = if !batch.force
        && !close.is_empty()
        && snapshot
            .as_ref()
            .is_ok_and(|snapshot| !snapshot.processes.is_empty())
    {
        process_windows()
    } else {
        Ok(HashMap::new())
    };

    let mut closing: Vec<_> = close
        .into_iter()
        .map(|target| CloseResult::dispatch(target, &snapshot, &windows, batch.force, request))
        .collect();

    for target in open {
        let result =
            if batch.single {
                target.image.as_ref().map_err(String::clone).and_then(|_| {
                    launch(&target.original, request).map_err(|err| format!("{err:#}"))
                })
            } else {
                open_if_needed(target, &snapshot, request)
            };
        if let Err(err) = result {
            if let Some(applied) = batch.applied.as_mut() {
                applied.failed_open.push(target.original.clone());
            }
            failures.push(format!("无法启动 {} · {err}", target.original.display()));
        }
    }

    let deadline = Instant::now() + CLOSE_TIMEOUT;
    for result in &mut closing {
        result.wait(deadline);
        if !result.errors.is_empty() {
            if let Ok(image) = &result.target.image {
                if let Some(applied) = batch.applied.as_mut() {
                    applied.failed_close.push(image.canonical.clone());
                }
                if result.running && !batch.force {
                    forceable.push(image.canonical.clone());
                }
            }
            failures.push(format!(
                "无法关闭 {} · {}",
                result.target.original.display(),
                result.errors.join("，")
            ));
        }
    }
}

pub fn running_paths(paths: &[PathBuf]) -> Result<HashSet<PathBuf>> {
    in_sta(|| {
        let targets: Vec<_> = paths.iter().map(|path| Target::resolve(path)).collect();
        let snapshot = Snapshot::take(&targets)?;
        Ok(targets
            .iter()
            .filter(|target| {
                target.image.as_ref().is_ok_and(|image| {
                    snapshot
                        .matching(image)
                        .any(|process| matches!(still_running(&process.handle, 0), Ok(true)))
                })
            })
            .map(|target| target.original.clone())
            .collect())
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(original: &str, image: &str) -> Target {
        Target {
            original: PathBuf::from(original),
            image: Ok(Image {
                target: PathBuf::from(image),
                canonical: PathBuf::from(image),
            }),
        }
    }

    #[test]
    fn aliases_are_kept_and_distinct_paths_with_the_same_name_are_switched() {
        let previous = [
            entry(r"C:\Links\Shared.lnk", r"C:\Apps\Shared.exe"),
            entry(r"C:\Office\Tool.exe", r"C:\Office\Tool.exe"),
        ];
        let desired = [
            entry(r"C:\Apps\shared.exe", r"C:\Apps\shared.exe"),
            entry(r"C:\Games\Tool.exe", r"C:\Games\Tool.exe"),
        ];
        let (close, open) = switch_plan(&desired, &previous, &[], &[]);
        assert_eq!(close.len(), 1);
        assert_eq!(close[0].original, previous[1].original);
        assert_eq!(open.len(), 1);
        assert_eq!(open[0].original, desired[1].original);
    }

    #[test]
    fn failed_opens_retry_only_if_enabled_and_failed_closes_follow_the_target() {
        let keep = entry(r"C:\keep.exe", r"C:\keep.exe");
        let removed = entry(r"C:\removed.exe", r"C:\removed.exe");
        let pending = entry(r"C:\pending.exe", r"C:\pending.exe");
        let wanted = entry(r"C:\wanted.exe", r"C:\wanted.exe");
        let desired = [keep.clone(), wanted.clone()];
        let previous = [keep.clone(), removed.clone()];
        let failed_open = [keep.clone(), removed.clone()];
        let failed_close = [pending.clone(), wanted.clone()];
        let (close, open) = switch_plan(&desired, &previous, &failed_open, &failed_close);
        assert_eq!(
            close.iter().map(|item| &item.original).collect::<Vec<_>>(),
            [&removed.original, &pending.original]
        );
        assert_eq!(
            open.iter().map(|item| &item.original).collect::<Vec<_>>(),
            [&keep.original, &wanted.original]
        );
    }

    #[test]
    #[ignore = "helper launched from a disposable copy of the test executable"]
    fn process_fixture() {
        use windows::{
            Win32::UI::WindowsAndMessaging::{
                CreateWindowExW, DispatchMessageW, IsWindow, MSG, PM_REMOVE, PeekMessageW,
                WINDOW_EX_STYLE, WS_OVERLAPPED,
            },
            core::w,
        };

        let current_exe = std::env::current_exe().unwrap();
        if !current_exe
            .file_name()
            .unwrap()
            .to_string_lossy()
            .starts_with("aprogram-fixture-")
            || !Path::new("fixture-expected").is_file()
        {
            return;
        }
        let window = unsafe {
            CreateWindowExW(
                WINDOW_EX_STYLE::default(),
                w!("STATIC"),
                w!("AProgram test fixture"),
                WS_OVERLAPPED,
                0,
                0,
                1,
                1,
                None,
                None,
                None,
                None,
            )
        }
        .unwrap();
        fs::write("fixture-ready", b"").unwrap();

        let refuse_close = Path::new("fixture-refuse-close").is_file();
        let deadline = Instant::now() + Duration::from_secs(20);
        let mut message = MSG::default();
        while Instant::now() < deadline && unsafe { IsWindow(Some(window)).as_bool() } {
            while unsafe { PeekMessageW(&mut message, None, 0, 0, PM_REMOVE).as_bool() } {
                if message.message != WM_CLOSE || !refuse_close {
                    unsafe { DispatchMessageW(&message) };
                }
            }
            thread::sleep(Duration::from_millis(10));
        }
    }

    #[test]
    fn switching_away_closes_the_applied_image_after_shortcut_is_retargeted() {
        use crate::state::AppEntry;
        use windows::core::w;

        fn wait_until_ready(dir: &Path) {
            let deadline = Instant::now() + Duration::from_secs(5);
            while !dir.join("fixture-ready").is_file() {
                assert!(
                    Instant::now() < deadline,
                    "fixture did not start in {}",
                    dir.display()
                );
                thread::sleep(Duration::from_millis(10));
            }
        }

        let directory = tempfile::tempdir().unwrap();
        let parent = directory.path();
        let name = format!(
            "aprogram-fixture-{}.exe",
            parent.file_name().unwrap().to_string_lossy()
        );
        let first_dir = parent.join("first");
        let second_dir = parent.join("second");
        let work_dir = parent.join("link-working-directory");
        let other_work_dir = parent.join("second-instance");
        for dir in [&first_dir, &second_dir, &work_dir, &other_work_dir] {
            fs::create_dir(dir).unwrap();
            fs::write(dir.join("fixture-expected"), b"").unwrap();
        }
        let exe = std::env::current_exe().unwrap();
        let first = first_dir.join(&name);
        let second = second_dir.join(&name);
        fs::copy(&exe, &first).unwrap();
        fs::copy(&exe, &second).unwrap();
        let shortcut = parent.join("First.lnk");
        let save_shortcut = |target: &Path| {
            let _apartment = Apartment::initialize().unwrap();
            let link: IShellLinkW =
                unsafe { CoCreateInstance(&ShellLink, None, CLSCTX_INPROC_SERVER).unwrap() };
            let persistence: IPersistFile = link.cast().unwrap();
            unsafe {
                link.SetPath(PCWSTR(wide_string(target).unwrap().as_ptr()))
                    .unwrap();
                link.SetArguments(w!("--ignored --exact process::tests::process_fixture"))
                    .unwrap();
                link.SetWorkingDirectory(PCWSTR(wide_string(&work_dir).unwrap().as_ptr()))
                    .unwrap();
                persistence
                    .Save(PCWSTR(wide_string(&shortcut).unwrap().as_ptr()), true)
                    .unwrap();
            }
        };
        save_shortcut(&first);

        let first_group = || Group {
            name: "fixture".to_owned(),
            apps: vec![AppEntry {
                path: shortcut.clone(),
                enabled: true,
            }],
        };
        let opened = run(Command::Switch {
            group: first_group(),
            previous: None,
        });
        assert!(opened.failures.is_empty(), "{:?}", opened.failures);
        assert!(opened.first_request_after.is_some());
        wait_until_ready(&work_dir);

        let start_stubborn_fixture = |working_dir: &Path| {
            fs::write(working_dir.join("fixture-refuse-close"), b"").unwrap();
            let child = std::process::Command::new(&second)
                .args(["--ignored", "--exact", "process::tests::process_fixture"])
                .current_dir(working_dir)
                .spawn()
                .unwrap();
            wait_until_ready(working_dir);
            child
        };
        let mut second_child = start_stubborn_fixture(&second_dir);
        let mut other_child = start_stubborn_fixture(&other_work_dir);

        let checked_paths = [first.clone(), second.clone(), shortcut.clone()];
        let running = running_paths(&checked_paths).unwrap();
        assert_eq!(running, HashSet::from(checked_paths.clone()));

        let already_running = run(Command::Launch(first_group()));
        assert!(
            already_running.failures.is_empty(),
            "{:?}",
            already_running.failures
        );
        assert!(already_running.first_request_after.is_none());

        let cancelled = run_with_cancel(Command::Close(first_group()), &AtomicBool::new(true));
        assert!(cancelled.first_request_after.is_none());
        assert_eq!(cancelled.failures, ["操作已取消"]);
        assert_eq!(running_paths(&checked_paths).unwrap(), running);

        save_shortcut(&second);
        let empty_group = || Group {
            name: "empty".to_owned(),
            apps: Vec::new(),
        };
        let legacy = run(Command::Switch {
            group: empty_group(),
            previous: Some(Applied {
                group: "legacy".to_owned(),
                enabled: vec![shortcut.clone()],
                failed_open: Vec::new(),
                failed_close: vec![shortcut.clone()],
            }),
        });
        assert!(legacy.first_request_after.is_none());
        assert_eq!(legacy.failures.len(), 1);
        assert!(legacy.applied.unwrap().failed_close.is_empty());

        let closed = run(Command::Switch {
            group: empty_group(),
            previous: opened.applied,
        });
        assert!(closed.failures.is_empty(), "{:?}", closed.failures);
        assert!(closed.forceable.is_empty());
        assert!(closed.first_request_after.is_some());
        assert_eq!(
            running_paths(&checked_paths).unwrap(),
            HashSet::from([second.clone(), shortcut.clone()])
        );
        assert!(second_child.try_wait().unwrap().is_none());

        let stubborn = run(Command::Switch {
            group: first_group(),
            previous: closed.applied,
        });
        assert!(stubborn.first_request_after.is_none());
        assert!(stubborn.failures.is_empty());
        let started = Instant::now();
        let refused = run(Command::Switch {
            group: empty_group(),
            previous: stubborn.applied,
        });
        assert!(
            started.elapsed() < Duration::from_secs(5),
            "each process waited separately"
        );
        assert_eq!(refused.failures.len(), 1);
        let second_image = fs::canonicalize(second).unwrap();
        assert_eq!(refused.forceable, std::slice::from_ref(&second_image));
        assert_eq!(refused.applied.unwrap().failed_close, [second_image]);
        assert!(second_child.try_wait().unwrap().is_none());
        assert!(other_child.try_wait().unwrap().is_none());

        let forced = run(Command::Force(refused.forceable));
        assert!(forced.failures.is_empty(), "{:?}", forced.failures);
        assert!(forced.first_request_after.is_some());
        assert!(!second_child.wait().unwrap().success());
        assert!(!other_child.wait().unwrap().success());
    }
}
