#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""
AUTO_MAA
AUTO_MAA主程序
v4.4
作者：DLmaster_361
"""


# Nuitka环境检测和修复
def setup_nuitka_compatibility():
    """设置Nuitka打包环境的兼容性"""

    # 检测打包环境
    is_nuitka = (
        hasattr(sys, "frozen")
        or "nuitka" in sys.modules
        or "Temp\\AUTO_MAA" in str(sys.executable)
        or os.path.basename(sys.executable) == "AUTO_MAA.exe"
    )

    if is_nuitka:

        # 修复PySide6 QTimer问题
        try:
            from PySide6.QtCore import QTimer

            original_singleShot = QTimer.singleShot

            @staticmethod
            def safe_singleShot(*args, **kwargs):
                if len(args) >= 2:
                    msec = args[0]
                    callback = args[-1]
                    # 确保使用正确的调用签名
                    return original_singleShot(msec, callback)
                return original_singleShot(*args, **kwargs)

            QTimer.singleShot = safe_singleShot

        except Exception as e:

            pass


# 立即应用兼容性修复
setup_nuitka_compatibility()

# 屏蔽广告
import builtins

original_print = builtins.print


def no_print(*args, **kwargs):
    if (
        args
        and isinstance(args[0], str)
        and "QFluentWidgets Pro is now released." in args[0]
    ):
        return
    return original_print(*args, **kwargs)


builtins.print = no_print


import os
import sys
import ctypes
import traceback
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentTranslator


def is_admin() -> bool:
    """检查当前程序是否以管理员身份运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def show_system_error(title: str, message: str, detailed_error: str = None):
    """使用系统级消息框显示错误"""
    try:
        # Windows系统消息框
        if sys.platform == "win32":
            # 组合完整的错误信息
            full_message = message
            if detailed_error:
                # 限制详细错误信息长度，避免消息框过大
                if len(detailed_error) > 2000:
                    detailed_error = (
                        detailed_error[:2000] + "\n\n... (错误信息过长已截断)"
                    )
                full_message += f"\n\n详细错误信息:\n{detailed_error}"

            # 使用ctypes调用Windows API
            ctypes.windll.user32.MessageBoxW(
                0,  # 父窗口句柄
                full_message,  # 消息内容
                title,  # 标题
                0x10 | 0x0,  # MB_ICONERROR | MB_OK
            )

        # Linux系统 - 尝试使用zenity或kdialog
        elif sys.platform.startswith("linux"):
            full_message = message
            if detailed_error:
                full_message += f"\n\n详细错误:\n{detailed_error[:1000]}"

            try:
                # 尝试zenity (GNOME)
                os.system(
                    f'zenity --error --title="{title}" --text="{full_message}" 2>/dev/null'
                )
            except:
                try:
                    # 尝试kdialog (KDE)
                    os.system(
                        f'kdialog --error "{full_message}" --title "{title}" 2>/dev/null'
                    )
                except:
                    # 降级到控制台输出
                    print(f"错误: {title}")
                    print(f"消息: {message}")
                    if detailed_error:
                        print(f"详细信息:\n{detailed_error}")

        # macOS系统
        elif sys.platform == "darwin":
            full_message = message
            if detailed_error:
                full_message += f"\n\n详细错误:\n{detailed_error[:1000]}"

            try:
                os.system(
                    f'osascript -e \'display alert "{title}" message "{full_message}" as critical\''
                )
            except:
                print(f"错误: {title}")
                print(f"消息: {message}")
                if detailed_error:
                    print(f"详细信息:\n{detailed_error}")

        else:
            # 其他系统降级到控制台输出
            print(f"错误: {title}")
            print(f"消息: {message}")
            if detailed_error:
                print(f"详细信息:\n{detailed_error}")

    except Exception as e:
        # 如果连系统消息框都失败了，输出到控制台
        print(f"无法显示错误对话框: {e}")
        print(f"原始错误: {title} - {message}")
        if detailed_error:
            print(f"详细错误信息:\n{detailed_error}")


def save_error_log(error_info: str):
    """保存错误日志到文件"""
    try:
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_dir = os.path.join(os.path.dirname(__file__), "debug")
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, f"crash_{timestamp}.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"AUTO_MAA 崩溃日志\n")
            f.write(f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Python版本: {sys.version}\n")
            f.write(f"平台: {sys.platform}\n")
            f.write(f"工作目录: {os.getcwd()}\n")
            f.write("=" * 50 + "\n")
            f.write(error_info)

        return log_file
    except:
        return None


def main():
    """主程序入口"""
    application = None

    try:
        # 创建QApplication
        application = QApplication(sys.argv)

        # 安装翻译器
        translator = FluentTranslator()
        application.installTranslator(translator)

        try:
            # 导入主窗口模块
            from app.ui.main_window import AUTO_MAA

            # 创建主窗口
            window = AUTO_MAA()
            window.show_ui("显示主窗口", if_start=True)
            window.start_up_task()

        except ImportError as e:
            error_msg = f"模块导入失败: {str(e)}"
            detailed_error = traceback.format_exc()
            log_file = save_error_log(f"{error_msg}\n\n{detailed_error}")

            if log_file:
                error_msg += f"\n\n错误日志已保存到: {log_file}"

            show_system_error("模块导入错误", error_msg, detailed_error)
            return

        except Exception as e:
            error_msg = f"主窗口创建失败: {str(e)}"
            detailed_error = traceback.format_exc()
            log_file = save_error_log(f"{error_msg}\n\n{detailed_error}")

            if log_file:
                error_msg += f"\n\n错误日志已保存到: {log_file}"

            show_system_error("窗口创建错误", error_msg, detailed_error)
            return

        # 启动事件循环
        sys.exit(application.exec())

    except Exception as e:
        error_msg = f"应用程序启动失败: {str(e)}"
        detailed_error = traceback.format_exc()
        log_file = save_error_log(f"{error_msg}\n\n{detailed_error}")

        if log_file:
            error_msg += f"\n\n错误日志已保存到: {log_file}"

        # 尝试显示错误对话框
        show_system_error("应用程序启动错误", error_msg, detailed_error)

        # 如果有应用程序实例，确保正确退出
        if application:
            try:
                application.quit()
            except:
                pass

        sys.exit(1)


def handle_exception(exc_type, exc_value, exc_traceback):
    """全局异常处理器"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    error_msg = f"未处理的异常: {exc_type.__name__}: {str(exc_value)}"
    detailed_error = "".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)
    )
    log_file = save_error_log(f"{error_msg}\n\n{detailed_error}")

    if log_file:
        error_msg += f"\n\n错误日志已保存到: {log_file}"

    show_system_error("程序异常", error_msg, detailed_error)


# 设置全局异常处理器
sys.excepthook = handle_exception


if __name__ == "__main__":

    try:
        if is_admin():
            main()
        else:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, os.path.realpath(sys.argv[0]), None, 1
            )
            sys.exit(0)
    except Exception as e:
        error_msg = f"程序启动失败: {str(e)}"
        detailed_error = traceback.format_exc()
        log_file = save_error_log(f"{error_msg}\n\n{detailed_error}")

        if log_file:
            error_msg += f"\n\n错误日志已保存到: {log_file}"

        show_system_error("启动错误", error_msg, detailed_error)
        sys.exit(1)
