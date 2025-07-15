import sys
import os
import json
import subprocess
import winreg
from PyQt5.QtWidgets import (
    QApplication, QWidget, QListWidget, QPushButton, QVBoxLayout,
    QHBoxLayout, QListWidgetItem, QFileDialog, QInputDialog, QMessageBox, QLabel,
    QMenu, QAction, QSystemTrayIcon, QCheckBox, QDialog, QFormLayout, QFrame
)
from PyQt5.QtGui import QPixmap, QImage, QIcon, QFont
from PyQt5.QtCore import Qt, QSize

# 👇 添加快捷方式解析依赖
import pythoncom
from win32com.client import Dispatch
import win32gui
import win32con
import win32api
import ctypes
import ctypes.wintypes as wintypes

CONFIG_FILE = "software_groups.json"
SETTINGS_FILE = "settings.json"

# 默认设置
DEFAULT_SETTINGS = {
    "auto_start": False,
    "minimize_to_tray": True
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_settings():
    """加载设置"""
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
    """保存设置"""
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


def get_icon_from_lnk(path):
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
    try:
        large, _ = win32gui.ExtractIconEx(path, 0)
        if not large:
            print(f"[extract_icon_from_exe] 未提取到图标: {path}")
            icon = QIcon(path)
            if not icon.isNull():
                print(f"[extract_icon_from_exe] QIcon直接加载exe成功: {path}")
                return icon
            else:
                print(f"[extract_icon_from_exe] QIcon直接加载exe失败: {path}")
            return QIcon()
        hicon = large[0]
        hdc = win32gui.CreateCompatibleDC(0)
        size = win32api.GetSystemMetrics(win32con.SM_CXICON)
        hbitmap = win32gui.CreateCompatibleBitmap(hdc, size, size)
        win32gui.SelectObject(hdc, hbitmap)
        win32gui.DrawIconEx(hdc, 0, 0, hicon, size, size,
                            0, 0, win32con.DI_NORMAL)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', ctypes.c_uint32),
                ('biWidth', ctypes.c_int32),
                ('biHeight', ctypes.c_int32),
                ('biPlanes', ctypes.c_uint16),
                ('biBitCount', ctypes.c_uint16),
                ('biCompression', ctypes.c_uint32),
                ('biSizeImage', ctypes.c_uint32),
                ('biXPelsPerMeter', ctypes.c_int32),
                ('biYPelsPerMeter', ctypes.c_int32),
                ('biClrUsed', ctypes.c_uint32),
                ('biClrImportant', ctypes.c_uint32)
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = size
        bmi.biHeight = -size
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        bits = ctypes.create_string_buffer(size * size * 4)
        hbitmap_int = int(hbitmap)
        hdc_int = int(hdc)

        ctypes.windll.gdi32.GetDIBits(
            hdc_int,
            hbitmap_int,
            0,
            size,
            bits,
            ctypes.byref(bmi),
            0
        )

        image = QImage(bits, size, size, QImage.Format_ARGB32)
        pixmap = QPixmap.fromImage(image)
        win32gui.DestroyIcon(hicon)
        icon = QIcon(pixmap)
        print(
            f"[extract_icon_from_exe] 成功提取图标: {path}, isNull={icon.isNull()}, pixmap.isNull={icon.pixmap(32, 32).isNull()}")
        return icon
    except Exception as e:
        print(f"[extract_icon_from_exe] 提取失败: {e}, 路径: {path}")
        icon = QIcon(path)
        if not icon.isNull():
            print(f"[extract_icon_from_exe] QIcon直接加载exe成功: {path}")
            return icon
        else:
            print(f"[extract_icon_from_exe] QIcon直接加载exe失败: {path}")
        return QIcon()


def resolve_lnk(path):
    try:
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortcut(path)
        return shortcut.TargetPath
    except Exception:
        return path


class AppCardWidget(QFrame):
    def __init__(self, icon, name, path, parent_launcher):
        super().__init__()
        self.path = path
        self.parent_launcher = parent_launcher

        # 设置固定大小，与原来的程序列表项保持一致
        scale = 1.666
        self.setFixedSize(int(90*scale), int(90*scale))

        # 设置样式，简化样式避免双层效果
        self.setStyleSheet("""
            AppCardWidget {
                background-color: transparent;
                border: none;
                margin: 4px;
                padding: 8px;
            }
            AppCardWidget:hover {
                background-color: rgba(237, 242, 247, 0.6);
                border-radius: 6px;
            }
            QLabel {
                color: #2d3748;
                font-size: 12px;
                background: transparent;
                border: none;
            }
        """)

        # 使用绝对定位，让删除按钮不占用布局空间
        # 创建主布局（只包含图标和名称）
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 图标区域
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(int(32*scale), int(32*scale)))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        # 名称区域
        name_label = QLabel(name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setMaximumHeight(int(24*scale))
        layout.addWidget(name_label)

        self.setLayout(layout)

        # 删除按钮使用绝对定位，不占用布局空间
        self.delete_btn = QPushButton("×", self)
        self.delete_btn.setFixedSize(18, 18)
        self.delete_btn.clicked.connect(self.delete_app)
        self.delete_btn.hide()  # 初始隐藏
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                border-radius: 9px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)

        # 将删除按钮定位到右上角
        self.delete_btn.move(self.width() - 20, 2)

        # 双击启动应用
        self.mouseDoubleClickEvent = self.launch_app

    def resizeEvent(self, event):
        """窗口大小改变时重新定位删除按钮"""
        super().resizeEvent(event)
        self.delete_btn.move(self.width() - 20, 2)

    def enterEvent(self, event):
        """鼠标进入事件"""
        self.delete_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开事件"""
        self.delete_btn.hide()
        super().leaveEvent(event)

    def delete_app(self):
        """删除应用"""
        reply = QMessageBox.question(
            self, "确认", f"确定要删除应用：\n{os.path.basename(self.path)}？",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.parent_launcher.remove_app_from_current_group(self.path)

    def launch_app(self, event):
        """启动应用"""
        try:
            subprocess.Popen(self.path, shell=True)
        except Exception as e:
            QMessageBox.warning(self, "启动失败", f"无法启动应用：\n{str(e)}")


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedSize(400, 200)
        self.setModal(True)

        # 加载当前设置
        self.settings = load_settings()

        # 创建界面
        self.setup_ui()

        # 应用样式
        self.setStyleSheet("""
            QDialog {
                background-color: #f8fafc;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #2d3748;
                font-size: 14px;
            }
            QCheckBox {
                color: #2d3748;
                font-size: 14px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #cbd5e0;
                border-radius: 3px;
                background-color: white;
            }
            QCheckBox::indicator:checked {
                background-color: #4299e1;
                border-color: #4299e1;
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOSIgdmlld0JveD0iMCAwIDEyIDkiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDQuNUw0LjUgOEwxMSAxIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPgo8L3N2Zz4K);
            }
            QPushButton {
                background-color: #4299e1;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3182ce;
            }
            QPushButton:pressed {
                background-color: #2b6cb0;
            }
        """)

    def setup_ui(self):
        layout = QVBoxLayout()

        # 表单布局
        form_layout = QFormLayout()
        form_layout.setSpacing(15)

        # 开机自启选项 - 同步实际状态
        actual_auto_start = get_auto_start_status()
        self.settings["auto_start"] = actual_auto_start

        self.auto_start_checkbox = QCheckBox("开机自动启动")
        self.auto_start_checkbox.setChecked(self.settings["auto_start"])
        self.auto_start_checkbox.stateChanged.connect(
            self.on_auto_start_changed)

        # 最小化到托盘选项
        self.minimize_to_tray_checkbox = QCheckBox("关闭窗口时最小化到系统托盘")
        self.minimize_to_tray_checkbox.setChecked(
            self.settings["minimize_to_tray"])
        self.minimize_to_tray_checkbox.stateChanged.connect(
            self.on_minimize_to_tray_changed)

        form_layout.addRow("", self.auto_start_checkbox)
        form_layout.addRow("", self.minimize_to_tray_checkbox)

        layout.addLayout(form_layout)
        layout.addStretch()

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        ok_button = QPushButton("确定")
        ok_button.clicked.connect(self.accept)

        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #a0aec0;
                color: white;
            }
            QPushButton:hover {
                background-color: #718096;
            }
        """)

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def on_auto_start_changed(self, state):
        self.settings["auto_start"] = (state == Qt.Checked)
        # 立即应用设置
        set_auto_start(self.settings["auto_start"])

    def on_minimize_to_tray_changed(self, state):
        self.settings["minimize_to_tray"] = (state == Qt.Checked)

    def get_settings(self):
        return self.settings


class SoftwareLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("app.ico"))
        self.setWindowTitle("软件组启动器")
        self.setAcceptDrops(True)
        self.resize(1200, 800)

        # 恢复样式表
        self.setStyleSheet("""
            QWidget {
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                font-size: 14px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f8fafc, stop:1 #e2e8f0);
            }
            QListWidget {
                background-color: rgba(255, 255, 255, 0.9);
                border: 1px solid #cbd5e0;
                border-radius: 8px;
                padding: 8px;
                selection-background-color: #4299e1;
                selection-color: white;
                alternate-background-color: #f7fafc;
                gridline-color: #e2e8f0;
                outline: none;
            }
            QListWidget::item {
                background-color: rgba(255, 255, 255, 0.8);
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                margin: 2px;
                padding: 8px;
                color: #2d3748;
            }
            QListWidget::item:hover {
                background-color: #edf2f7;
                border: 1px solid #cbd5e0;
            }
            QListWidget::item:selected {
                background-color: #4299e1;
                color: white;
                border: 1px solid #3182ce;
                font-weight: bold;
            }
            QPushButton {
                background-color: #4299e1;
                color: white;
                border: none;
                padding: 10px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
                min-height: 18px;
            }
            QPushButton:hover {
                background-color: #3182ce;
            }
            QPushButton:pressed {
                background-color: #2b6cb0;
            }
            QPushButton:disabled {
                background-color: #a0aec0;
                color: #718096;
            }
            QLabel {
                color: #2d3748;
                font-weight: bold;
                font-size: 15px;
                padding: 6px 0;
            }
            QMenu {
                background-color: rgba(255, 255, 255, 0.95);
                border: 1px solid #cbd5e0;
                border-radius: 6px;
                padding: 4px;
                color: #2d3748;
                font-weight: 500;
            }
            QMenu::item {
                background-color: transparent;
                border-radius: 4px;
                padding: 6px 12px;
                margin: 1px;
            }
            QMenu::item:selected {
                background-color: #edf2f7;
                color: #2d3748;
            }
            QMenu::separator {
                height: 1px;
                background-color: #e2e8f0;
                margin: 4px 0;
            }
            QScrollBar:vertical {
                background-color: #f7fafc;
                width: 10px;
                border-radius: 5px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background-color: #cbd5e0;
                border-radius: 5px;
                min-height: 20px;
                margin: 1px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a0aec0;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        # 移除无边框设计，使用标准窗口
        # self.setWindowFlags(Qt.FramelessWindowHint)
        # self.setAttribute(Qt.WA_TranslucentBackground)

        # 创建主容器
        # self.main_container = QWidget()
        # self.main_container.setObjectName("mainContainer")
        # self.main_container.setStyleSheet("""
        #     #mainContainer {
        #         background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        #             stop:0 #f8fafc, stop:1 #e2e8f0);
        #         border-radius: 12px;
        #         border: 1px solid #cbd5e0;
        #     }
        # """)

        # 加载设置和数据
        self.settings = load_settings()
        self.data = load_config()
        self.current_group = None

        # 保留加载状态标记
        self.loading_group = False  # 标记是否正在加载组

        # 初始化系统托盘
        self.setup_system_tray()

        # 注释掉所有 setStyleSheet 相关代码
        # self.setStyleSheet("")
        # print("[UI] 主窗口样式表已注释")

        # 放大因子
        scale = 1.666  # 2/3 增大

        # 左侧：组列表
        self.group_list = QListWidget()
        self.group_list.itemClicked.connect(self.on_group_clicked)
        self.group_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.group_list.customContextMenuRequested.connect(
            self.show_group_context_menu)
        # 先创建状态栏
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(
            f"color: #4a5568; font-size: {int(12*scale)}px; padding: {int(5*scale)}px {int(10*scale)}px; background: rgba(255,255,255,0.8); border-radius: {int(4*scale)}px; border: 1px solid #e2e8f0;")
        self.status_label.setAlignment(Qt.AlignCenter)
        # 先创建程序显示区域
        self.program_container = QWidget()
        self.program_container.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.9);
                border: 1px solid #cbd5e0;
                border-radius: 8px;
            }
        """)

        self.program_layout = QVBoxLayout()
        self.program_scroll_layout = QHBoxLayout()
        self.program_scroll_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # 创建一个可滚动的区域来放置应用卡片
        from PyQt5.QtWidgets import QScrollArea
        self.program_scroll = QScrollArea()
        self.program_scroll.setWidgetResizable(True)
        self.program_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.program_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.program_scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #f7fafc;
                width: 10px;
                border-radius: 5px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background-color: #cbd5e0;
                border-radius: 5px;
                min-height: 20px;
                margin: 1px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a0aec0;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background-color: #f7fafc;
                height: 10px;
                border-radius: 5px;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background-color: #cbd5e0;
                border-radius: 5px;
                min-width: 20px;
                margin: 1px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #a0aec0;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

        # 创建一个容器来放置所有应用卡片
        self.program_cards_container = QWidget()
        self.program_cards_container.setStyleSheet(
            "background-color: transparent;")
        self.program_cards_layout = QHBoxLayout()
        self.program_cards_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.program_cards_layout.setSpacing(int(12*scale))
        self.program_cards_layout.setContentsMargins(5, 5, 5, 5)
        self.program_cards_container.setLayout(self.program_cards_layout)

        self.program_scroll.setWidget(self.program_cards_container)
        self.program_layout.addWidget(self.program_scroll)
        self.program_container.setLayout(self.program_layout)
        # 先创建所有按钮
        btn_font = QFont()
        btn_font.setPointSize(int(13*scale))
        btn_height = int(36*scale)
        self.add_group_btn = QPushButton("➕ 新建组")
        self.add_group_btn.setFont(btn_font)
        self.add_group_btn.setMinimumHeight(btn_height)
        self.add_group_btn.clicked.connect(self.add_group)
        # 移除保存按钮，现在使用自动保存
        self.launch_btn = QPushButton("🚀 启动当前组")
        self.launch_btn.setFont(btn_font)
        self.launch_btn.setMinimumHeight(btn_height)
        self.launch_btn.clicked.connect(self.launch_all)
        self.settings_btn = QPushButton("⚙️ 设置")
        self.settings_btn.setFont(btn_font)
        self.settings_btn.setMinimumHeight(btn_height)
        self.settings_btn.clicked.connect(self.show_settings)

        # 左侧：组区标题和按钮同一行
        group_title_layout = QHBoxLayout()
        group_title_label = QLabel("📁 软件组")
        group_title_label.setStyleSheet(
            f"font-size: {int(15*scale)}px; font-weight: bold; padding: {int(6*scale)}px 0;")
        group_title_layout.addWidget(group_title_label)
        group_title_layout.addStretch()
        group_title_layout.addWidget(self.add_group_btn)

        # 右侧：应用区标题和按钮同一行
        app_title_layout = QHBoxLayout()
        app_title_label = QLabel("📱 拖入 EXE 或快捷方式：")
        app_title_label.setStyleSheet(
            f"font-size: {int(15*scale)}px; font-weight: bold; padding: {int(6*scale)}px 0;")
        app_title_layout.addWidget(app_title_label)
        app_title_layout.addStretch()
        app_title_layout.addWidget(self.launch_btn)
        app_title_layout.addWidget(self.settings_btn)

        # 左右布局
        left_layout = QVBoxLayout()
        left_layout.addLayout(group_title_layout)
        left_layout.addWidget(self.group_list)

        right_layout = QVBoxLayout()
        right_layout.addLayout(app_title_layout)
        right_layout.addWidget(self.program_container)
        right_layout.addWidget(self.status_label)

        # 主内容布局
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(20, 10, 20, 20)
        content_layout.setSpacing(20)
        content_layout.addLayout(left_layout, 2)
        content_layout.addLayout(right_layout, 5)

        # 设置主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.addLayout(content_layout)

        self.setLayout(main_layout)
        self.refresh_group_list()

    # 移除保存状态管理方法，现在使用自动保存

    def update_group_display(self, group_name):
        """更新组列表中的显示状态"""
        # 不再在组名上显示*标记，改为在状态栏显示
        self.update_status_message()

    def update_status_message(self):
        """更新状态栏信息"""
        if not self.current_group:
            self.status_label.setText("就绪")
            return

        program_count = len(self.get_current_program_paths())
        self.status_label.setText(
            f"📁 已选择组 '{self.current_group}' ({program_count} 个程序)")

    # 旧的get_current_program_paths方法已移动到后面，使用新的卡片布局

    # 移除保存状态检查方法，现在使用自动保存

    def refresh_group_list(self):
        self.group_list.clear()
        for group in self.data:
            self.group_list.addItem(group)

        if self.data:
            self.group_list.setCurrentRow(0)
            self.on_group_selected(self.group_list.item(0))

    def on_group_clicked(self, item):
        """处理组列表点击事件"""
        new_group = item.text()

        # 如果点击的是当前组，直接返回
        if self.current_group == new_group:
            return

        # 直接切换到新组（现在使用自动保存，不需要检查未保存状态）
        self.switch_to_group(new_group)

    def switch_to_group(self, group_name):
        """切换到指定组"""
        self.current_group = group_name
        self.clear_program_cards()

        # 重新加载程序列表时不触发修改状态
        self.loading_group = True
        for path in self.data[group_name]:
            self.add_program_item(path)
        self.loading_group = False

        self.update_status_message()

    def clear_program_cards(self):
        """清空程序卡片"""
        while self.program_cards_layout.count():
            child = self.program_cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def get_current_program_paths(self):
        """获取当前程序列表中的所有路径"""
        paths = []
        for i in range(self.program_cards_layout.count()):
            widget = self.program_cards_layout.itemAt(i).widget()
            if isinstance(widget, AppCardWidget):
                paths.append(widget.path)
        return paths

    def auto_save_current_group(self):
        """自动保存当前组"""
        if not self.current_group:
            return

        paths = self.get_current_program_paths()
        self.data[self.current_group] = paths
        save_config(self.data)

        self.update_status_message()
        print(f"[自动保存] 组 '{self.current_group}' 已保存 ({len(paths)} 个程序)")

    def remove_app_from_current_group(self, app_path):
        """从当前组中移除应用"""
        if not self.current_group:
            return

        # 从布局中移除对应的卡片
        for i in range(self.program_cards_layout.count()):
            widget = self.program_cards_layout.itemAt(i).widget()
            if isinstance(widget, AppCardWidget) and widget.path == app_path:
                self.program_cards_layout.removeWidget(widget)
                widget.deleteLater()
                break

        # 自动保存
        self.auto_save_current_group()

    def on_group_selected(self, item):
        """兼容性方法，用于程序初始化时调用"""
        new_group = item.text()
        self.switch_to_group(new_group)

    def add_group(self):
        name, ok = QInputDialog.getText(self, "新建软件组", "请输入组名：")
        if ok and name.strip():
            name = name.strip()
            if name in self.data:
                QMessageBox.warning(self, "警告", "组名已存在")
                return
            self.data[name] = []
            save_config(self.data)  # 立即保存新组
            self.refresh_group_list()

    def delete_group(self, name=None):
        group = name or self.current_group
        if not group:
            return
        reply = QMessageBox.question(
            self, "确认", f"确定要删除组 '{group}'？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.data[group]
            save_config(self.data)  # 立即保存
            self.refresh_group_list()
            self.clear_program_cards()

    def rename_group(self, item):
        old_name = item.text()
        new_name, ok = QInputDialog.getText(
            self, "重命名组", "请输入新名称：", text=old_name)
        if ok and new_name.strip() and new_name != old_name:
            new_name = new_name.strip()
            self.data[new_name] = self.data.pop(old_name)
            # 更新当前组名
            if self.current_group == old_name:
                self.current_group = new_name
            save_config(self.data)  # 立即保存
            self.refresh_group_list()

    def launch_group(self, name):
        if not name or name not in self.data:
            self.status_label.setText("❌ 请先选择一个组")
            return
        launched_count = 0
        for path in self.data[name]:
            try:
                subprocess.Popen(path, shell=True)
                launched_count += 1
            except Exception as e:
                QMessageBox.warning(self, "启动失败", f"{path}\n{str(e)}")
        self.status_label.setText(
            f"🚀 已启动 {launched_count}/{len(self.data[name])} 个程序")

    def show_group_context_menu(self, pos):
        item = self.group_list.itemAt(pos)
        menu = QMenu(self)

        if item:
            group_name = item.text()  # 不再需要移除*标记
            action_launch = QAction("🚀 启动组", self)
            action_launch.triggered.connect(
                lambda: self.launch_group(group_name))
            menu.addAction(action_launch)

            action_rename = QAction("✏️ 重命名", self)
            action_rename.triggered.connect(lambda: self.rename_group(item))
            menu.addAction(action_rename)

            # 复制组功能
            action_copy = QAction("📋 复制组", self)

            def copy_group():
                old_name = group_name
                new_name, ok = QInputDialog.getText(
                    self, "复制组", f"请输入新组名（将复制 '{old_name}'）：")
                if ok and new_name.strip():
                    new_name = new_name.strip()
                    if new_name in self.data:
                        QMessageBox.warning(self, "警告", "组名已存在")
                        return
                    self.data[new_name] = list(self.data[old_name])  # 深拷贝
                    save_config(self.data)  # 立即保存
                    self.refresh_group_list()
                    QMessageBox.information(
                        self, "复制成功", f"组 '{old_name}' 已复制为 '{new_name}'")
            action_copy.triggered.connect(copy_group)
            menu.addAction(action_copy)

            action_delete = QAction("🗑 删除组", self)
            action_delete.triggered.connect(
                lambda: self.delete_group(group_name))
            menu.addAction(action_delete)
        else:
            action_add = QAction("➕ 新建组", self)
            action_add.triggered.connect(self.add_group)
            menu.addAction(action_add)

        menu.exec_(self.group_list.mapToGlobal(pos))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.current_group:
            QMessageBox.warning(self, "未选择组", "请先选择一个组")
            return
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path) and (path.endswith(".exe") or path.endswith(".lnk")):
                self.add_program_item(path)

    def add_program_item(self, path):
        # 应用名：.lnk用快捷方式名，exe用文件名
        if path.endswith('.lnk'):
            name = os.path.splitext(os.path.basename(path))[0]
        else:
            name = os.path.basename(path)
        display_path = path
        icon = QIcon()
        default_icon = QIcon("app.ico") if os.path.exists(
            "app.ico") else QIcon()
        feishu_icon_path = r"D:/SoftWare/Feishu/icon.ico"
        feishu_icon = QIcon(feishu_icon_path) if os.path.exists(
            feishu_icon_path) else None

        if path.endswith(".lnk"):
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
            # 不再覆盖name，始终用.lnk文件名
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
                print(f"[图标] QIcon({path})兜底失败，使用默认图标app.ico")
                icon = QIcon("app.ico") if os.path.exists(
                    "app.ico") else QIcon()

                # 创建应用卡片
        app_card = AppCardWidget(icon, name, display_path, self)
        self.program_cards_layout.addWidget(app_card)

        print(f"[UI] 添加应用卡片: {name}")

        # 如果不是加载状态，则自动保存
        if self.current_group and not self.loading_group:
            self.auto_save_current_group()

        # 移除旧的右键菜单方法，现在使用卡片上的删除按钮

    def save_group(self):
        group = self.current_group
        if not group:
            self.status_label.setText("❌ 请先选择一个组")
            return
        paths = [self.program_list.item(i).data(
            Qt.UserRole) for i in range(self.program_list.count())]
        self.data[group] = paths
        save_config(self.data)

        QMessageBox.information(self, "保存成功", "配置已保存")

    def launch_all(self):
        self.launch_group(self.current_group)

    def show_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            settings = dialog.get_settings()
            save_settings(settings)
            self.settings = settings
            if settings["auto_start"]:
                set_auto_start(True)
            else:
                set_auto_start(False)
            QMessageBox.information(self, "设置已保存", "设置已保存")

    def setup_system_tray(self):
        """初始化系统托盘图标"""
        self.tray_icon = QSystemTrayIcon(self)

        # 尝试加载图标文件，如果不存在则使用默认图标
        icon_path = "app.ico"
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            # 创建一个简单的默认图标
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.transparent)
            self.tray_icon.setIcon(QIcon(pixmap))

        self.tray_icon.setVisible(True)

        # 创建菜单
        self.tray_menu = QMenu(self)
        self.tray_menu.addAction("显示主窗口", self.show)
        self.tray_menu.addAction("退出", self.quit_app)
        self.tray_icon.setContextMenu(self.tray_menu)

        # 连接信号
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.messageClicked.connect(self.tray_icon_message_clicked)

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show()
        elif reason == QSystemTrayIcon.DoubleClick:
            self.show()

    def tray_icon_message_clicked(self):
        self.show()

        # 移除未保存检查方法，现在使用自动保存

    def quit_app(self):
        """退出应用程序"""
        self.tray_icon.hide()
        sys.exit(0)

    def closeEvent(self, event):
        """关闭窗口事件"""
        if self.settings.get("minimize_to_tray", True):
            self.hide()
            self.tray_icon.showMessage(
                "软件组启动器",
                "程序已最小化到系统托盘",
                QSystemTrayIcon.Information,
                2000
            )
            event.ignore()
        else:
            self.tray_icon.hide()
            event.accept()


if __name__ == "__main__":
    # 保证工作目录为脚本所在目录
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))
    app = QApplication(sys.argv)
    win = SoftwareLauncher()
    win.show()
    sys.exit(app.exec_())
