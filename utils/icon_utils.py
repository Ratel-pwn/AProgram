"""图标处理工具"""
import os
import tempfile
import pythoncom
from win32com.client import Dispatch
import win32gui
import win32ui
import win32con
import win32api
from PIL import Image
from PyQt5.QtGui import QIcon


def get_icon_from_lnk(path):
    """从快捷方式获取图标路径"""
    try:
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortcut(path)
        icon_path = shortcut.IconLocation.split(',')[0]
        if os.path.exists(icon_path):
            return icon_path
    except Exception as e:
        print(f"[图标提取失败] {e}")
    return None


def extract_icon_from_exe(path):
    """从EXE文件提取图标，使用win32ui的方法"""
    try:
        # 提取图标句柄
        large, _ = win32gui.ExtractIconEx(path, 0)
        if not large:
            print(f"[extract_icon_from_exe] 未提取到图标: {path}")
            # 尝试QIcon直接加载作为备选
            icon = QIcon(path)
            if not icon.isNull():
                print(f"[extract_icon_from_exe] QIcon直接加载exe成功: {path}")
                return icon
            else:
                print(f"[extract_icon_from_exe] QIcon直接加载exe失败: {path}")
            return QIcon()

        hicon = large[0]
        ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)

        # 创建设备上下文
        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hdc_mem = hdc.CreateCompatibleDC()

        # 创建位图
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(hdc, ico_x, ico_x)
        hdc_mem.SelectObject(bmp)

        # 绘制图标到位图
        win32gui.DrawIconEx(hdc_mem.GetHandleOutput(), 0, 0,
                            hicon, ico_x, ico_x, 0, 0, win32con.DI_NORMAL)

        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.bmp', delete=False) as temp_bmp:
            bmp_path = temp_bmp.name

        with tempfile.NamedTemporaryFile(suffix='.ico', delete=False) as temp_ico:
            ico_path = temp_ico.name

        try:
            # 保存为BMP并转换为ICO
            bmp.SaveBitmapFile(hdc_mem, bmp_path)
            img = Image.open(bmp_path)
            img.save(ico_path, format='ICO')

            # 创建QIcon
            icon = QIcon(ico_path)

            # 清理临时文件
            os.remove(bmp_path)
            os.remove(ico_path)

            # 销毁图标句柄
            win32gui.DestroyIcon(hicon)

            print(
                f"[extract_icon_from_exe] 成功提取图标: {path}, isNull={icon.isNull()}, pixmap.isNull={icon.pixmap(32, 32).isNull()}")
            return icon

        except Exception as e:
            # 清理临时文件
            try:
                os.remove(bmp_path)
            except:
                pass
            try:
                os.remove(ico_path)
            except:
                pass
            raise e

    except Exception as e:
        print(f"[extract_icon_from_exe] 提取失败: {e}, 路径: {path}")
        # 尝试QIcon直接加载作为备选
        icon = QIcon(path)
        if not icon.isNull():
            print(f"[extract_icon_from_exe] QIcon直接加载exe成功: {path}")
            return icon
        else:
            print(f"[extract_icon_from_exe] QIcon直接加载exe失败: {path}")
        return QIcon()


def get_app_icon(path):
    """获取应用图标"""
    from config.constants import APP_ICON_PATH

    icon = QIcon()
    default_icon = QIcon(APP_ICON_PATH) if os.path.exists(
        APP_ICON_PATH) else QIcon()

    if path.endswith(".lnk"):
        from .file_utils import resolve_lnk
        resolved_path = resolve_lnk(path)
        icon_path = get_icon_from_lnk(path)
        if icon_path and os.path.exists(icon_path):
            if icon_path.lower().endswith('.ico'):
                icon = QIcon(icon_path)
                print(
                    f"[图标] 使用.lnk的IconLocation(ico): {icon_path}, isNull={icon.isNull()}, pixmap.isNull={icon.pixmap(32, 32).isNull()}")
            else:
                icon = extract_icon_from_exe(icon_path)
                print(
                    f"[图标] 使用.lnk的IconLocation(exe/dll): {icon_path}, isNull={icon.isNull()}, pixmap.isNull={icon.pixmap(32, 32).isNull()}")
        elif resolved_path and os.path.exists(resolved_path) and resolved_path.lower().endswith('.exe'):
            icon = extract_icon_from_exe(resolved_path)
            print(
                f"[图标] 使用.lnk目标exe: {resolved_path}, isNull={icon.isNull()}, pixmap.isNull={icon.pixmap(32, 32).isNull()}")
        else:
            print(
                f"[图标] .lnk无有效图标，路径: {path}，目标: {resolved_path}，IconLocation: {icon_path}")
    elif os.path.exists(path):
        icon = extract_icon_from_exe(path)

    if icon.isNull() or icon.pixmap(32, 32).isNull():
        print(
            f"[图标] icon无效，尝试QIcon({path})兜底: isNull={icon.isNull()}, pixmap.isNull={icon.pixmap(32, 32).isNull()}")
        fallback_icon = QIcon(path)
        if not fallback_icon.isNull() and not fallback_icon.pixmap(32, 32).isNull():
            icon = QIcon(path)
            print(f"[图标] QIcon({path})兜底成功")
        else:
            print(f"[图标] QIcon({path})兜底失败，使用默认图标{APP_ICON_PATH}")
            icon = QIcon(APP_ICON_PATH) if os.path.exists(
                APP_ICON_PATH) else QIcon()

    return icon
