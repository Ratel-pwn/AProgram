"""文件处理工具"""
import os
from win32com.client import Dispatch


def resolve_lnk(path):
    """解析快捷方式文件，返回目标路径"""
    try:
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortcut(path)
        return shortcut.TargetPath
    except Exception:
        return path


def get_app_name(path):
    """获取应用名称"""
    if path.endswith('.lnk'):
        # .lnk用快捷方式名
        return os.path.splitext(os.path.basename(path))[0]
    else:
        # exe用文件名
        return os.path.basename(path)


def is_valid_app_file(path):
    """检查是否是有效的应用文件"""
    return os.path.isfile(path) and (path.endswith(".exe") or path.endswith(".lnk"))
