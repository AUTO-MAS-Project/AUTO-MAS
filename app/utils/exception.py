class OCRException(Exception):
    """OCR错误的基本异常。"""
    pass

class WindowsNotFoundException(OCRException):
    """未找到指定窗口时引发的异常。"""
    pass

class WindowsNotFocusException(OCRException):
    """指定窗口未获得焦点时引发的异常。"""
    pass

class OCRNotFoundTitleException(OCRException):
    """未设定cls.title且未指定形参指定标题时引发的异常。"""
    pass

class ADBException(OCRException):
    """ADB操作相关的基本异常。"""
    pass

class ADBFileNotFoundException(ADBException):
    """ADB可执行文件不存在时引发的异常。"""
    pass

class ADBCommandFailedException(ADBException):
    """ADB命令执行失败时引发的异常。"""
    pass

class ADBDeviceNotFoundException(ADBException):
    """ADB设备未找到或无法连接时引发的异常。"""
    pass

class ADBConnectionFailedException(ADBException):
    """ADB设备连接失败时引发的异常。"""
    pass

class ADBTimeoutException(ADBException):
    """ADB命令执行超时时引发的异常。"""
    pass

class ADBScreenshotException(ADBException):
    """ADB截图失败时引发的异常。"""
    pass

class ImageProcessException(OCRException):
    """图像处理相关的异常。"""
    pass
