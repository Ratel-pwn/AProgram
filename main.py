import sys
import os
import json
import subprocess
import winreg
from PyQt5.QtWidgets import (
    QApplication, QWidget, QListWidget, QPushButton, QVBoxLayout,
    QHBoxLayout, QListWidgetItem, QFileDialog, QInputDialog, QMessageBox, QLabel,
    QMenu, QAction, QSystemTrayIcon, QCheckBox, QDialog, QFormLayout
)
from PyQt5.QtGui import QPixmap, QImage, QIcon
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
            return QIcon()
        hicon = large[0]
        hdc = win32gui.CreateCompatibleDC(0)
        size = win32api.GetSystemMetrics(win32con.SM_CXICON)
        hbitmap = win32gui.CreateCompatibleBitmap(hdc, size, size)
        win32gui.SelectObject(hdc, hbitmap)
        win32gui.DrawIconEx(hdc, 0, 0, hicon, size, size,
                            0, 0, win32con.DI_NORMAL)

        # BitmapInfoHeader
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
        bmi.biHeight = -size  # Top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0  # BI_RGB

        bits = ctypes.create_string_buffer(size * size * 4)

        # GetDIBits 参数修正
        hbitmap_int = int(hbitmap)  # 强制转换为 int
        hdc_int = int(hdc)

        ctypes.windll.gdi32.GetDIBits(
            hdc_int,
            hbitmap_int,
            0,
            size,
            bits,
            ctypes.byref(bmi),
            0  # DIB_RGB_COLORS
        )

        image = QImage(bits, size, size, QImage.Format_ARGB32)
        pixmap = QPixmap.fromImage(image)
        win32gui.DestroyIcon(hicon)
        return QIcon(pixmap)
    except Exception as e:
        print(f"[extract_icon_from_exe] 提取失败: {e}")
        return QIcon()


