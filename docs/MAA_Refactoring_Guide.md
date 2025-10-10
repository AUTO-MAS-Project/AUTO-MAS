# MAA.py 重构指南

## 📋 重构目标

1. **生命周期划分**: 将程序分为运行前/运行中/运行结束三个阶段
2. **模式解耦**: 完全分离自动代理和人工排查逻辑
3. **函数拆分**: 将过长函数拆分为职责单一的小函数
4. **添加注释**: 为每个方法添加清晰的文档字符串

## 🏗️ 重构后的代码结构

```python
class MaaManager:
    # ==================== 生命周期方法 ====================
    
    async def run(self):
        """主流程入口: 准备 -> 执行 -> 清理"""
        if not await self._prepare():
            return
        await self._execute()
    
    # --- 运行前准备阶段 ---
    async def _prepare(self) -> bool:
        """运行前准备"""
        
    async def _backup_maa_config(self):
        """备份MAA配置文件"""
        
    async def _prepare_user_list(self):
        """准备用户列表"""
    
    # --- 运行中执行阶段 ---
    async def _execute(self):
        """根据模式分发执行"""
        
    # --- 运行结束清理阶段 ---
    async def final_task(self, task: asyncio.Task):
        """收尾工作"""
    
    # ==================== 自动代理模式 ====================
    
    async def _run_auto_proxy(self):
        """自动代理主流程"""
        
    async def _process_user_proxy(self, user: dict):
        """处理单个用户代理"""
        
    async def _execute_proxy_modes(self, user: dict):
        """执行剿灭-日常模式循环"""
        
    async def _execute_mode_task(self, user: dict, mode: str):
        """执行单个模式任务"""
        
    async def _execute_single_attempt(self, user: dict, mode: str):
        """执行单次尝试"""
    
    # ==================== 人工排查模式 ====================
    
    async def _run_manual_check(self):
        """人工排查主流程"""
        
    async def _process_user_check(self, user: dict):
        """处理单个用户排查"""
        
    async def _execute_signin_check_loop(self, user: dict):
        """登录检查循环"""
    
    # ==================== 设置脚本模式 ====================
    
    async def _run_script_setup(self):
        """设置脚本主流程"""
    
    # ==================== 辅助方法 ====================
    
    async def _release_adb_connection(self):
        """释放ADB连接"""
        
    async def _start_emulator_if_needed(self) -> bool:
        """启动模拟器"""
        
    async def _handle_skland_signin(self, user: dict):
        """处理森空岛签到"""
```

## 📝 重构示例

### 1. 运行前准备阶段重构

**重构前** (约150行混杂在run方法中):
```python
async def run(self):
    self.current_date = datetime.now().strftime("%m-%d")
    self.curdate = Config.server_date().strftime("%Y-%m-%d")
    # ... 很多准备代码 ...
    await self.configure()
    # ... 配置检查 ...
    # ... 用户列表准备 ...
    
    # 然后才开始执行业务逻辑
```

**重构后** (清晰分离):
```python
async def run(self):
    """
    主流程入口
    
    生命周期: 准备 -> 执行 -> 清理
    """
    # 阶段1: 运行前准备
    if not await self._prepare():
        return
    
    # 阶段2: 运行中执行
    await self._execute()

async def _prepare(self) -> bool:
    """
    运行前准备阶段
    
    Returns:
        bool: 准备成功返回True, 失败返回False
    """
    # 初始化时间信息
    self.current_date = datetime.now().strftime("%m-%d")
    self.curdate = Config.server_date().strftime("%Y-%m-%d")
    self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 提取配置信息
    await self.configure()
    
    # 配置合法性检查
    self.check_result = self.check_config()
    if self.check_result != "Success!":
        logger.error(f"未通过配置检查: {self.check_result}")
        await Config.send_json(
            WebSocketMessage(
                id=self.ws_id, type="Info", data={"Error": self.check_result}
            ).model_dump()
        )
        return False

    # 备份配置文件
    await self._backup_maa_config()
    
    # 准备用户列表
    if self.mode != "设置脚本":
        await self._prepare_user_list()
    
    return True
```

### 2. 模式分离重构

**重构前** (700行代码混在一起):
```python
async def run(self):
    # ... 准备代码 ...
    
    if self.mode == "自动代理":
        # 300行自动代理逻辑
        for user in self.user_list:
            # 嵌套循环
            for mode in ["Annihilation", "Routine"]:
                # 又是嵌套循环
                for i in range(times):
                    # 大量代码
    
    elif self.mode == "人工排查":
        # 200行人工排查逻辑
        for user in self.user_list:
            # 很多代码
    
    elif self.mode == "设置脚本":
        # 设置逻辑
```

