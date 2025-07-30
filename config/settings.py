"""设置管理模块"""
import os
import json
import sys
import winreg
from .constants import DEFAULT_SETTINGS, CONFIG_FILE, SETTINGS_FILE


def load_config():
    """加载软件组配置"""
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(data):
    """保存软件组配置"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_settings():
    """加载应用设置"""
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
            # 确保所有设置项都存在
            for key, default_value in DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = default_value
            return settings
    except Exception as e:
        print(f"[设置加载失败] {e}")
        return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    """保存应用设置"""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[设置保存失败] {e}")


def set_auto_start(enable):
    """设置开机自启"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        )

        app_path = sys.argv[0]
        if not app_path.endswith('.py'):
            # 如果是打包后的exe
            app_path = os.path.abspath(sys.argv[0])
        else:
            # 如果是python脚本，使用python解释器
            app_path = f'pythonw "{os.path.abspath(sys.argv[0])}"'

        if enable:
            winreg.SetValueEx(key, "SoftwareLauncher",
                              0, winreg.REG_SZ, app_path)
        else:
            try:
                winreg.DeleteValue(key, "SoftwareLauncher")
            except FileNotFoundError:
                pass  # 如果值不存在，忽略错误

        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"[开机自启设置失败] {e}")
        return False


def get_auto_start_status():
    """获取开机自启状态"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_QUERY_VALUE
        )

        try:
            winreg.QueryValueEx(key, "SoftwareLauncher")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception as e:
        print(f"[获取开机自启状态失败] {e}")
        return False
