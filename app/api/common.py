from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.models.common_contract import ComboBoxItem, ComboBoxOut, OutBase


OutT = TypeVar("OutT", bound=OutBase)


def error_out(
	model_cls: type[OutT],
	exc: Exception,
	*,
	message: str | None = None,
	**kwargs: object,
) -> OutT:
	return model_cls(
		code=500,
		status="error",
		message=message or f"{type(exc).__name__}: {str(exc)}",
		**kwargs,
	)


async def run_api(
	success_factory: Callable[[], Awaitable[OutT]],
	*,
	model_cls: type[OutT],
	message: str | None = None,
	**fallback_kwargs: object,
) -> OutT:
	try:
		return await success_factory()
	except Exception as exc:
		return error_out(
			model_cls,
			exc,
			message=message,
			**fallback_kwargs,
		)


__all__ = [
	"OutBase",
	"ComboBoxItem",
	"ComboBoxOut",
	"error_out",
	"run_api",
]