**重构后** (清晰分离):
```python
async def _execute(self):
    """根据模式分发到不同的执行流程"""
    if self.mode == "自动代理":
        await self._run_auto_proxy()
    elif self.mode == "人工排查":
        await self._run_manual_check()
    elif self.mode == "设置脚本":
        await self._run_script_setup()

# --- 自动代理模式 (完全独立) ---
async def _run_auto_proxy(self):
    """自动代理模式主流程"""
    self.if_open_emulator = True
    await self._preprocess_user_proxy_data()
    
    for self.index, user in enumerate(self.user_list):
        try:
            await self._process_user_proxy(user)
        except Exception as e:
            logger.exception(f"代理用户 {user['user_id']} 时出现异常: {e}")
            # 错误处理

# --- 人工排查模式 (完全独立) ---
async def _run_manual_check(self):
    """人工排查模式主流程"""
    logger.info("人工排查任务开始, 屏蔽静默操作")
    Config.if_ignore_silence.append(self.script_id)
    
    self.if_open_emulator = True
    
    for self.index, user in enumerate(self.user_list):
        await self._process_user_check(user)

# --- 设置脚本模式 (完全独立) ---
async def _run_script_setup(self):
    """设置脚本模式主流程"""
    await self.set_maa(self.mode)
    logger.info(f"启动MAA进程: {self.maa_exe_path}")
    await self.maa_process_manager.open_process(self.maa_exe_path, [], 0)
    
    self.wait_event.clear()
    await self.wait_event.wait()
```

### 3. 函数拆分重构

**重构前** (单个函数200+行):
```python
async def _process_user_proxy(self, user):
    # 检查代理次数
    # 初始化状态
    # 森空岛签到
    # 剿灭模式循环
        # 日常模式循环
            # 重试循环
                # 配置MAA
                # 启动模拟器
                # 启动MAA
                # 监控日志
                # 处理结果
                # 清理资源
                # 保存日志
                # 处理更新
    # 记录结果
    # ... 200+行代码 ...
```

**重构后** (拆分为多个小函数):
```python
async def _process_user_proxy(self, user: dict[str, str]):
    """
    处理单个用户的自动代理任务
    
    流程:
    1. 检查代理次数限制
    2. 初始化用户数据
    3. 执行森空岛签到
    4. 执行剿灭和日常模式
    5. 记录结果
    """
    self.cur_user_data = self.user_config[uuid.UUID(user["user_id"])]
    
    # 1. 检查代理次数限制
    if not await self._check_proxy_times_limit(user):
        return
    
    logger.info(f"开始代理用户: {user['user_id']}")
    
    # 2. 初始化用户数据
    if self.cur_user_data.get("Info", "Mode") == "详细":
        self.if_open_emulator = True
    self._init_user_proxy_status()
    
    # 3. 执行森空岛签到
    await self._handle_skland_signin(user)
    
    # 4. 执行剿灭和日常模式
    await self._execute_proxy_modes(user)
    
    # 5. 记录结果
    await self.result_record()

async def _check_proxy_times_limit(self, user: dict) -> bool:
    """检查用户是否超过代理次数限制"""
    # 单一职责: 只检查次数限制
    
async def _init_user_proxy_status(self):
    """初始化单个用户的代理状态记录"""
    # 单一职责: 只初始化状态
    
async def _handle_skland_signin(self, user: dict):
    """处理森空岛签到"""
    # 单一职责: 只处理签到
    
async def _execute_proxy_modes(self, user: dict):
    """执行剿灭-日常模式循环"""
    for mode in ["Annihilation", "Routine"]:
        await self._execute_mode_task(user, mode)

async def _execute_mode_task(self, user: dict, mode: str):
    """执行单个模式任务"""
    # 进一步拆分...
```

### 4. 嵌套循环拆分

**重构前** (三层嵌套):
```python
# 用户循环
for user in self.user_list:
    # 模式循环  
    for mode in ["Annihilation", "Routine"]:
        # 重试循环
        for i in range(retry_times):
            # 100+行业务逻辑
```

**重构后** (每层一个函数):
```python
# 第一层: 用户循环
for self.index, user in enumerate(self.user_list):
    await self._process_user_proxy(user)

# 第二层: 模式循环
async def _process_user_proxy(self, user):
    for mode in ["Annihilation", "Routine"]:
        await self._execute_mode_task(user, mode)

# 第三层: 重试循环
async def _execute_mode_task(self, user, mode):
    for i in range(self.script_config.get("Run", "RunTimesLimit")):
        if self.run_book[mode]:
            break
        await self._execute_single_attempt(user, mode)

# 第四层: 单次执行
async def _execute_single_attempt(self, user, mode):
    # 配置、启动、监控、处理...
```

## 🎯 重构收益

### 代码可读性提升

**重构前**:
- `run()` 方法: 700+ 行
- 最深嵌套层级: 6层
- 单个代码块: 200+ 行

**重构后**:
- `run()` 方法: 10行
- 最深嵌套层级: 2层
- 单个函数: ≤ 50行

### 可维护性提升

1. **职责明确**: 每个函数只做一件事
2. **易于测试**: 可以单独测试每个小函数
3. **易于扩展**: 添加新模式只需新增一个方法
4. **易于调试**: 问题定位更快

### 代码复用

**重构前**: ADB释放代码重复5次
**重构后**: 提取为 `_release_adb_connection()` 方法

```python
async def _release_adb_connection(self):
    """释放ADB连接 (被多处复用)"""
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
```

## 📚 注释规范

