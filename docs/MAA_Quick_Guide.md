# MAA.py 代码优化快速指南

## ✅ 当前状态确认

**文件状态**: ✅ 正常，无语法错误
**文件行数**: 1979行
**最后检查**: 2025年10月7日
**验证方式**: Python编译检查通过

---

## 🎯 推荐的优化方式

### 第一步: 添加注释（最安全，最推荐）

**目标**: 提高代码可读性，不改变任何逻辑

#### 1.1 为 `run()` 方法添加分区注释

在 `async def run(self):` 方法中添加清晰的注释分隔不同阶段：

```python
async def run(self):
    """主进程, 运行MAA代理进程"""

    # ==================== 阶段1: 初始化时间信息 ====================
    self.current_date = datetime.now().strftime("%m-%d")
    self.curdate = Config.server_date().strftime("%Y-%m-%d")
    self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ==================== 阶段2: 配置提取与检查 ====================
    await self.configure()
    self.check_result = self.check_config()
    if self.check_result != "Success!":
        logger.error(f"未通过配置检查: {self.check_result}")
        await Config.send_json(
            WebSocketMessage(
                id=self.ws_id, type="Info", data={"Error": self.check_result}
            ).model_dump()
        )
        return

    # ==================== 阶段3: 备份MAA配置文件 ====================
    logger.info(f"记录 MAA 配置文件: {self.maa_set_path}")
    (Path.cwd() / f"data/{self.script_id}/Temp").mkdir(parents=True, exist_ok=True)
    if self.maa_set_path.exists():
        shutil.copy(
            self.maa_set_path, Path.cwd() / f"data/{self.script_id}/Temp/gui.json"
        )

    # ==================== 阶段4: 准备用户列表 ====================
    if self.mode != "设置脚本":
        self.user_list: list[dict[str, str]] = [
            {
                "user_id": str(uid),
                "status": "等待",
                "name": config.get("Info", "Name"),
            }
            for uid, config in self.user_config.items()
            if config.get("Info", "Status")
            and config.get("Info", "RemainedDay") != 0
        ]
        self.user_list = sorted(
            self.user_list,
            key=lambda x: (
                self.user_config[uuid.UUID(x["user_id"])].get("Info", "Mode")
            ),
        )
        logger.info(f"用户列表创建完成, 已筛选用户数: {len(self.user_list)}")

    # ==================== 阶段5: 根据模式执行任务 ====================
    
    # --- 自动代理模式 ---
    if self.mode == "自动代理":
        # 标记是否需要重启模拟器
        self.if_open_emulator = True
        
        # 预处理: 重置每日代理次数
        for _ in self.user_list:
            if (
                self.user_config[uuid.UUID(_["user_id"])].get(
                    "Data", "LastProxyDate"
                )
                != self.curdate
            ):
                await self.user_config[uuid.UUID(_["user_id"])].set(
                    "Data", "LastProxyDate", self.curdate
                )
                await self.user_config[uuid.UUID(_["user_id"])].set(
                    "Data", "ProxyTimes", 0
                )

        # 开始代理
        for self.index, user in enumerate(self.user_list):
            try:
                # ... 继续添加注释 ...
```

#### 1.2 为关键方法添加文档字符串

```python
async def configure(self):
    """
    提取配置信息并初始化各种路径和监控器
    
    执行内容:
    1. 订阅广播消息队列
    2. 锁定脚本配置（防止并发修改）
    3. 加载用户配置数据
    4. 初始化MAA相关路径（根目录、配置文件、日志文件、可执行文件）
    5. 设置ADB搜索范围
    6. 初始化日志监控器
    
    设置的关键属性:
    - self.script_config: 脚本配置对象
    - self.user_config: 用户配置集合
    - self.maa_root_path: MAA根目录
    - self.maa_set_path: MAA配置文件路径
    - self.maa_log_path: MAA日志文件路径
    - self.maa_exe_path: MAA可执行文件路径
    - self.maa_log_monitor: 日志监控器实例
    """
    # 原有代码保持不变...
```

```python
def check_config(self) -> str:
    """
    检查配置是否可用
    
    检查项:
    1. 脚本配置类型是否为MaaConfig
    2. MAA.exe文件是否存在
    3. MAA配置文件是否存在
    4. 如果是非设置脚本模式，检查全局设置是否完成
    
    Returns:
        str: "Success!" 表示检查通过，其他字符串为错误信息
    """
    # 原有代码保持不变...
```

