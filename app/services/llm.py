#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""
LLM 服务模块

本模块负责与 LLM API 进行通信，分析任务日志并返回判定结果。
"""

import json
import asyncio
import time
from typing import Any, Dict, Optional
from dataclasses import dataclass

import httpx

from app.models.task import TaskJudgmentResult
from app.models.config import LLMProviderConfig
from app.core.llm_config import get_llm_config_manager, PRESET_PROVIDERS
from app.utils import get_logger

logger = get_logger("LLM服务")


# 速率限制追踪
@dataclass
class RateLimitTracker:
    """速率限制追踪器"""
    last_request_time: float = 0.0
    request_count: int = 0
    window_start: float = 0.0


class LLMService:
    """LLM 服务类"""
    
    PRESET_PROVIDERS = PRESET_PROVIDERS
    
    def __init__(self):
        """初始化 LLM 服务"""
        self._rate_limiter = RateLimitTracker()
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=60.0)
        return self._http_client
    
    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def analyze_log(
        self,
        log_content: str,
        task_context: Dict[str, Any],
        traditional_result: str
    ) -> TaskJudgmentResult:
        """分析日志内容并返回判定结果"""
        logger.info("开始 LLM 日志分析")
        
        try:
            # 获取配置管理器
            config_manager = await get_llm_config_manager()
            
            # 检查 LLM 功能是否启用
            if not config_manager.is_enabled():
                logger.debug("LLM 功能未启用，返回传统判定结果")
                return TaskJudgmentResult(
                    status=traditional_result,
                    reason="LLM 功能未启用",
                    judged_by_llm=False
                )
            
            # 获取当前激活的提供商配置
            provider_config = await config_manager.get_active_provider()
            if provider_config is None:
                logger.warning("未配置激活的 LLM 提供商，返回传统判定结果")
                return TaskJudgmentResult(
                    status=traditional_result,
                    reason="未配置激活的 LLM 提供商",
                    judged_by_llm=False
                )
            
            # 获取全局设置
            global_settings = await config_manager.get_global_settings()
            timeout = global_settings.get("timeout", 30)
            max_retries = global_settings.get("max_retries", 1)
            rate_limit = global_settings.get("rate_limit", 10)
            
            # 检查速率限制
            if not await self._check_rate_limit(rate_limit):
                logger.warning("已达到速率限制，返回传统判定结果")
                return TaskJudgmentResult(
                    status=traditional_result,
                    reason="已达到 LLM API 速率限制",
                    judged_by_llm=False
                )
            
            # 获取提供商信息
            provider_name = provider_config.get("Info", "Name")
            model_name = provider_config.get("Data", "Model")
            max_tokens = provider_config.get("Data", "MaxTokens")
            
            # 智能截断日志
            truncated_log = self._truncate_log(log_content, max_tokens)
            
            # 构建提示词
            prompt = self._build_prompt(truncated_log, task_context, traditional_result)
            
            # 调用 LLM API（带重试）
            response = None
            last_error = None
            
            for attempt in range(max_retries + 1):
                try:
                    response = await asyncio.wait_for(
                        self._call_llm_api(provider_config, prompt),
                        timeout=timeout
                    )
                    break
                except asyncio.TimeoutError:
                    last_error = "API 调用超时"
                    logger.warning(f"LLM API 调用超时 (尝试 {attempt + 1}/{max_retries + 1})")
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"LLM API 调用失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                
                if attempt < max_retries:
                    await asyncio.sleep(1)  # 重试前等待
            
            # API 调用失败时回退到传统判定结果
            if response is None:
                logger.error(f"LLM API 调用失败，回退到传统判定: {last_error}")
                return TaskJudgmentResult(
                    status=traditional_result,
                    reason=f"LLM API 调用失败: {last_error}",
                    judged_by_llm=False
                )
            
            # 解析响应
            result = self._parse_response(response, provider_name, model_name)
            
            logger.info(f"LLM 判定完成: {result.status}")
            return result
            
        except Exception as e:
            logger.error(f"LLM 分析过程出错: {e}")
            return TaskJudgmentResult(
                status=traditional_result,
                reason=f"LLM 分析出错: {str(e)}",
                judged_by_llm=False
            )

    def _build_prompt(
        self,
        log_content: str,
        task_context: Dict[str, Any],
        traditional_result: str
    ) -> str:
        """构建提示词"""
        # 提取任务上下文信息
        task_name = task_context.get("task_name", "未知任务")
        user_name = task_context.get("user_name", "未知用户")
        script_name = task_context.get("script_name", "未知脚本")
        script_type = task_context.get("script_type", "unknown")
        
        # 构建系统提示词
        system_prompt = """你是一个专业的任务日志分析助手。你的任务是分析自动化脚本的执行日志，判断任务是否成功完成。

