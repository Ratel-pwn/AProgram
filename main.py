"""
AProgram - 软件组启动器
主入口文件
"""
import os
import sys
from PyQt5.QtWidgets import QApplication
from ui import SoftwareLauncher
from utils.system_utils import get_app_directory


def main():
    """主函数"""
    # 保证工作目录为脚本所在目录
    os.chdir(get_app_directory())

    # 创建应用程序
    app = QApplication(sys.argv)

    # 创建主窗口
    window = SoftwareLauncher()
    window.show()

    # 运行应用程序
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
