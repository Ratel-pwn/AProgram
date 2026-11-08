use std::cell::{Cell, RefCell};
use std::rc::Rc;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use windows::Win32::Foundation::{
    CloseHandle, ERROR_ALREADY_EXISTS, GetLastError, HANDLE, HINSTANCE, HWND, LPARAM, LRESULT,
    WPARAM,
};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::Threading::{CreateMutexW, ReleaseMutex};
use windows::Win32::UI::Shell::{
    NIF_ICON, NIF_INFO, NIF_MESSAGE, NIF_SHOWTIP, NIF_TIP, NIIF_INFO, NIM_ADD, NIM_DELETE,
    NIM_MODIFY, NIM_SETFOCUS, NIM_SETVERSION, NIN_SELECT, NINF_KEY, NOTIFYICON_VERSION_4,
    NOTIFYICONDATAW, Shell_NotifyIconW,
};
use windows::Win32::UI::WindowsAndMessaging::{
    AllowSetForegroundWindow, AppendMenuW, CREATESTRUCTW, CreatePopupMenu, CreateWindowExW,
    DefWindowProcW, DestroyMenu, DestroyWindow, FindWindowW, GWLP_USERDATA, GetSystemMetrics,
    GetWindowLongPtrW, GetWindowThreadProcessId, HICON, HMENU, IDI_APPLICATION, KillTimer,
    LoadIconW, MF_CHECKED, MF_GRAYED, MF_SEPARATOR, MF_STRING, PostMessageW, RegisterClassW,
    RegisterWindowMessageW, SM_MENUDROPALIGNMENT, SetForegroundWindow, SetMenuDefaultItem,
    SetTimer, SetWindowLongPtrW, TPM_LEFTALIGN, TPM_RETURNCMD, TPM_RIGHTALIGN, TPM_RIGHTBUTTON,
    TrackPopupMenu, UnregisterClassW, WM_APP, WM_CLOSE, WM_CONTEXTMENU, WM_NCCREATE, WM_NULL,
    WM_TIMER, WNDCLASSW, WS_EX_TOOLWINDOW, WS_POPUP,
};
use windows::core::{Error, PCWSTR, w};

const TRAY_CLASS: PCWSTR = w!("AProgram.Tray.9DBC6E0E");
const INSTANCE_MUTEX: PCWSTR = w!("Local\\AProgram.Instance.9DBC6E0E");
const TRAY_CALLBACK: u32 = WM_APP + 1;
const SHOW_EXISTING: u32 = WM_APP + 2;
const ICON_ID: u32 = 1;
const ICON_RETRY_TIMER: usize = 1;
const ICON_RETRY_MS: u32 = 2000;
const NIN_KEYSELECT: u32 = NIN_SELECT | NINF_KEY;
const SHOW_COMMAND: u32 = 1;
const QUIT_COMMAND: u32 = 2;
const FIRST_GROUP_COMMAND: u32 = 3;

#[derive(Debug, PartialEq, Eq)]
pub enum Event {
    Show,
    Switch(String),
    Quit,
}

pub struct Instance(HANDLE);

impl Drop for Instance {
    fn drop(&mut self) {
        unsafe {
            let _ = ReleaseMutex(self.0);
            let _ = CloseHandle(self.0);
        }
    }
}

pub fn acquire_instance() -> Result<Option<Instance>> {
    let mutex = unsafe { CreateMutexW(None, true, INSTANCE_MUTEX) };
    let already_exists = unsafe { GetLastError() } == ERROR_ALREADY_EXISTS;
    let mutex = mutex.context("创建 AProgram 单实例互斥锁失败")?;
    if !already_exists {
        return Ok(Some(Instance(mutex)));
    }
    unsafe { CloseHandle(mutex) }.context("关闭 AProgram 单实例互斥锁句柄失败")?;

    // The first process may have acquired the mutex before creating its tray window.
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        if let Ok(hwnd) = unsafe { FindWindowW(TRAY_CLASS, None) } {
            let mut process_id = 0;
            unsafe {
                GetWindowThreadProcessId(hwnd, Some(&mut process_id));
                if process_id != 0 {
                    let _ = AllowSetForegroundWindow(process_id);
                }
                if PostMessageW(Some(hwnd), SHOW_EXISTING, WPARAM(0), LPARAM(0)).is_ok() {
                    break;
                }
            }
        }
        if Instant::now() >= deadline {
            break;
        }
        thread::sleep(Duration::from_millis(50));
    }
    Ok(None)
}

pub struct Tray {
    hwnd: HWND,
    module: HINSTANCE,
    state: Rc<State>,
}

