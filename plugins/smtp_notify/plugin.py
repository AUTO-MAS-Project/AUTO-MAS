import json
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, List


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _get_event_list(config: Dict[str, Any]) -> List[str]:
    raw = config.get("events", ["script.success"])
    if isinstance(raw, list):
        result = [str(item).strip() for item in raw if str(item).strip()]
        return result or ["script.success"]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return ["script.success"]


def _build_mail_content(config: Dict[str, Any], event_name: str, payload: Any) -> str:
    lines: List[str] = []
    base_message = str(config.get("message", "任务状态已更新"))
    lines.append(base_message)
    lines.append("")
    lines.append(f"事件: {event_name}")

    if _to_bool(config.get("include_payload", True), True):
        lines.append("")
        lines.append("Payload:")
        try:
            lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception:
            lines.append(str(payload))

    return "\n".join(lines)


def _send_mail(config: Dict[str, Any], event_name: str, payload: Any, logger) -> None:
    smtp_host = str(config.get("smtp_host", "")).strip()
    smtp_port = _to_int(config.get("smtp_port", 587), 587)
    smtp_username = str(config.get("smtp_username", "")).strip()
    smtp_password = str(config.get("smtp_password", ""))
    smtp_use_ssl = _to_bool(config.get("smtp_use_ssl", False), False)
    smtp_use_starttls = _to_bool(config.get("smtp_use_starttls", True), True)
    sender_email = str(config.get("sender_email", "")).strip() or smtp_username
    target_email = str(config.get("target_email", "")).strip()
    subject = str(config.get("subject", "AUTO-MAS 通知"))
    timeout_seconds = _to_int(config.get("timeout_seconds", 15), 15)

    if not smtp_host:
        raise ValueError("smtp_host 不能为空")
    if not target_email:
        raise ValueError("target_email 不能为空")
    if not sender_email:
        raise ValueError("sender_email 不能为空，且未提供 smtp_username")

    body = _build_mail_content(config, event_name, payload)

    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = target_email
    msg["Subject"] = subject
    msg.set_content(body)

    if smtp_use_ssl:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout_seconds)
    else:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=timeout_seconds)

    try:
        if not smtp_use_ssl and smtp_use_starttls:
            server.starttls()

        if smtp_username and smtp_password:
            server.login(smtp_username, smtp_password)

        server.send_message(msg)
        logger.info(f"SMTP 邮件发送成功: event={event_name}, to={target_email}")
    finally:
        server.quit()


def setup(ctx):
    """SMTP 通知插件入口。"""
    config = ctx.config or {}
    events = _get_event_list(config)
    callbacks = []

    ctx.logger.info(f"SMTP 插件已启动，监听事件: {events}")

    def make_handler(event_name: str):
        def handler(payload: Any) -> None:
            if not _to_bool(config.get("enable", True), True):
                return
            try:
                _send_mail(config, event_name, payload, ctx.logger)
            except Exception as e:
                ctx.logger.error(f"SMTP 邮件发送失败: event={event_name}, error={e}")

        return handler

    for event_name in events:
        callback = make_handler(event_name)
        callbacks.append((event_name, callback))
        ctx.events.on(event_name, callback)

    def dispose():
        for event_name, callback in callbacks:
            ctx.events.off(event_name, callback)
        ctx.logger.info("SMTP 插件已关闭")

    return dispose