```python
async def check_maa_log(self, log_content: list[str]) -> None:
    """
    获取MAA日志并检查以判断MAA程序运行状态
    
    功能:
    1. 更新MAA日志到前端界面
    2. 解析日志内容，识别任务完成情况
    3. 检测各种异常情况（登录失败、ADB异常、超时等）
    4. 更新self.maa_result状态
    5. 完成时释放等待锁
    
    Args:
        log_content: MAA日志内容列表，每行一个字符串
    
    日志分析逻辑:
    - 自动代理模式: 检查各任务完成状态、异常情况、超时
    - 人工排查模式: 仅检查登录成功或失败
    
    状态值:
    - "Success!": 任务成功完成
    - "Wait": 继续等待
    - 其他: 具体的错误信息
    """
    # 原有代码保持不变...
```

```python
async def set_maa(self, mode: str) -> dict:
    """
    配置MAA运行参数，动态生成gui.json配置文件
    
    Args:
        mode: 运行模式
            - "Annihilation": 剿灭模式
            - "Routine": 日常模式
            - "人工排查": 人工排查模式
            - "Update": MAA更新模式
            - 其他: 设置脚本模式
    
    Returns:
        dict: 生成的MAA配置字典
    
    配置内容:
    1. 基础设置: 时间设置、更新设置
    2. 模式特定设置: 根据mode参数配置不同的任务
    3. 用户特定设置: 根据用户配置调整关卡、基建等
    4. 模拟器设置: ADB路径、启动行为等
    
    关键配置项:
    - Start.RunDirectly: 启动后是否直接运行
    - Start.OpenEmulatorAfterLaunch: 是否自动开启模拟器
    - MainFunction.PostActions: 完成后行为（退出MAA/退出模拟器等）
    - TaskQueue.*: 各任务的启用状态
    """
    # 原有代码保持不变...
```

#### 1.3 为复杂逻辑添加行内注释

```python
# 剿灭模式: 满足条件跳过剿灭
if (
    mode == "Annihilation"
    and self.script_config.get("Run", "AnnihilationWeeklyLimit")  # 启用了周限制
    and datetime.strptime(
        self.cur_user_data.get("Data", "LastAnnihilationDate"),
        "%Y-%m-%d",
    ).isocalendar()[:2]  # 上次剿灭的年份和周数
    == datetime.strptime(
        self.curdate, "%Y-%m-%d"
    ).isocalendar()[:2]  # 当前的年份和周数
):
    # 本周已执行过剿灭，跳过
    logger.info(
        f"用户: {user['user_id']} - 本周剿灭模式已达上限, 跳过执行剿灭任务"
    )
    self.run_book[mode] = True
    continue
```

---

### 第二步: 提取简单的辅助方法（风险较低）

只提取明显重复的代码块，不改变主流程。

#### 2.1 提取ADB释放方法

**查找重复代码**: ADB释放代码在文件中出现多次

**新增方法**（添加到类的末尾）:
```python
async def _release_adb_connection(self, adb_path: Path, adb_address: str):
    """
    释放ADB连接
    
    Args:
        adb_path: ADB可执行文件路径
        adb_address: ADB连接地址
    
    Note:
        忽略CalledProcessError，因为可能本来就没有连接
    """
    try:
        logger.info(f"释放ADB: {adb_address}")
        subprocess.run(
            [adb_path, "disconnect", adb_address],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.CalledProcessError as e:
        logger.warning(f"释放ADB时出现异常: {e}")
    except Exception as e:
        logger.exception(f"释放ADB时出现异常: {e}")
        await Config.send_json(
            WebSocketMessage(
                id=self.ws_id,
                type="Info",
                data={"Error": f"释放ADB时出现异常: {e}"},
            ).model_dump()
        )
```

**替换调用点**（一次只替换一处，测试通过后再替换下一处）:
```python
# 替换前:
try:
    logger.info(f"释放ADB: {self.ADB_address}")
    subprocess.run(
        [self.ADB_path, "disconnect", self.ADB_address],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
except subprocess.CalledProcessError as e:
    logger.warning(f"释放ADB时出现异常: {e}")
except Exception as e:
    logger.exception(f"释放ADB时出现异常: {e}")
    await Config.send_json(...)

# 替换后:
await self._release_adb_connection(self.ADB_path, self.ADB_address)
```

---

### 第三步: 添加常量定义（风险很低）

在类的开头添加常量，提高代码可维护性：

