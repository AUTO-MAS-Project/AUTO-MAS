# 模拟器路径自动搜索功能

## 功能概述

当用户更新模拟器配置时,如果修改了模拟器路径,系统会自动搜索上下文件夹,智能定位到模拟器主程序所在的根目录。

**新增功能**: 系统现在支持解析 Windows 快捷方式 (`.lnk` 文件)。如果用户选择了快捷方式文件,系统会自动解析获取真实目标路径,然后再进行根目录搜索。

这个功能可以帮助用户即使选择了子目录、可执行文件或快捷方式,也能自动调整到正确的模拟器安装目录。

## 使用场景

### 场景 1: 用户选择了子目录
- **输入**: `C:\MuMu Player 12\shell`
- **自动调整为**: `C:\MuMu Player 12`
- **原因**: 系统检测到父目录包含更完整的模拟器文件

### 场景 2: 用户选择了可执行文件
- **输入**: `C:\MuMu Player 12\shell\MuMuManager.exe`
- **自动调整为**: `C:\MuMu Player 12`
- **原因**: 系统自动从文件路径提取并搜索正确的根目录

### 场景 3: 用户从深层子目录选择
- **输入**: `C:\LDPlayer4.0\vms\leidian0\config`
- **自动调整为**: `C:\LDPlayer4.0`
- **原因**: 系统向上搜索找到包含模拟器可执行文件的根目录

### 场景 4: 用户选择了快捷方式 ⭐ 新功能
- **输入**: `C:\Users\用户名\Desktop\MuMu模拟器.lnk`
- **解析为**: `C:\Program Files\MuMu Player 12\MuMuPlayer.exe`
- **最终调整为**: `C:\Program Files\MuMu Player 12`
- **原因**: 系统先解析快捷方式获取真实路径,再搜索根目录

### 场景 5: 用户已选择正确路径
- **输入**: `C:\MuMu Player 12`
- **保持不变**: `C:\MuMu Player 12`
- **原因**: 路径已经是正确的根目录,无需调整

## 工作原理

### 快捷方式解析 ⭐ 新功能

在进行路径搜索前,系统会首先检测输入路径是否为 Windows 快捷方式 (`.lnk` 文件):

1. **检测快捷方式**: 如果文件扩展名为 `.lnk`
2. **解析目标路径**: 
   - 优先使用 `pywin32` 库 (`win32com.client`) 解析
   - 如果未安装 `pywin32`,则使用 PowerShell 作为备用方法
3. **验证目标**: 检查解析后的目标路径是否存在
4. **继续处理**: 使用解析后的真实路径进行后续的根目录搜索

### 搜索策略

1. **向上搜索**: 从输入路径开始,逐级向上检查父目录(最多5级)
2. **验证标准**: 检查目录是否包含模拟器特定的可执行文件
3. **智能选择**: 
   - 优先选择直接包含**更多**可执行文件的目录
   - 其次选择子目录中包含更多可执行文件的目录
   - 最后考虑路径深度,选择更接近输入路径的目录

### 支持的模拟器类型

- **MuMu模拟器** (`mumu`)
  - 关键文件: `MuMuManager.exe`, `MuMuPlayer.exe`
  
- **雷电模拟器** (`ldplayer`)
  - 关键文件: `LDPlayer.exe`, `dnplayer.exe`
  
- **夜神模拟器** (`nox`)
  - 关键文件: `Nox.exe`, `NoxVMHandle.exe`
  
- **逍遥模拟器** (`memu`)
  - 关键文件: `MEmu.exe`, `MemuManager.exe`
  
- **BlueStacks** (`bluestacks`)
  - 关键文件: `BlueStacks.exe`, `HD-Player.exe`

## API 集成

### 更新模拟器配置时自动调整路径

在 `/api/setting/emulator/update` 接口中,当 `Info.Path` 字段被修改时:

```python
# 请求示例
POST /api/setting/emulator/update
{
    "emulatorId": "uuid-string",
    "data": {
        "Info": {
            "Path": "C:\\MuMu Player 12\\shell"  // 用户选择的路径
        }
    }
}

# 系统会自动将路径调整为: "C:\\MuMu Player 12"
```

### 日志输出

系统会记录路径搜索和调整的详细信息:

```
[INFO] 检测到快捷方式文件: C:\Users\用户名\Desktop\MuMu模拟器.lnk
[INFO] 解析快捷方式: C:\Users\用户名\Desktop\MuMu模拟器.lnk -> C:\Program Files\MuMu Player 12\MuMuPlayer.exe
[INFO] 检测到路径修改: C:\Program Files\MuMu Player 12\MuMuPlayer.exe, 模拟器类型: mumu
[INFO] 开始搜索MuMu模拟器根目录,起始路径: C:\Program Files\MuMu Player 12
[DEBUG] 当前目录有效: C:\Program Files\MuMu Player 12
[INFO] 找到模拟器根目录 (直接包含1个exe,子目录1个): C:\Program Files\MuMu Player 12
[INFO] 路径已自动调整: C:\Program Files\MuMu Player 12\MuMuPlayer.exe -> C:\Program Files\MuMu Player 12
```

