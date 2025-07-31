"""样式定义"""


def get_main_window_style():
    """获取主窗口样式"""
    return """
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
            background-color: transparent;
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
    """


def get_close_button_style():
    """获取关闭按钮样式"""
    return """
        QPushButton {
            background-color: #e53e3e;
            color: white;
            border: none;
            padding: 10px 16px;
            border-radius: 6px;
            font-weight: bold;
            font-size: 13px;
            min-height: 18px;
        }
        QPushButton:hover {
            background-color: #c53030;
        }
        QPushButton:pressed {
            background-color: #9c2c2c;
        }
        QPushButton:disabled {
            background-color: #a0aec0;
            color: #718096;
        }
    """


def get_settings_dialog_style():
    """获取设置对话框样式"""
    return """
        QDialog {
            background-color: #f8fafc;
            font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
        }
        QLabel {
            color: #2d3748;
            font-size: 14px;
            background-color: transparent;
        }
        QCheckBox {
            color: #2d3748;
            font-size: 14px;
            spacing: 8px;
            background-color: transparent;
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
    """


def get_program_container_style():
    """获取程序容器样式"""
    return """
        QWidget {
            background-color: rgba(255, 255, 255, 0.9);
            border: 1px solid #cbd5e0;
            border-radius: 8px;
        }
    """


def get_scroll_area_style():
    """获取滚动区域样式"""
    return """
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
    """
