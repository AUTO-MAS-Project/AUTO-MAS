project: emulator
MuMu 启动失败时在报错里附带 MuMu 诊断字段（launch_err_code / launch_err_msg / error_code / player_state），便于定位 -503 这类冷启动失败
control launch 返回 -503（mainnx connect failed）时自动重发一次启动命令，冷态下实例其实已在启动的场景不必再等一轮失败收尾
