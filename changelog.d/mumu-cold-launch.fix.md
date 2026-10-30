project: emulator
MuMu 启动失败时在报错里附带 MuMu 诊断字段（launch_err_code / launch_err_msg / error_code / player_state），便于定位 -503 这类冷启动失败
control launch 返回 -503（mainnx connect failed）时按 1/3/10/30/60 秒退避重发，最多 6 次；重发受最大等待时间约束，预算不足时提前放弃，避免开机冷态下实例已在启动却被判失败
