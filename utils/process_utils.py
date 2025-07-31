"""进程管理工具"""
import os
import time
import psutil
from .file_utils import resolve_lnk


def close_application_by_path(app_path):
    """根据应用路径关闭对应的进程"""
    try:
        # 处理快捷方式
        if app_path.endswith('.lnk'):
            target_path = resolve_lnk(app_path)
            if target_path and os.path.exists(target_path):
                app_path = target_path

        # 获取应用的可执行文件名
        app_name = os.path.basename(app_path).lower()

        closed_processes = []

        # 遍历所有进程
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                proc_info = proc.info

                # 检查进程名是否匹配
                if proc_info['name'] and proc_info['name'].lower() == app_name:
                    proc.terminate()  # 先尝试优雅关闭
                    closed_processes.append(proc_info['name'])
                    continue

                # 检查完整路径是否匹配
                if proc_info['exe'] and os.path.normpath(proc_info['exe'].lower()) == os.path.normpath(app_path.lower()):
                    proc.terminate()  # 先尝试优雅关闭
                    closed_processes.append(proc_info['name'])
                    continue

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # 等待一下，然后强制关闭还在运行的进程
        if closed_processes:
            time.sleep(1)

            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    proc_info = proc.info

                    # 检查是否还有相关进程在运行
                    if (proc_info['name'] and proc_info['name'].lower() == app_name) or \
                       (proc_info['exe'] and os.path.normpath(proc_info['exe'].lower()) == os.path.normpath(app_path.lower())):
                        proc.kill()  # 强制关闭

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

        if closed_processes:
            print(f"[关闭成功] {app_path} -> {', '.join(set(closed_processes))}")
            return True
        else:
            print(f"[未找到进程] {app_path}")
            return False

    except Exception as e:
        print(f"[关闭失败] {app_path}: {str(e)}")
        return False


def launch_application(path):
    """启动应用程序"""
    try:
        import subprocess
        subprocess.Popen(path, shell=True)
        return True
    except Exception as e:
        print(f"[启动失败] {path}: {str(e)}")
        return False


def is_application_running(app_path):
    """检测应用程序是否正在运行"""
    try:
        # 处理快捷方式
        if app_path.endswith('.lnk'):
            target_path = resolve_lnk(app_path)
            if target_path and os.path.exists(target_path):
                app_path = target_path

        # 获取应用的可执行文件名
        app_name = os.path.basename(app_path).lower()

        # 遍历所有进程
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                proc_info = proc.info

                # 检查进程名是否匹配
                if proc_info['name'] and proc_info['name'].lower() == app_name:
                    return True

                # 检查完整路径是否匹配
                if proc_info['exe'] and os.path.normpath(proc_info['exe'].lower()) == os.path.normpath(app_path.lower()):
                    return True

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        return False

    except Exception as e:
        print(f"[状态检测失败] {app_path}: {str(e)}")
        return False
