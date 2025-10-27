class OCRException(Exception):
    """OCR错误的基本异常。"""
    pass

class WindowsNotFoundException(OCRException):
    """未找到指定窗口时引发的异常。"""
    pass

class WindowsNotFocusException(OCRException):
    """指定窗口未获得焦点时引发的异常。"""
    pass