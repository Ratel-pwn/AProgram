use std::{
    ffi::OsStr,
    os::windows::ffi::OsStrExt,
    path::{Path, PathBuf},
    sync::Arc,
    time::Duration,
};

use anyhow::{Result, ensure};
use gpui::{RenderImage, Window};
use raw_window_handle::{HasWindowHandle, RawWindowHandle};
use windows::{
    Win32::{
        Foundation::{HWND, LPARAM, WPARAM},
        Graphics::Gdi::{
            BI_RGB, BITMAPINFO, BITMAPINFOHEADER, CreateCompatibleDC, CreateDIBSection,
            DIB_RGB_COLORS, DeleteDC, DeleteObject, SelectObject,
        },
        System::{
            LibraryLoader::GetModuleHandleW,
            Registry::{
                HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ, RRF_RT_REG_SZ, RegCloseKey,
                RegDeleteValueW, RegGetValueW, RegOpenKeyExW, RegSetValueExW,
            },
        },
        UI::{
            Controls::EM_SETSEL,
            Input::KeyboardAndMouse::GetDoubleClickTime,
            Shell::{SHFILEINFOW, SHGFI_ICON, SHGFI_SMALLICON, SHGetFileInfoW},
            WindowsAndMessaging::*,
        },
    },
    core::{PCWSTR, w},
};

fn wide(text: impl AsRef<OsStr>) -> Vec<u16> {
    text.as_ref().encode_wide().chain(Some(0)).collect()
}

pub fn hwnd(window: &Window) -> Result<HWND> {
    let handle = HasWindowHandle::window_handle(window)
        .map_err(|error| anyhow::anyhow!("读取窗口句柄失败：{error}"))?;
    match handle.as_raw() {
        RawWindowHandle::Win32(handle) => Ok(HWND(handle.hwnd.get() as _)),
        _ => anyhow::bail!("无法获取 Windows 窗口句柄"),
    }
}

pub fn show(hwnd: HWND) {
    unsafe {
        let command = if IsIconic(hwnd).as_bool() {
            SW_RESTORE
        } else {
            SW_SHOW
        };
        let _ = ShowWindowAsync(hwnd, command);
        let _ = SetForegroundWindow(hwnd);
    }
}

pub fn hide(hwnd: HWND) {
    unsafe {
        let _ = ShowWindowAsync(hwnd, SW_HIDE);
    }
}

pub fn visible(hwnd: HWND) -> bool {
    unsafe { IsWindowVisible(hwnd).as_bool() && !IsIconic(hwnd).as_bool() }
}

pub fn double_click_time() -> Duration {
    Duration::from_millis(u64::from(unsafe { GetDoubleClickTime() }))
}

pub fn show_error(message: &str) {
    let message = wide(message);
    unsafe {
        let _ = MessageBoxW(None, PCWSTR(message.as_ptr()), w!("AProgram"), MB_ICONERROR);
    }
}

pub fn set_auto_start(enabled: bool) -> Result<()> {
    let command = auto_start_command()?;
    let mut key = Default::default();
    unsafe {
        RegOpenKeyExW(
            HKEY_CURRENT_USER,
            w!("Software\\Microsoft\\Windows\\CurrentVersion\\Run"),
            Some(0),
            KEY_SET_VALUE,
            &mut key,
        )
        .ok()?;
        let result = if enabled {
            let bytes = std::slice::from_raw_parts(command.as_ptr().cast(), command.len() * 2);
            RegSetValueExW(key, w!("AProgram"), Some(0), REG_SZ, Some(bytes)).ok()
        } else {
            let status = RegDeleteValueW(key, w!("AProgram"));
            if status.0 == 2 { Ok(()) } else { status.ok() }
        };
        let _ = RegCloseKey(key);
        result?;
    }
    Ok(())
}

fn auto_start_command() -> Result<Vec<u16>> {
    let mut command = Vec::new();
    command.push(u16::from(b'"'));
    command.extend(std::env::current_exe()?.as_os_str().encode_wide());
    command.extend(wide("\" --tray"));
    Ok(command)
}

pub fn auto_start_enabled() -> bool {
    let Ok(command) = auto_start_command() else {
        return false;
    };
    let mut value = vec![0u16; command.len()];
    let mut bytes = (value.len() * size_of::<u16>()) as u32;
    let status = unsafe {
        RegGetValueW(
            HKEY_CURRENT_USER,
            w!("Software\\Microsoft\\Windows\\CurrentVersion\\Run"),
            w!("AProgram"),
            RRF_RT_REG_SZ,
            None,
            Some(value.as_mut_ptr().cast()),
            Some(&mut bytes),
        )
    };
    status.is_ok() && value == command
}

struct GroupDialog {
    title: Vec<u16>,
    initial: Vec<u16>,
    result: Option<String>,
}

const EDIT_ID: i32 = 100;

pub fn group_name(owner: isize, title: &str, initial: &str) -> Result<Option<String>> {
    let mut dialog = GroupDialog {
        title: wide(title),
        initial: wide(initial),
        result: None,
    };
    let template = group_dialog_template();
    let result = unsafe {
        DialogBoxIndirectParamW(
            Some(GetModuleHandleW(None)?.into()),
            template.as_ptr().cast(),
            Some(HWND(owner as _)),
            Some(group_dialog_proc),
            LPARAM((&mut dialog as *mut GroupDialog) as isize),
        )
    };
    ensure!(result != -1, "无法打开组名对话框");
    Ok(dialog.result)
}