## 分析规则

1. **成功判定**：如果日志显示任务已正常完成（如出现"完成"、"成功"、"finished"、"completed"等关键词，或任务流程正常结束），判定为成功。

2. **运行中判定**：如果日志显示任务仍在正常执行中（如正在处理、等待中、进行中等），判定为运行中。

3. **失败判定**：如果日志明确显示错误、异常、崩溃或任务无法继续，判定为失败并说明原因。

## 特别注意

- 日志格式可能因软件版本更新而变化，不要仅依赖特定关键词
- 关注日志的整体语义和任务流程
- 如果日志显示任务实际已完成但格式与预期不同，仍应判定为成功
- 部分完成的任务如果主要目标已达成，可以判定为成功

## 输出格式

你必须以 JSON 格式输出，包含以下字段：
- status: 判定状态，必须是以下三种之一：
  - "Success!" 表示任务成功完成
  - "[脚本名称]正常运行中" 表示任务仍在运行
  - 具体的错误描述（如"连接超时"、"登录失败"等）表示任务失败
- reason: 判定理由，简要说明为何做出此判定

示例输出：
{"status": "Success!", "reason": "日志显示所有任务已完成，虽然格式与预期不同，但任务实际已成功执行"}
{"status": "MAA正常运行中", "reason": "日志显示任务正在执行基建换班操作"}
{"status": "ADB连接失败", "reason": "日志显示无法连接到模拟器，ADB连接超时"}"""

        # 构建用户提示词
        user_prompt = f"""## 任务信息

- 任务名称: {task_name}
- 用户名称: {user_name}
- 脚本名称: {script_name}
- 脚本类型: {script_type}
- 传统判定结果: {traditional_result}

## 日志内容

```
{log_content}
```