### 类级别注释
```python
class MaaManager:
    """
    MAA控制器
    
    功能:
    - 管理MAA自动化任务的完整生命周期
    - 支持三种模式: 自动代理、人工排查、设置脚本
    - 处理模拟器启动、日志监控、结果通知等
    
    生命周期:
    1. 准备阶段 (_prepare): 配置检查、用户列表准备
    2. 执行阶段 (_execute): 根据模式执行任务
    3. 清理阶段 (final_task): 资源清理、报告生成
    """
```

### 方法级别注释
```python
async def _execute_mode_task(self, user: dict[str, str], mode: str):
    """
    执行单个模式任务（剿灭或日常）
    
    Args:
        user: 用户信息字典，包含 user_id, status, name
        mode: 模式名称（"Annihilation"剿灭 或 "Routine"日常）
    
    流程:
    1. 检查模式是否已完成
    2. 检查剿灭模式周限制
    3. 检查详细配置文件
    4. 更新UI状态
    5. 解析任务构成
    6. 执行重试循环
    
    Raises:
        Exception: 配置文件不存在时
    """
```

### 代码块注释
```python
# ==================== 运行前准备阶段 ====================

# ==================== 自动代理模式 ====================

# ==================== 人工排查模式 ====================
```

## 🚀 实施建议

### 分步重构策略

1. **第一步**: 提取运行前准备代码
   - 创建 `_prepare()` 方法
   - 创建 `_backup_maa_config()` 等辅助方法

2. **第二步**: 分离三种模式
   - 创建 `_run_auto_proxy()`
   - 创建 `_run_manual_check()`
   - 创建 `_run_script_setup()`

3. **第三步**: 拆分自动代理模式
   - 逐层拆分嵌套循环
   - 提取通用方法（ADB释放、模拟器启动等）

4. **第四步**: 拆分人工排查模式
   - 提取登录检查循环
   - 提取确认方法

5. **第五步**: 完善清理阶段
   - 重构 `final_task()`
   - 分离报告生成逻辑

### 测试策略

每完成一步重构后:
1. 运行程序确保功能正常
2. 检查日志输出是否符合预期
3. 测试异常情况处理

## 📖 完整示例: 森空岛签到重构

**重构前** (混在主流程中，60行):
```python
# 在 run() 方法中
if self.cur_user_data.get("Info", "IfSkland") and self.cur_user_data.get("Info", "SklandToken"):
    if self.cur_user_data.get("Data", "LastSklandDate") != datetime.now().strftime("%Y-%m-%d"):
        await Config.send_json(...)
        skland_result = await skland_sign_in(...)
        for type, user_list in skland_result.items():
            # 很多推送逻辑...
        if skland_result["总计"] == 0:
            # 失败处理...
        if skland_result["总计"] > 0 and len(skland_result["失败"]) == 0:
            # 成功处理...
elif self.cur_user_data.get("Info", "IfSkland"):
    # 未配置Token处理...
```

**重构后** (独立方法，清晰易读):
```python
async def _handle_skland_signin(self, user: dict[str, str]):
    """
    处理森空岛签到
    
    执行条件:
    - 用户启用森空岛签到
    - 配置了Token
    - 今天尚未签到
    
    Args:
        user: 用户信息字典
    """
    # 未启用森空岛签到
    if not self.cur_user_data.get("Info", "IfSkland"):
        return
    
    # 未配置Token
    if not self.cur_user_data.get("Info", "SklandToken"):
        await self._warn_skland_token_missing(user)
        return
    
    # 今天已经签到过
    if self.cur_user_data.get("Data", "LastSklandDate") == datetime.now().strftime("%Y-%m-%d"):
        return
    
    # 执行签到
    await self._do_skland_signin(user)

async def _warn_skland_token_missing(self, user: dict):
    """警告用户未配置森空岛Token"""
    logger.warning(f"用户: {user['user_id']} - 未配置森空岛签到Token")
    await Config.send_json(
        WebSocketMessage(
            id=self.ws_id,
            type="Info",
            data={"Warning": f"用户 {user['name']} 未配置森空岛签到Token"},
        ).model_dump()
    )

async def _do_skland_signin(self, user: dict):
    """执行森空岛签到并推送结果"""
    await Config.send_json(
        WebSocketMessage(
            id=self.ws_id,
            type="Update",
            data={"log": "正在执行森空岛签到中\n请稍候~"},
        ).model_dump()
    )
    
    skland_result = await skland_sign_in(
        self.cur_user_data.get("Info", "SklandToken")
    )
    
    await self._push_skland_result(user, skland_result)
    await self._update_skland_date_if_success(skland_result)
```

## 🎓 总结

重构的核心原则:
1. **单一职责**: 每个函数只做一件事
2. **清晰命名**: 函数名清楚描述其功能
3. **适当长度**: 单个函数不超过50行
4. **降低嵌套**: 嵌套层级不超过3层
5. **充分注释**: 每个方法都有清晰的文档字符串

这样的代码更容易:
- ✅ 阅读理解
- ✅ 维护修改
- ✅ 测试调试
- ✅ 团队协作
