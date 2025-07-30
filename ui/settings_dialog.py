"""设置对话框组件"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QCheckBox, QPushButton, QLabel)
from PyQt5.QtCore import Qt
from config.settings import load_settings, get_auto_start_status, set_auto_start
from .styles import get_settings_dialog_style


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
        self.setStyleSheet(get_settings_dialog_style())

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