def resolve_lnk(path):
    try:
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortcut(path)
        return shortcut.TargetPath
    except Exception:
        return path


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
        self.setWindowTitle("软件组启动器")
        self.setAcceptDrops(True)
        self.resize(900, 600)

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

        # 初始化系统托盘
        self.setup_system_tray()

        # 样式表（现代化 UI）
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

        # 左侧：组列表
        self.group_list = QListWidget()
        self.group_list.itemClicked.connect(self.on_group_selected)
        self.group_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.group_list.customContextMenuRequested.connect(
            self.show_group_context_menu)

        # 右侧：程序列表
        self.program_list = QListWidget()
        self.program_list.setIconSize(QSize(32, 32))
        self.program_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.program_list.customContextMenuRequested.connect(
            self.show_context_menu)

        # 按钮区域
        self.add_group_btn = QPushButton("➕ 新建组")
        self.add_group_btn.clicked.connect(self.add_group)

        self.save_btn = QPushButton("💾 保存组")
        self.save_btn.clicked.connect(self.save_group)

        self.launch_btn = QPushButton("🚀 启动当前组")
        self.launch_btn.clicked.connect(self.launch_all)

        # 设置按钮
        self.settings_btn = QPushButton("⚙️ 设置")
        self.settings_btn.clicked.connect(self.show_settings)

        # 状态栏
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #4a5568;
                font-size: 12px;
                padding: 5px 10px;
                background: rgba(255, 255, 255, 0.8);
                border-radius: 4px;
                border: 1px solid #e2e8f0;
            }
        """)
        self.status_label.setAlignment(Qt.AlignCenter)

        # 左右布局
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("📁 软件组"))
        left_layout.addWidget(self.group_list)
        left_layout.addWidget(self.add_group_btn)

        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("📱 拖入 EXE 或快捷方式："))
        right_layout.addWidget(self.program_list)
        right_layout.addWidget(self.save_btn)
        right_layout.addWidget(self.launch_btn)
        right_layout.addWidget(self.settings_btn)
        right_layout.addWidget(self.status_label)

        # 创建标题栏
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("""
            QWidget {
                background: transparent;
                color: #2d3748;
                font-weight: bold;
                font-size: 16px;
            }
        """)

        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(20, 0, 20, 0)

        title_label = QLabel("🚀 软件组启动器")
        title_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #2d3748;")

        title_layout.addWidget(title_label)
        title_layout.addStretch()

        # 主内容布局
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(20, 10, 20, 20)
        content_layout.setSpacing(20)
        content_layout.addLayout(left_layout, 2)
        content_layout.addLayout(right_layout, 5)

        # 设置主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.addWidget(title_bar)
        main_layout.addLayout(content_layout)

        self.setLayout(main_layout)
        self.refresh_group_list()

    def refresh_group_list(self):
        self.group_list.clear()
        for group in self.data:
            self.group_list.addItem(group)
        if self.data:
            self.group_list.setCurrentRow(0)
            self.on_group_selected(self.group_list.item(0))

    def on_group_selected(self, item):
        group = item.text()
        self.current_group = group
        self.program_list.clear()
        for path in self.data[group]:
            self.add_program_item(path)
        self.status_label.setText(
            f"📁 已选择组 '{group}' ({len(self.data[group])} 个程序)")

    def add_group(self):
        name, ok = QInputDialog.getText(self, "新建软件组", "请输入组名：")
        if ok and name.strip():
            name = name.strip()
            if name in self.data:
                QMessageBox.warning(self, "警告", "组名已存在")
                return
            self.data[name] = []
            self.refresh_group_list()

    def delete_group(self, name=None):
        group = name or self.current_group
        if not group:
            return
        reply = QMessageBox.question(
            self, "确认", f"确定要删除组 '{group}'？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.data[group]
            self.refresh_group_list()
            self.program_list.clear()
            save_config(self.data)

    def rename_group(self, item):
        old_name = item.text()
        new_name, ok = QInputDialog.getText(
            self, "重命名组", "请输入新名称：", text=old_name)
        if ok and new_name.strip() and new_name != old_name:
            new_name = new_name.strip()
            self.data[new_name] = self.data.pop(old_name)
            save_config(self.data)
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
            action_launch = QAction("🚀 启动组", self)
            action_launch.triggered.connect(
                lambda: self.launch_group(item.text()))
            menu.addAction(action_launch)

            action_rename = QAction("✏️ 重命名", self)
            action_rename.triggered.connect(lambda: self.rename_group(item))
            menu.addAction(action_rename)

            action_delete = QAction("🗑 删除组", self)
            action_delete.triggered.connect(
                lambda: self.delete_group(item.text()))
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
        name = os.path.basename(path)
        display_path = path
        icon = QIcon()

        if path.endswith(".lnk"):
            resolved_path = resolve_lnk(path)
            icon_path = get_icon_from_lnk(path) or resolved_path

            if os.path.exists(resolved_path):
                name = os.path.splitext(os.path.basename(resolved_path))[0]
            if icon_path and os.path.exists(icon_path):
                icon = extract_icon_from_exe(icon_path)
        elif os.path.exists(path):
            icon = extract_icon_from_exe(path)

        item = QListWidgetItem(icon, name)
        item.setToolTip(display_path)
        item.setData(Qt.UserRole, display_path)
        self.program_list.addItem(item)

        # 更新状态
        count = self.program_list.count()
        self.status_label.setText(f"💾 已添加 {count} 个程序")

    def show_context_menu(self, pos):
        item = self.program_list.itemAt(pos)
        if item:
            reply = QMessageBox.question(
                self, "删除程序", f"是否删除：\n{item.toolTip()}？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.program_list.takeItem(self.program_list.row(item))
                count = self.program_list.count()
                self.status_label.setText(f"🗑️ 已删除程序，剩余 {count} 个")

    def save_group(self):
        group = self.current_group
        if not group:
            self.status_label.setText("❌ 请先选择一个组")
            return
        paths = [self.program_list.item(i).data(
            Qt.UserRole) for i in range(self.program_list.count())]
        self.data[group] = paths
        save_config(self.data)
        self.status_label.setText(f"✅ 组 '{group}' 已保存 ({len(paths)} 个程序)")
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
            self.quit_app()
            event.accept()


if __name__ == "__main__":
    # 保证工作目录为脚本所在目录
    os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))
    app = QApplication(sys.argv)
    win = SoftwareLauncher()
    win.show()
    sys.exit(app.exec_())