```python
class MaaManager:
    """MAA控制器"""
    
    # ==================== 类常量定义 ====================
    
    # 运行模式
    MODE_AUTO_PROXY = "自动代理"
    MODE_MANUAL_CHECK = "人工排查"
    MODE_SCRIPT_SETUP = "设置脚本"
    
    # 任务模式
    TASK_MODE_ANNIHILATION = "Annihilation"  # 剿灭
    TASK_MODE_ROUTINE = "Routine"  # 日常
    
    # 服务器类型
    SERVER_OFFICIAL = "Official"  # 官服
    SERVER_BILIBILI = "Bilibili"  # B服
    
    # 用户模式
    USER_MODE_SIMPLE = "简洁"
    USER_MODE_DETAIL = "详细"
    
    # 任务状态
    STATUS_WAITING = "等待"
    STATUS_RUNNING = "运行"
    STATUS_COMPLETED = "完成"
    STATUS_ERROR = "异常"
    STATUS_SKIPPED = "跳过"
    
    # 结果状态
    RESULT_SUCCESS = "Success!"
    RESULT_WAIT = "Wait"
    
    def __init__(
        self,
        mode: maa_mode_type,
        script_id: uuid.UUID,
        user_id: uuid.UUID | None,
        ws_id: str,
    ):
        super().__init__()
        # 原有代码...
```

**使用常量替换硬编码字符串**（逐步替换，不要一次全改）:
```python
# 替换前:
if self.mode == "自动代理":

# 替换后:
if self.mode == self.MODE_AUTO_PROXY:

# 替换前:
user["status"] = "运行"

# 替换后:
user["status"] = self.STATUS_RUNNING
```

---

## ⚠️ 注意事项

### 修改前必须做的事
1. ✅ 使用Git创建新分支: `git checkout -b feature/add-comments`
2. ✅ 确保有完整的备份
3. ✅ 理解要修改的代码功能

### 修改后必须做的事
1. ✅ 运行Python语法检查: `python -m py_compile app/task/MAA.py`
2. ✅ 启动程序测试基本功能
3. ✅ 提交Git: `git add -p` 然后 `git commit -m "添加注释"`

### 绝对不要做的事
1. ❌ 一次性修改太多地方
2. ❌ 在不理解的情况下修改逻辑
3. ❌ 修改后不测试就提交
4. ❌ 删除看似"无用"的代码（可能有特殊用途）

---

## 📋 修改检查清单

每次修改完成后，检查以下项目:

- [ ] 代码没有语法错误（运行 `python -m py_compile`）
- [ ] 程序可以正常启动
- [ ] 核心功能可以正常工作
- [ ] 日志输出正常
- [ ] 已用Git提交修改
- [ ] 提交信息清晰描述了修改内容

---

## 🎯 优先级建议

### 高优先级（立即可做）⭐⭐⭐⭐⭐
1. 为 `run()` 方法添加分区注释
2. 为 `configure()`, `check_config()`, `set_maa()` 添加文档字符串
3. 为复杂的条件判断添加行内注释

### 中优先级（一周内完成）⭐⭐⭐⭐
1. 添加类常量定义
2. 提取 `_release_adb_connection()` 方法
3. 为其他主要方法添加文档字符串

### 低优先级（一个月内完成）⭐⭐⭐
1. 逐步使用常量替换硬编码字符串
2. 提取其他重复代码
3. 考虑更大范围的重构

---

## 📚 相关文档

详细的重构指南和方案已经准备好，可以作为参考：

1. **MAA_Current_Status.md** - 当前状态报告（本文档同目录）
2. **MAA_Refactoring_Guide.md** - 详细重构指南（参考用）
3. **MAA_Refactoring_Summary.md** - 完整实施方案（参考用）

---

## 💡 小贴士

1. **每天只做一点**: 不要想着一天完成所有优化
2. **频繁提交**: 每做一小部分就提交一次Git
3. **保持耐心**: 好的代码是一点点改进出来的
4. **及时测试**: 不要积累太多未测试的修改
5. **记录问题**: 遇到不理解的代码，先记录下来，不要盲目修改

---

## ✅ 总结

**当前状态**: 代码正常，可以安全运行 ✅

**推荐方案**: 
- **第一步**: 添加注释（本周完成）
- **第二步**: 提取辅助方法（下周完成）
- **第三步**: 添加常量（两周内完成）

**核心原则**: 小步迭代、频繁测试、安全第一

祝优化顺利！🎉