请分析以上日志内容，判断任务的实际执行状态。注意：传统判定结果可能因日志格式变化而不准确，请根据日志的实际内容进行判断。"""

        return f"{system_prompt}\n\n{user_prompt}"

    async def _call_llm_api(
        self,
        provider_config: LLMProviderConfig,
        prompt: str
    ) -> Dict[str, Any]:
        """调用 LLM API"""
        # 获取配置
        provider_type = provider_config.get("Info", "Type")
        api_key = provider_config.get("Data", "ApiKey")
        base_url = provider_config.get("Data", "BaseUrl")
        model = provider_config.get("Data", "Model")
        max_tokens = provider_config.get("Data", "MaxTokens")
        temperature = provider_config.get("Data", "Temperature")
        
        # 如果是预设提供商且未设置 base_url，使用预设值
        if provider_type in self.PRESET_PROVIDERS and not base_url:
            preset = self.PRESET_PROVIDERS[provider_type]
            base_url = preset["base_url"]
            if not model:
                model = preset["model"]
        
        # 验证必要参数
        if not api_key:
            raise ValueError("API 密钥未配置")
        if not base_url:
            raise ValueError("Base URL 未配置")
        if not model:
            raise ValueError("模型名称未配置")
        
        # 根据提供商类型调用不同的 API
        if provider_type == "claude":
            return await self._call_claude_api(
                api_key, base_url, model, prompt, max_tokens, temperature
            )
        else:
            # OpenAI 兼容 API（包括 OpenAI、DeepSeek、Qwen、MiMo 和自定义）
            return await self._call_openai_compatible_api(
                api_key, base_url, model, prompt, max_tokens, temperature
            )
    
    async def _call_openai_compatible_api(
        self,
        api_key: str,
        base_url: str,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """调用 OpenAI 兼容 API"""
        # 确保 base_url 格式正确
        if not base_url.endswith("/"):
            base_url = base_url + "/"
        
        url = f"{base_url}chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 分离系统提示词和用户提示词
        parts = prompt.split("\n\n", 1)
        if len(parts) == 2:
            system_content = parts[0]
            user_content = parts[1]
        else:
            system_content = ""
            user_content = prompt
        
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"}
        }
        
        client = await self._get_http_client()
        response = await client.post(url, headers=headers, json=data)
        
        if response.status_code != 200:
            error_text = response.text
            if response.status_code == 401:
                raise ValueError(f"API 密钥无效或已过期: {error_text}")
            elif response.status_code == 429:
                raise ValueError(f"API 速率限制: {error_text}")
            else:
                raise Exception(f"API 调用失败 (HTTP {response.status_code}): {error_text}")
        
        return response.json()

    async def _call_claude_api(
        self,
        api_key: str,
        base_url: str,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float
    ) -> Dict[str, Any]:
        """调用 Claude API"""
        # 确保 base_url 格式正确
        if not base_url.endswith("/"):
            base_url = base_url + "/"
        
        url = f"{base_url}messages"
        
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        # 分离系统提示词和用户提示词
        parts = prompt.split("\n\n", 1)
        if len(parts) == 2:
            system_content = parts[0]
            user_content = parts[1]
        else:
            system_content = ""
            user_content = prompt
        
        data = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_content,
            "messages": [
                {"role": "user", "content": user_content}
            ]
        }
        
        client = await self._get_http_client()
        response = await client.post(url, headers=headers, json=data)
        
        if response.status_code != 200:
            error_text = response.text
            if response.status_code == 401:
                raise ValueError(f"API 密钥无效或已过期: {error_text}")
            elif response.status_code == 429:
                raise ValueError(f"API 速率限制: {error_text}")
            else:
                raise Exception(f"API 调用失败 (HTTP {response.status_code}): {error_text}")
        
        # 转换 Claude 响应为 OpenAI 兼容格式
        claude_response = response.json()
        
        # 提取文本内容
        content = ""
        if "content" in claude_response and len(claude_response["content"]) > 0:
            content = claude_response["content"][0].get("text", "")
        
        # 转换为 OpenAI 兼容格式
        return {
            "choices": [
                {
                    "message": {
                        "content": content
                    }
                }
            ],
            "usage": {
                "prompt_tokens": claude_response.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": claude_response.get("usage", {}).get("output_tokens", 0),
                "total_tokens": (
                    claude_response.get("usage", {}).get("input_tokens", 0) +
                    claude_response.get("usage", {}).get("output_tokens", 0)
                )
            }
        }

    def _parse_response(
        self,
        response: Dict[str, Any],
        provider_name: str,
        model_name: str
    ) -> TaskJudgmentResult:
        """解析 LLM 响应"""
        try:
            # 提取响应内容
            content = ""
            if "choices" in response and len(response["choices"]) > 0:
                message = response["choices"][0].get("message", {})
                content = message.get("content", "")
            
            if not content:
                logger.warning("LLM 响应内容为空")
                return TaskJudgmentResult(
                    status="响应解析失败",
                    reason="LLM 响应内容为空",
                    judged_by_llm=True,
                    provider_name=provider_name,
                    model_name=model_name
                )
            
            # 尝试解析 JSON
            try:
                # 清理可能的 markdown 代码块标记
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                result_data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"LLM 响应 JSON 解析失败: {e}")
                # 尝试从文本中提取信息
                return self._parse_text_response(content, provider_name, model_name)
            
            # 提取状态和理由
            status = result_data.get("status", "")
            reason = result_data.get("reason", "")
            
            if not status:
                logger.warning("LLM 响应中缺少 status 字段")
                return TaskJudgmentResult(
                    status="响应格式错误",
                    reason="LLM 响应中缺少 status 字段",
                    judged_by_llm=True,
                    provider_name=provider_name,
                    model_name=model_name
                )
            
            return TaskJudgmentResult(
                status=status,
                reason=reason,
                judged_by_llm=True,
                provider_name=provider_name,
                model_name=model_name
            )
            
        except Exception as e:
            logger.error(f"解析 LLM 响应时出错: {e}")
            return TaskJudgmentResult(
                status="响应解析失败",
                reason=f"解析错误: {str(e)}",
                judged_by_llm=True,
                provider_name=provider_name,
                model_name=model_name
            )
    
    def _parse_text_response(
        self,
        content: str,
        provider_name: str,
        model_name: str
    ) -> TaskJudgmentResult:
        """从文本响应中提取判定结果（当 JSON 解析失败时的备用方案）"""
        content_lower = content.lower()
        
        # 尝试识别成功状态
        success_keywords = ["success", "成功", "完成", "finished", "completed"]
        for keyword in success_keywords:
            if keyword in content_lower:
                return TaskJudgmentResult(
                    status="Success!",
                    reason=content[:200],  # 截取前200字符作为理由
                    judged_by_llm=True,
                    provider_name=provider_name,
                    model_name=model_name
                )
        
        # 尝试识别运行中状态
        running_keywords = ["运行中", "running", "进行中", "processing", "执行中"]
        for keyword in running_keywords:
            if keyword in content_lower:
                return TaskJudgmentResult(
                    status="任务正常运行中",
                    reason=content[:200],
                    judged_by_llm=True,
                    provider_name=provider_name,
                    model_name=model_name
                )
        
        # 默认返回失败状态
        return TaskJudgmentResult(
            status="任务状态不明确",
            reason=content[:200],
            judged_by_llm=True,
            provider_name=provider_name,
            model_name=model_name
        )

    def _truncate_log(self, log_content: str, max_tokens: int) -> str:
        """智能截断日志内容"""
        # 估算 token 数（粗略估计：1 token ≈ 4 字符对于英文，≈ 1.5 字符对于中文）
        # 使用保守估计：1 token ≈ 2 字符
        estimated_chars_per_token = 2
        
        # 预留一些 token 给提示词和响应
        reserved_tokens = 500
        available_tokens = max(max_tokens - reserved_tokens, 500)
        max_chars = available_tokens * estimated_chars_per_token
        
        # 如果日志内容在限制内，直接返回
        if len(log_content) <= max_chars:
            return log_content
        
        # 按行分割日志
        lines = log_content.split("\n")
        
        # 保留最近的日志行（从末尾开始）
        truncated_lines = []
        current_chars = 0
        
        # 添加截断提示
        truncation_notice = "[... 日志已截断，仅显示最近的内容 ...]\n"
        current_chars += len(truncation_notice)
        
        # 从最后一行开始向前添加
        for line in reversed(lines):
            line_chars = len(line) + 1  # +1 for newline
            if current_chars + line_chars > max_chars:
                break
            truncated_lines.insert(0, line)
            current_chars += line_chars
        
        # 如果没有任何行能被添加，至少保留最后一行的部分内容
        if not truncated_lines and lines:
            last_line = lines[-1]
            remaining_chars = max_chars - len(truncation_notice)
            if remaining_chars > 0:
                truncated_lines.append(last_line[-remaining_chars:])
        
        return truncation_notice + "\n".join(truncated_lines)
    
    async def _check_rate_limit(self, rate_limit: int) -> bool:
        """检查速率限制"""
        current_time = time.time()
        window_duration = 60.0  # 1 分钟窗口
        
        # 检查是否需要重置窗口
        if current_time - self._rate_limiter.window_start >= window_duration:
            self._rate_limiter.window_start = current_time
            self._rate_limiter.request_count = 0
        
        # 检查是否超过限制
        if self._rate_limiter.request_count >= rate_limit:
            return False
        
        # 更新计数
        self._rate_limiter.request_count += 1
        self._rate_limiter.last_request_time = current_time
        
        return True
    
    async def test_connection(
        self,
        provider_config: LLMProviderConfig
    ) -> Dict[str, Any]:
        """测试 LLM 提供商连接"""
        logger.info("测试 LLM 提供商连接")
        
        start_time = time.time()
        
        try:
            # 构建简单的测试提示词
            test_prompt = """请回复一个简单的 JSON 对象来确认连接正常。

输出格式：
{"status": "ok", "message": "连接成功"}"""
            
            response = await asyncio.wait_for(
                self._call_llm_api(provider_config, test_prompt),
                timeout=30
            )
            
            response_time = time.time() - start_time
            
            # 验证响应
            if "choices" in response and len(response["choices"]) > 0:
                return {
                    "success": True,
                    "message": "连接测试成功",
                    "response_time": round(response_time, 2),
                    "model": provider_config.get("Data", "Model")
                }
            else:
                return {
                    "success": False,
                    "message": "响应格式异常",
                    "response_time": round(response_time, 2)
                }
                
        except asyncio.TimeoutError:
            return {
                "success": False,
                "message": "连接超时",
                "response_time": 30.0
            }
        except ValueError as e:
            return {
                "success": False,
                "message": str(e),
                "response_time": time.time() - start_time
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"连接失败: {str(e)}",
                "response_time": time.time() - start_time
            }


# 全局 LLM 服务实例
_llm_service: Optional[LLMService] = None


async def get_llm_service() -> LLMService:
    """获取全局 LLM 服务实例"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