impl Tray {
    /// Create on the UI thread. The callback should enqueue events for the application.
    pub fn new(send: impl Fn(Event) + 'static) -> Result<Self> {
        let module = HINSTANCE(unsafe { GetModuleHandleW(None) }?.0);
        let taskbar_created = unsafe { RegisterWindowMessageW(w!("TaskbarCreated")) };
        if taskbar_created == 0 {
            return Err(Error::from_win32()).context("注册 Windows 任务栏消息失败");
        }
        let state = Rc::new(State {
            send: Box::new(send),
            taskbar_created,
            icon: unsafe { LoadIconW(None, IDI_APPLICATION) }.context("加载托盘图标失败")?,
            menu: RefCell::default(),
            menu_open: Cell::new(false),
        });
        let class = WNDCLASSW {
            hInstance: module,
            lpfnWndProc: Some(window_proc),
            lpszClassName: TRAY_CLASS,
            ..Default::default()
        };
        if unsafe { RegisterClassW(&class) } == 0 {
            return Err(Error::from_win32()).context("注册 AProgram 托盘窗口类失败");
        }

        // A hidden top-level window receives TaskbarCreated broadcasts.
        let hwnd = unsafe {
            CreateWindowExW(
                WS_EX_TOOLWINDOW,
                TRAY_CLASS,
                None,
                WS_POPUP,
                0,
                0,
                0,
                0,
                None,
                None,
                Some(module),
                Some(Rc::as_ptr(&state).cast()),
            )
        };
        let hwnd = match hwnd {
            Ok(hwnd) => hwnd,
            Err(error) => {
                let _ = unsafe { UnregisterClassW(TRAY_CLASS, Some(module)) };
                return Err(error).context("创建 AProgram 托盘窗口失败");
            }
        };
        state.register_icon(hwnd);
        Ok(Self {
            hwnd,
            module,
            state,
        })
    }

    pub fn update(&self, names: Vec<String>, active: Option<String>, busy: bool) {
        self.state.menu.replace(MenuState {
            names,
            active,
            busy,
        });
    }

    pub fn notify(&self, title: &str, message: &str) {
        let mut icon = icon_data(self.hwnd);
        icon.uFlags = NIF_INFO;
        icon.dwInfoFlags = NIIF_INFO;
        write_text(&mut icon.szInfoTitle, title);
        write_text(&mut icon.szInfo, message);
        let _ = unsafe { Shell_NotifyIconW(NIM_MODIFY, &icon) };
    }
}

impl Drop for Tray {
    fn drop(&mut self) {
        unsafe {
            SetWindowLongPtrW(self.hwnd, GWLP_USERDATA, 0);
            let _ = KillTimer(Some(self.hwnd), ICON_RETRY_TIMER);
            let _ = Shell_NotifyIconW(NIM_DELETE, &icon_data(self.hwnd));
            let _ = DestroyWindow(self.hwnd);
            let _ = UnregisterClassW(TRAY_CLASS, Some(self.module));
        }
    }
}

struct State {
    send: Box<dyn Fn(Event)>,
    taskbar_created: u32,
    icon: HICON,
    menu: RefCell<MenuState>,
    menu_open: Cell<bool>,
}

impl State {
    fn register_icon(&self, hwnd: HWND) {
        let mut icon = icon_data(hwnd);
        icon.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP;
        icon.uCallbackMessage = TRAY_CALLBACK;
        icon.hIcon = self.icon;
        write_text(&mut icon.szTip, "AProgram");
        icon.Anonymous.uVersion = NOTIFYICON_VERSION_4;
        unsafe {
            let added = Shell_NotifyIconW(NIM_ADD, &icon).as_bool()
                || Shell_NotifyIconW(NIM_MODIFY, &icon).as_bool();
            if added && Shell_NotifyIconW(NIM_SETVERSION, &icon).as_bool() {
                let _ = KillTimer(Some(hwnd), ICON_RETRY_TIMER);
            } else {
                // Explorer may still be starting during sign-in.
                SetTimer(Some(hwnd), ICON_RETRY_TIMER, ICON_RETRY_MS, None);
            }
        }
    }

    fn show_menu(&self, hwnd: HWND, position: WPARAM) {
        if self.menu_open.get() {
            return;
        }
        let displayed = self.menu.borrow().clone();
        let Ok(menu) = build_menu(&displayed) else {
            return;
        };

        let x = (position.0 as i16) as i32;
        let y = ((position.0 >> 16) as i16) as i32;
        self.menu_open.set(true);
        let command = unsafe {
            let alignment = if GetSystemMetrics(SM_MENUDROPALIGNMENT) == 0 {
                TPM_LEFTALIGN
            } else {
                TPM_RIGHTALIGN
            };
            let _ = SetForegroundWindow(hwnd);
            let command = TrackPopupMenu(
                menu.0,
                TPM_RETURNCMD | TPM_RIGHTBUTTON | alignment,
                x,
                y,
                None,
                hwnd,
                None,
            );
            let _ = PostMessageW(Some(hwnd), WM_NULL, WPARAM(0), LPARAM(0));
            command.0 as u32
        };
        self.menu_open.set(false);

        let event = match command {
            0 => {
                let _ = unsafe { Shell_NotifyIconW(NIM_SETFOCUS, &icon_data(hwnd)) };
                None
            }
            SHOW_COMMAND => Some(Event::Show),
            QUIT_COMMAND => Some(Event::Quit),
            _ => {
                let current = self.menu.borrow();
                displayed
                    .names
                    .get((command - FIRST_GROUP_COMMAND) as usize)
                    .filter(|name| !current.busy && current.names.contains(name))
                    .map(|name| Event::Switch(name.clone()))
            }
        };
        if let Some(event) = event {
            (self.send)(event);
        }
    }
}

