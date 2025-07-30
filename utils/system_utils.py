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


def create_white_default_icon(size=32):
    """创建白色背景的默认图标"""
    from config.constants import APP_ICON_PATH
    from PyQt5.QtGui import QPainter, QBrush, QPen, QColor

    if os.path.exists(APP_ICON_PATH):
        return QIcon(APP_ICON_PATH)
    else:
        # 创建一个白色背景的默认图标
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.white)

        # 绘制一个简单的应用图标样式
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # 绘制外边框 - 深灰色
        pen = QPen(QColor(100, 100, 100), 2)  # 更深的颜色，更粗的线条
        painter.setPen(pen)
        painter.drawRoundedRect(3, 3, size-6, size-6, 6, 6)

        # 绘制应用符号 - 一个带窗口的图标
        # 主窗口
        brush = QBrush(QColor(120, 120, 120))  # 深灰色
        painter.setBrush(brush)
        painter.setPen(Qt.NoPen)

        # 计算图标内部区域
        margin = size // 4
        inner_size = size - 2 * margin

        # 绘制主体
        painter.drawRoundedRect(margin, margin, inner_size, inner_size, 3, 3)

        # 绘制标题栏
        title_height = inner_size // 4
        painter.setBrush(QBrush(QColor(80, 80, 80)))  # 更深的颜色作为标题栏
        painter.drawRoundedRect(margin, margin, inner_size, title_height, 3, 3)

        # 绘制三个圆点（窗口控制按钮）
        dot_size = max(2, size // 16)
        dot_y = margin + title_height // 2
        dot_colors = [QColor(255, 95, 86), QColor(
            255, 189, 46), QColor(39, 201, 63)]  # 红黄绿

        for i, color in enumerate(dot_colors):
            painter.setBrush(QBrush(color))
            dot_x = margin + inner_size - \
                (len(dot_colors) - i) * (dot_size + 3) - 3
            painter.drawEllipse(dot_x, dot_y - dot_size//2, dot_size, dot_size)

        painter.end()
        print(f"[图标] 创建白色背景默认图标，尺寸: {size}x{size}")
        return QIcon(pixmap)


def get_app_directory():
    """获取应用程序目录"""
    return os.path.dirname(os.path.abspath(sys.argv[0]))
