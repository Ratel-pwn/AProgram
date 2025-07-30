"""常量定义"""

# 配置文件名
CONFIG_FILE = "software_groups.json"
SETTINGS_FILE = "settings.json"

# 默认设置
DEFAULT_SETTINGS = {
    "auto_start": False,
    "minimize_to_tray": True
}

# UI 相关常量
SCALE_FACTOR = 1.666  # UI缩放因子
CARD_WIDTH = int(90 * SCALE_FACTOR)
CARD_HEIGHT = int(90 * SCALE_FACTOR)
ICON_SIZE = int(32 * SCALE_FACTOR)
BUTTON_HEIGHT = int(36 * SCALE_FACTOR)

# 应用图标路径
APP_ICON_PATH = "app.ico"
