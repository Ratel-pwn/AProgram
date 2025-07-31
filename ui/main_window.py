"""主窗口类"""
import os
import sys
import copy
import subprocess
from PyQt5.QtWidgets import (QWidget, QListWidget, QPushButton, QVBoxLayout,
                             QHBoxLayout, QInputDialog, QMessageBox, QLabel,
                             QMenu, QAction, QSystemTrayIcon, QDialog, QScrollArea)
from PyQt5.QtGui import QIcon, QFont, QPixmap
from PyQt5.QtCore import Qt

from config.settings import load_config, save_config, load_settings, save_settings, set_auto_start
from config.constants import SCALE_FACTOR, BUTTON_HEIGHT, APP_ICON_PATH
from utils.file_utils import is_valid_app_file, get_app_name
from utils.icon_utils import get_app_icon
from utils.process_utils import close_application_by_path, launch_application, is_application_running
from utils.system_utils import create_default_icon
from .app_card import AppCardWidget
from .settings_dialog import SettingsDialog
from .flow_layout import FlowLayout
from .styles import (get_main_window_style, get_close_button_style,
                     get_program_container_style, get_scroll_area_style)


class SoftwareLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(create_default_icon())
        self.setWindowTitle("AProgram")
        self.setAcceptDrops(True)
        self.resize(1200, 800)

        # 应用样式
        self.setStyleSheet(get_main_window_style())

        # 加载设置和数据
        self.settings = load_settings()
        self.data = load_config()
        self.current_group = None

        # 保留加载状态标记
        self.loading_group = False  # 标记是否正在加载组

        # 初始化系统托盘
        self.setup_system_tray()

        # 放大因子
        scale = SCALE_FACTOR

        # 左侧：组列表
        self.group_list = QListWidget()
        self.group_list.itemClicked.connect(self.on_group_clicked)
        self.group_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.group_list.customContextMenuRequested.connect(
            self.show_group_context_menu)

        # 重写鼠标按下事件，阻止右键选中
        self.group_list.mousePressEvent = self.group_list_mouse_press_event

        # 先创建状态栏
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(
            f"color: #4a5568; font-size: {int(12*scale)}px; padding: {int(5*scale)}px {int(10*scale)}px; background: rgba(255,255,255,0.8); border-radius: {int(4*scale)}px; border: 1px solid #e2e8f0;")
        self.status_label.setAlignment(Qt.AlignCenter)

        # 先创建程序显示区域
        self.program_container = QWidget()
        self.program_container.setStyleSheet(get_program_container_style())

        self.program_layout = QVBoxLayout()
        self.program_scroll_layout = QHBoxLayout()
        self.program_scroll_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # 创建一个可滚动的区域来放置应用卡片
        self.program_scroll = QScrollArea()
        self.program_scroll.setWidgetResizable(True)
        self.program_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.program_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.program_scroll.setStyleSheet(get_scroll_area_style())

        # 创建一个容器来放置所有应用卡片
        self.program_cards_container = QWidget()
        self.program_cards_container.setStyleSheet(
            "background-color: transparent;")
        self.program_cards_layout = FlowLayout()
        self.program_cards_layout.setSpacing(int(12*scale))
        self.program_cards_layout.setContentsMargins(5, 5, 5, 5)
        self.program_cards_container.setLayout(self.program_cards_layout)

        self.program_scroll.setWidget(self.program_cards_container)
        self.program_layout.addWidget(self.program_scroll)
        self.program_container.setLayout(self.program_layout)

        # 先创建所有按钮
        btn_font = QFont()
        btn_font.setPointSize(int(13*scale))
        btn_height = BUTTON_HEIGHT

        self.add_group_btn = QPushButton("➕ 新建组")
        self.add_group_btn.setFont(btn_font)
        self.add_group_btn.setMinimumHeight(btn_height)
        self.add_group_btn.clicked.connect(self.add_group)

        self.launch_btn = QPushButton("🚀 启动组")
        self.launch_btn.setFont(btn_font)
        self.launch_btn.setMinimumHeight(btn_height)
        self.launch_btn.clicked.connect(self.launch_all)

        self.close_btn = QPushButton("🛑 关闭组")
        self.close_btn.setFont(btn_font)
        self.close_btn.setMinimumHeight(btn_height)
        self.close_btn.clicked.connect(self.close_all)
        self.close_btn.setStyleSheet(get_close_button_style())

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
        app_title_layout.addWidget(self.close_btn)
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

    def update_group_display(self, group_name):
        """更新组列表中的显示状态"""
        # 不再在组名上显示*标记，改为在状态栏显示
        self.update_status_message()

    def update_status_message(self):
        """更新状态栏信息"""
        if not self.current_group:
            self.status_label.setText("就绪")
            return

        programs = self.get_current_program_paths()
        enabled_count = sum(1 for p in programs if p['enabled'])
        total_count = len(programs)
        self.status_label.setText(
            f"📁 已选择组 '{self.current_group}' ({enabled_count}/{total_count} 个程序已启用)")

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
        group_data = self.data[group_name]

        # 兼容旧格式（纯路径列表）和新格式（包含enabled状态的字典列表）
        if group_data:
            if isinstance(group_data[0], str):
                # 旧格式：转换为新格式，默认全部启用
                for path in group_data:
                    self.add_program_item(path, enabled=True)
            else:
                # 新格式
                for item in group_data:
                    if isinstance(item, dict):
                        self.add_program_item(
                            item['path'], enabled=item.get('enabled', True))
                    else:
                        # 兼容混合格式
                        self.add_program_item(item, enabled=True)

        self.loading_group = False
        self.update_status_message()

    def clear_program_cards(self):
        """清空程序卡片"""
        while self.program_cards_layout.count():
            child = self.program_cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def get_current_program_paths(self):
        """获取当前程序列表中的所有路径和启用状态"""
        programs = []
        for i in range(self.program_cards_layout.count()):
            widget = self.program_cards_layout.itemAt(i).widget()
            if isinstance(widget, AppCardWidget):
                programs.append({
                    'path': widget.path,
                    'enabled': widget.enabled
                })
        return programs

    def auto_save_current_group(self):
        """自动保存当前组"""
        if not self.current_group:
            return

        programs = self.get_current_program_paths()
        self.data[self.current_group] = programs
        save_config(self.data)

        self.update_status_message()
        print(f"[自动保存] 组 '{self.current_group}' 已保存 ({len(programs)} 个程序)")

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
        total_enabled = 0
        group_data = self.data[name]

        for item in group_data:
            # 兼容旧格式和新格式
            if isinstance(item, str):
                path = item
                enabled = True  # 旧格式默认启用
            else:
                path = item['path']
                enabled = item.get('enabled', True)

            if enabled:
                total_enabled += 1
                if launch_application(path):
                    launched_count += 1
                else:
                    QMessageBox.warning(self, "启动失败", f"{path}")

        self.status_label.setText(
            f"🚀 已启动 {launched_count}/{total_enabled} 个已启用程序")

    def launch_all(self):
        """启动当前组中选中的应用"""
        self.launch_group(self.current_group)

    def close_all(self):
        """关闭当前组中选中的应用"""
        self.close_group(self.current_group)

    def close_group(self, name):
        """关闭指定组中选中的应用"""
        if not name or name not in self.data:
            self.status_label.setText("❌ 请先选择一个组")
            return

        # 确认对话框
        reply = QMessageBox.question(
            self, "确认关闭",
            f"确定要关闭组 '{name}' 中所有选中的应用吗？\n\n这将强制关闭正在运行的程序，请确保已保存重要文件。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        closed_count = 0
        total_enabled = 0
        group_data = self.data[name]

        for item in group_data:
            # 兼容旧格式和新格式
            if isinstance(item, str):
                path = item
                enabled = True  # 旧格式默认启用
            else:
                path = item['path']
                enabled = item.get('enabled', True)

            if enabled:
                total_enabled += 1
                try:
                    if close_application_by_path(path):
                        closed_count += 1
                except Exception as e:
                    print(f"[关闭失败] {path}: {str(e)}")

        self.status_label.setText(
            f"🛑 已尝试关闭 {closed_count}/{total_enabled} 个已启用程序")

    def group_list_mouse_press_event(self, event):
        """处理组列表鼠标按下事件，阻止右键选中"""
        if event.button() == Qt.RightButton:
            # 右键时不调用默认的mousePressEvent，阻止选中行为
            return
        else:
            # 左键时正常处理
            QListWidget.mousePressEvent(self.group_list, event)

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
                    # 深拷贝，保持数据格式
                    self.data[new_name] = copy.deepcopy(self.data[old_name])
                    # 复制时默认全部勾选
                    for item in self.data[new_name]:
                        if isinstance(item, dict):
                            item['enabled'] = True
                    save_config(self.data)  # 立即保存
                    self.refresh_group_list()
                    QMessageBox.information(
                        self, "复制成功", f"组 '{old_name}' 已复制为 '{new_name}'（默认全部勾选）")
            action_copy.triggered.connect(copy_group)
            menu.addAction(action_copy)

            # 切换组功能
            action_switch = QAction("🔄 切换组", self)
            action_switch.triggered.connect(
                lambda: self.smart_switch_group(group_name))
            menu.addAction(action_switch)

            action_delete = QAction("🗑 删除组", self)
            action_delete.triggered.connect(
                lambda: self.delete_group(group_name))
            menu.addAction(action_delete)
        else:
            action_add = QAction("➕ 新建组", self)
            action_add.triggered.connect(self.add_group)
            menu.addAction(action_add)

        menu.exec_(self.group_list.mapToGlobal(pos))

    def smart_switch_group(self, target_group_name):
        """智能切换组：关闭原组启动但目标组未启用的应用，启动目标组启用但原组未启动的应用"""
        if not self.current_group or target_group_name == self.current_group:
            self.switch_to_group(target_group_name)
            return

        try:
            # 获取当前组和目标组的应用数据
            current_group_data = self.data.get(self.current_group, [])
            target_group_data = self.data.get(target_group_name, [])

            # 标准化数据格式，确保都是字典格式
            def normalize_group_data(group_data):
                normalized = []
                for item in group_data:
                    if isinstance(item, str):
                        normalized.append({'path': item, 'enabled': True})
                    else:
                        normalized.append(item)
                return normalized

            current_apps = normalize_group_data(current_group_data)
            target_apps = normalize_group_data(target_group_data)

            # 创建路径到启用状态的映射
            current_enabled = {app['path']: app.get(
                'enabled', True) for app in current_apps}
            target_enabled = {app['path']: app.get(
                'enabled', True) for app in target_apps}

            # 统计操作
            closed_count = 0
            launched_count = 0

            # 1. 关闭原组启动但目标组未启用的应用
            for app_path in current_enabled:
                if current_enabled[app_path]:  # 当前组中启用
                    target_app_enabled = target_enabled.get(app_path, False)
                    if not target_app_enabled:  # 目标组中未启用或不存在
                        if is_application_running(app_path):
                            if close_application_by_path(app_path):
                                closed_count += 1

            # 2. 启动目标组启用但原组未启动的应用
            for app_path in target_enabled:
                if target_enabled[app_path]:  # 目标组中启用
                    current_app_enabled = current_enabled.get(app_path, False)
                    if not current_app_enabled:  # 当前组中未启用或不存在
                        if not is_application_running(app_path):
                            if launch_application(app_path):
                                launched_count += 1

            # 3. 切换到目标组
            self.switch_to_group(target_group_name)

            # 显示操作结果
            message = f"🔄 已切换到组 '{target_group_name}'"
            if closed_count > 0 or launched_count > 0:
                message += f"\n关闭了 {closed_count} 个应用，启动了 {launched_count} 个应用"

            self.status_label.setText(message)
            print(
                f"[智能切换] {self.current_group} -> {target_group_name}, 关闭: {closed_count}, 启动: {launched_count}")

        except Exception as e:
            print(f"[切换组失败] {str(e)}")
            self.status_label.setText(f"❌ 切换组失败: {str(e)}")
            # 即使出错也要切换组
            self.switch_to_group(target_group_name)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.current_group:
            QMessageBox.warning(self, "未选择组", "请先选择一个组")
            return
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if is_valid_app_file(path):
                self.add_program_item(path)

    def add_program_item(self, path, enabled=True):
        # 应用名：.lnk用快捷方式名，exe用文件名
        name = get_app_name(path)
        display_path = path
        icon = get_app_icon(path)

        # 创建应用卡片
        app_card = AppCardWidget(icon, name, display_path, self, enabled)
        self.program_cards_layout.addWidget(app_card)

        print(f"[UI] 添加应用卡片: {name} (启用: {enabled})")

        # 如果不是加载状态，则自动保存
        if self.current_group and not self.loading_group:
            self.auto_save_current_group()

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

    def setup_system_tray(self):
        """初始化系统托盘图标"""
        self.tray_icon = QSystemTrayIcon(self)

        # 尝试加载图标文件，如果不存在则使用默认图标
        if os.path.exists(APP_ICON_PATH):
            self.tray_icon.setIcon(QIcon(APP_ICON_PATH))
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
            self.tray_icon.hide()
            event.accept()