#[derive(Clone, Default)]
struct MenuState {
    names: Vec<String>,
    active: Option<String>,
    busy: bool,
}

struct Menu(HMENU);

impl Drop for Menu {
    fn drop(&mut self) {
        let _ = unsafe { DestroyMenu(self.0) };
    }
}

fn build_menu(state: &MenuState) -> windows::core::Result<Menu> {
    unsafe {
        let menu = Menu(CreatePopupMenu()?);
        AppendMenuW(
            menu.0,
            MF_STRING,
            SHOW_COMMAND as usize,
            w!("打开 AProgram"),
        )?;
        SetMenuDefaultItem(menu.0, SHOW_COMMAND, 0)?;
        if state.busy || !state.names.is_empty() {
            AppendMenuW(menu.0, MF_SEPARATOR, 0, None)?;
            if state.busy {
                AppendMenuW(menu.0, MF_STRING | MF_GRAYED, 0, w!("正在处理…"))?;
            }
            for (index, name) in state.names.iter().enumerate() {
                let mut flags = MF_STRING;
                if state.active.as_ref() == Some(name) {
                    flags |= MF_CHECKED;
                }
                if state.busy {
                    flags |= MF_GRAYED;
                }
                let label: Vec<u16> = name
                    .replace('&', "&&")
                    .replace('\0', "\u{fffd}")
                    .encode_utf16()
                    .chain(std::iter::once(0))
                    .collect();
                AppendMenuW(
                    menu.0,
                    flags,
                    FIRST_GROUP_COMMAND as usize + index,
                    PCWSTR(label.as_ptr()),
                )?;
            }
        }
        AppendMenuW(menu.0, MF_SEPARATOR, 0, None)?;
        AppendMenuW(menu.0, MF_STRING, QUIT_COMMAND as usize, w!("退出"))?;
        Ok(menu)
    }
}

fn icon_data(hwnd: HWND) -> NOTIFYICONDATAW {
    NOTIFYICONDATAW {
        cbSize: std::mem::size_of::<NOTIFYICONDATAW>() as u32,
        hWnd: hwnd,
        uID: ICON_ID,
        ..Default::default()
    }
}

fn write_text(buffer: &mut [u16], value: &str) {
    let limit = buffer.len() - 1;
    for (slot, unit) in buffer[..limit].iter_mut().zip(value.encode_utf16()) {
        *slot = if unit == 0 { 0xfffd } else { unit };
    }
    if (0xd800..=0xdbff).contains(&buffer[limit - 1]) {
        buffer[limit - 1] = 0;
    }
}

extern "system" fn window_proc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if msg == WM_NCCREATE {
        let creation = unsafe { &*(lparam.0 as *const CREATESTRUCTW) };
        unsafe { SetWindowLongPtrW(hwnd, GWLP_USERDATA, creation.lpCreateParams as isize) };
        return LRESULT(1);
    }

    let state = unsafe { GetWindowLongPtrW(hwnd, GWLP_USERDATA) } as *const State;
    if state.is_null() {
        return unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) };
    }
    // Tray owns this pointer until its Drop clears the window data. A local
    // strong reference also keeps it alive during the popup's nested message loop.
    let state = unsafe {
        Rc::increment_strong_count(state);
        Rc::from_raw(state)
    };
    match msg {
        TRAY_CALLBACK if ((lparam.0 as u32) >> 16) == ICON_ID => match lparam.0 as u32 & 0xffff {
            NIN_SELECT | NIN_KEYSELECT => (state.send)(Event::Show),
            WM_CONTEXTMENU => state.show_menu(hwnd, wparam),
            _ => {}
        },
        SHOW_EXISTING => (state.send)(Event::Show),
        WM_CLOSE => {}
        WM_TIMER if wparam.0 == ICON_RETRY_TIMER => state.register_icon(hwnd),
        msg if msg == state.taskbar_created => state.register_icon(hwnd),
        _ => return unsafe { DefWindowProcW(hwnd, msg, wparam, lparam) },
    }
    LRESULT(0)
}