## 实现细节

### 核心函数

#### `resolve_lnk_path(lnk_path)` ⭐ 新增

**功能**: 解析 Windows 快捷方式文件

**参数**:
- `lnk_path`: 快捷方式文件路径

**返回值**:
- 快捷方式指向的目标路径,如果解析失败则返回原路径

**解析方法**:
1. **主方法**: 使用 `win32com.client` (需要 pywin32 库)
2. **备用方法**: 使用 PowerShell 脚本解析

**使用示例**:
```python
from app.utils.emulator import resolve_lnk_path

# 解析快捷方式
target = resolve_lnk_path("C:\\Users\\用户名\\Desktop\\MuMu模拟器.lnk")
# 返回: "C:\\Program Files\\MuMu Player 12\\MuMuPlayer.exe"
```

#### `find_emulator_root_path(input_path, emulator_type, max_levels=5)`

**参数**:
- `input_path`: 用户输入的路径(可能是文件、快捷方式或目录)
- `emulator_type`: 模拟器类型 (`mumu`, `ldplayer`, `nox`, 等)
- `max_levels`: 向上搜索的最大层级数(默认5层)

**返回值**:
- 找到的模拟器根目录路径,如果未找到则返回原路径

**使用示例**:
```python
from app.utils.emulator import find_emulator_root_path

# 从快捷方式搜索
root_path = await find_emulator_root_path(
    "C:\\Users\\用户名\\Desktop\\MuMu模拟器.lnk", 
    "mumu"
)
# 返回: "C:\\Program Files\\MuMu Player 12"

# 从子目录搜索
root_path = await find_emulator_root_path(
    "C:\\MuMu Player 12\\shell", 
    "mumu"
)
# 返回: "C:\\MuMu Player 12"
```

### 评分机制

系统为每个候选目录计算评分:

```python
{
    'path': Path对象,
    'direct_count': 直接包含的可执行文件数量,
    'subfolder_count': 子目录中的可执行文件数量,
    'depth': 路径深度(层级数)
}
```

**排序规则**:
1. 直接包含的可执行文件数量(越多越好)
2. 子目录包含的可执行文件数量(越多越好)
3. 路径深度的相反数(越深越好,即越接近输入路径)

## 配置位置

- **核心实现**: `app/utils/emulator/tools.py`
- **配置管理集成**: `app/core/config.py` - `update_emulator()` 方法
- **API 端点**: `app/api/setting.py` - `/api/setting/emulator/update`
- **模拟器常量配置**: `app/utils/constants.py` - `EMULATOR_PATH_BOOK`

## 测试

运行测试脚本验证功能:

```bash
python test\utils\test_path_search_standalone.py
```

测试覆盖场景:
- ✓ MuMu模拟器 - 从shell子目录查找
- ✓ MuMu模拟器 - 从exe文件路径查找
- ✓ MuMu模拟器 - 已经是根目录
- ✓ 雷电模拟器 - 从深层子目录查找

## 注意事项

1. **权限问题**: 如果某些目录无法访问(PermissionError),系统会跳过这些目录
2. **路径有效性**: 输入的路径必须存在,否则返回原路径
3. **模拟器类型**: 必须提供正确的模拟器类型,否则无法识别应该查找哪些文件
4. **搜索深度**: 默认向上搜索5层,如果超出这个范围可能找不到根目录
5. **快捷方式解析**: 
   - 优先使用 `pywin32` 库,如果未安装会自动降级为 PowerShell 方法
   - PowerShell 方法可能稍慢,但无需额外依赖
   - 快捷方式目标必须存在,否则返回原路径

## 依赖项

### 可选依赖

- **pywin32** (推荐): 提供更快速的快捷方式解析
  ```bash
  pip install pywin32
  ```
  
- **PowerShell** (系统自带): 作为快捷方式解析的备用方法,Windows 系统默认包含

## 未来改进

- [ ] 支持用户自定义搜索深度
- [ ] 添加更多模拟器类型支持
- [ ] 提供路径验证失败时的用户友好提示
- [ ] 缓存已验证的路径以提高性能

## 相关文档

- [模拟器管理工具](./MAA_Quick_Guide.md)
- [配置管理说明](./Backend_Task_Scheduling_and_WebSocket_Messages.md)
