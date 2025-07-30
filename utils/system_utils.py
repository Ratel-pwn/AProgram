"""系统相关工具"""
import os
import sys
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt


def create_default_icon():
    """创建默认图标"""
    from config.constants import APP_ICON_PATH

    if os.path.exists(APP_ICON_PATH):
        return QIcon(APP_ICON_PATH)
    else:
        # 创建一个简单的默认图标
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        return QIcon(pixmap)


def get_app_directory():
    """获取应用程序目录"""
    return os.path.dirname(os.path.abspath(sys.argv[0]))
