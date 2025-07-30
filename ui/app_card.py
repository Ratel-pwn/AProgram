"""应用卡片组件"""
import os
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QMessageBox
from PyQt5.QtCore import Qt
from config.constants import CARD_WIDTH, CARD_HEIGHT, ICON_SIZE
from utils.file_utils import get_app_name
from utils.process_utils import launch_application


class AppCardWidget(QFrame):
    def __init__(self, icon, name, path, parent_launcher, enabled=True):
        super().__init__()
        self.path = path
        self.parent_launcher = parent_launcher
        self.enabled = enabled

        # 设置固定大小
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)

        # 更新样式表，移除复选框样式，添加选中状态的背景色
        self.update_style()

        # 创建主布局（移除勾选框，只包含图标和名称）
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 图标区域 - 使用圆角图标
        from utils.icon_utils import create_rounded_icon
        rounded_icon = create_rounded_icon(icon, ICON_SIZE, radius=8)

        icon_label = QLabel()
        icon_label.setPixmap(rounded_icon.pixmap(ICON_SIZE, ICON_SIZE))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        # 名称区域
        name_label = QLabel(name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setMaximumHeight(int(24 * 1.666))
        layout.addWidget(name_label)

        self.setLayout(layout)

        # 删除按钮使用绝对定位，不占用布局空间
        self.delete_btn = QPushButton("×", self)
        self.delete_btn.setFixedSize(20, 20)
        self.delete_btn.clicked.connect(self.delete_app)
        self.delete_btn.hide()  # 初始隐藏
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
                text-align: center;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)

        # 将删除按钮定位到右上角
        self.delete_btn.move(self.width() - 22, 2)

        # 单击切换选中状态，双击启动应用
        self.mousePressEvent = self.on_mouse_press
        self.mouseDoubleClickEvent = self.launch_app

    def update_style(self):
        """更新样式表，根据选中状态设置背景色"""
        if self.enabled:
            # 选中状态：蓝色背景
            self.setStyleSheet("""
                AppCardWidget {
                    background-color: rgba(66, 153, 225, 0.4);
                    border: 2px solid #4299e1;
                    border-radius: 8px;
                    margin: 4px;
                    padding: 8px;
                }
                AppCardWidget:hover {
                    background-color: rgba(66, 153, 225, 0.9);
                    border: 2px solid #3182ce;
                }
                QLabel {
                    color: white;
                    font-size: 12px;
                    font-weight: bold;
                    background: transparent;
                    border: none;
                }
            """)
        else:
            # 未选中状态：透明背景
            self.setStyleSheet("""
                AppCardWidget {
                    background-color: transparent;
                    border: 2px solid #e2e8f0;
                    border-radius: 8px;
                    margin: 4px;
                    padding: 8px;
                    opacity: 0.6;
                }
                AppCardWidget:hover {
                    background-color: rgba(237, 242, 247, 0.6);
                    border: 2px solid #cbd5e0;
                    opacity: 0.8;
                }
                QLabel {
                    color: #718096;
                    font-size: 12px;
                    background: transparent;
                    border: none;
                }
            """)

    def on_mouse_press(self, event):
        """处理鼠标单击事件，切换选中状态"""
        if event.button() == Qt.LeftButton:
            # 切换选中状态
            self.enabled = not self.enabled
            self.update_style()
            # 通知父窗口保存状态
            if hasattr(self.parent_launcher, 'auto_save_current_group'):
                self.parent_launcher.auto_save_current_group()

    def resizeEvent(self, event):
        """窗口大小改变时重新定位删除按钮"""
        super().resizeEvent(event)
        self.delete_btn.move(self.width() - 22, 2)

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
            self.parent_launcher, "确认", f"确定要删除应用：\n{os.path.basename(self.path)}？",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.parent_launcher.remove_app_from_current_group(self.path)

    def launch_app(self, event):
        """启动应用"""
        if not launch_application(self.path):
            QMessageBox.warning(self, "启动失败", f"无法启动应用：\n{self.path}")