fn group_dialog_template() -> Vec<u32> {
    // The standard Win32 dialog template stores text as UTF-16 and aligns each control to a DWORD.
    let mut words = Vec::new();
    let push_style = |words: &mut Vec<u16>, style: u32| {
        words.extend([style as u16, (style >> 16) as u16, 0, 0]);
    };
    push_style(
        &mut words,
        (WS_POPUP | WS_CAPTION | WS_SYSMENU).0
            | DS_MODALFRAME as u32
            | DS_CENTER as u32
            | DS_SETFONT as u32,
    );
    words.extend([3, 0, 0, 206, 57, 0, 0, 0, 9]);
    words.extend(wide("Microsoft YaHei UI"));
    let mut control = |style: u32, [x, y, width, height]: [u16; 4], id: i32, class, text| {
        if words.len() % 2 != 0 {
            words.push(0);
        }
        push_style(&mut words, (WS_CHILD | WS_VISIBLE | WS_TABSTOP).0 | style);
        words.extend([x, y, width, height, id as u16, 0xffff, class]);
        words.extend(wide(text));
        words.push(0);
    };
    control(
        WS_BORDER.0 | ES_AUTOHSCROLL as u32,
        [8, 9, 190, 15],
        EDIT_ID,
        0x81,
        "",
    );
    control(
        BS_DEFPUSHBUTTON as u32,
        [88, 33, 52, 15],
        IDOK.0,
        0x80,
        "确定",
    );
    control(
        BS_PUSHBUTTON as u32,
        [146, 33, 52, 15],
        IDCANCEL.0,
        0x80,
        "取消",
    );
    words
        .chunks(2)
        .map(|pair| u32::from(pair[0]) | (u32::from(*pair.get(1).unwrap_or(&0)) << 16))
        .collect()
}

unsafe extern "system" fn group_dialog_proc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> isize {
    unsafe {
        match msg {
            WM_INITDIALOG => {
                let dialog = &*(lparam.0 as *const GroupDialog);
                SetWindowLongPtrW(hwnd, GWLP_USERDATA, lparam.0);
                let _ = SetWindowTextW(hwnd, PCWSTR(dialog.title.as_ptr()));
                let _ = SetDlgItemTextW(hwnd, EDIT_ID, PCWSTR(dialog.initial.as_ptr()));
                let _ = SendDlgItemMessageW(hwnd, EDIT_ID, EM_SETSEL, WPARAM(0), LPARAM(-1));
                1
            }
            WM_COMMAND if wparam.0 as u16 == IDOK.0 as u16 => {
                let dialog = &mut *(GetWindowLongPtrW(hwnd, GWLP_USERDATA) as *mut GroupDialog);
                let mut text = [0; 256];
                let len = GetDlgItemTextW(hwnd, EDIT_ID, &mut text) as usize;
                dialog.result = Some(String::from_utf16_lossy(&text[..len]));
                let _ = EndDialog(hwnd, 1);
                1
            }
            WM_CLOSE | WM_COMMAND if msg == WM_CLOSE || wparam.0 as u16 == IDCANCEL.0 as u16 => {
                let _ = EndDialog(hwnd, 0);
                1
            }
            _ => 0,
        }
    }
}

pub fn app_icons(paths: Vec<PathBuf>) -> Vec<(PathBuf, Option<Arc<RenderImage>>)> {
    if paths.is_empty() {
        return Vec::new();
    }
    crate::process::in_sta(|| {
        Ok(paths
            .into_iter()
            .map(|path| {
                let icon = app_icon(&path);
                (path, icon)
            })
            .collect())
    })
    .unwrap_or_default()
}

fn app_icon(path: &Path) -> Option<Arc<RenderImage>> {
    let path = wide(path.as_os_str());
    unsafe {
        let mut info = SHFILEINFOW::default();
        if SHGetFileInfoW(
            PCWSTR(path.as_ptr()),
            Default::default(),
            Some(&mut info),
            size_of::<SHFILEINFOW>() as u32,
            SHGFI_ICON | SHGFI_SMALLICON,
        ) == 0
            || info.hIcon.is_invalid()
        {
            return None;
        }
        let icon = info.hIcon;
        let image = render_icon(icon);
        let _ = DestroyIcon(icon);
        image
    }
}

unsafe fn render_icon(icon: HICON) -> Option<Arc<RenderImage>> {
    const SIZE: i32 = 24;
    let info = BITMAPINFO {
        bmiHeader: BITMAPINFOHEADER {
            biSize: size_of::<BITMAPINFOHEADER>() as u32,
            biWidth: SIZE,
            biHeight: -SIZE,
            biPlanes: 1,
            biBitCount: 32,
            biCompression: BI_RGB.0,
            ..Default::default()
        },
        ..Default::default()
    };
    let mut bits = std::ptr::null_mut();
    unsafe {
        let dc = CreateCompatibleDC(None);
        if dc.is_invalid() {
            return None;
        }
        let result = CreateDIBSection(Some(dc), &info, DIB_RGB_COLORS, &mut bits, None, 0)
            .ok()
            .and_then(|bitmap| {
                let previous = SelectObject(dc, bitmap.into());
                let pixels =
                    std::slice::from_raw_parts_mut(bits.cast::<u8>(), (SIZE * SIZE * 4) as usize);
                pixels.fill(0);
                let image = DrawIconEx(dc, 0, 0, icon, SIZE, SIZE, 0, None, DI_NORMAL)
                    .ok()
                    .and_then(|()| {
                        image::RgbaImage::from_raw(SIZE as u32, SIZE as u32, pixels.to_vec())
                    });
                SelectObject(dc, previous);
                let _ = DeleteObject(bitmap.into());
                image.map(|image| Arc::new(RenderImage::new([image::Frame::new(image)])))
            });
        let _ = DeleteDC(dc);
        result
    }
}
