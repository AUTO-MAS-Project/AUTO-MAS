"""MaaFW 失败回放：把脚本自己用过的截图留在内存环里，任务失败时写出成一段帧序列。

全局设置 ``Replay.FrameReplay`` 打开时宿主随 job 下发 ``frameReplay``。取帧不开 debug 模式，
只挂两个本来就有的回调，此刻 ``cached_image`` 正是 MaaFramework 刚用过的那一帧
（2026-10-27 用自定义控制器喂生产截图实测，节点 12/12、截图 1439/1439 对得上）：

- context sink 的 ``Node.NextList.Starting``：流水线每轮识别前；
- controller sink 的 ``screencap`` 成功：agent 自己截的图。流水线内部的截图与点击不发
  ``Controller.Action.*``，agent 的发，只挂节点事件会漏掉 MaaEnd 这类 agent 截图为主的项目。

两个回调都同步挡着 MaaFramework（每个节点回调睡 30 ms，11.4 s 的运行变 12.1 s），
回调里只复制一帧（1–2 ms）入队，PNG 编码在后台线程。不能另开线程轮询 ``cached_image``：
截图进行中读会失败，每失败一次往 maafw.log 写一行 ERR。

写出的一段是一个目录：``0000.png`` 起的帧加 ``timeline.json``（每帧的时刻、任务、节点、
识别框、动作）。宿主把它合成 WebM 挂到历史记录上（``tools/embedded/frame_replay_video``）。

本模块只用标准库与 numpy；编码与取帧由调用方传入，不碰 MaaFramework。
"""

from __future__ import annotations

import json
import shutil
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

# 环里已编码 PNG 的总字节上限。全分辨率一帧约 1 MB，约 60 帧，去重后覆盖失败前 1–2 分钟。
FRAME_REPLAY_MAX_BYTES = 64 * 1024 * 1024
# 两路取帧的最小间隔：流水线每秒最多 2 帧；agent 截图最高约 40 次/秒（MaaEnd），
# 离上一次取帧满 1 秒才补一帧。
FRAME_REPLAY_PIPELINE_INTERVAL_SECONDS = 0.5
FRAME_REPLAY_AGENT_INTERVAL_SECONDS = 1.0
# controller 事件里不是 agent 输入的动作，不记进字幕
_NON_INPUT_ACTIONS = frozenset({"connect", "inactive"})
# 等编码的原图（每张约 2.7 MB）最多积压几张，超了新帧直接丢：编码一帧约 27 ms，正常追得上。
FRAME_REPLAY_MAX_PENDING = 8
# 一次运行最多留几段（一段约 60 MB 的 PNG 临时文件），超了删最早的；宿主跨重试再收一次。
FRAME_REPLAY_MAX_SEGMENTS = 3
# 宿主在 runDeadlineAt 后再宽限 90 s 才强杀（runner_task._RUN_DEADLINE_GRACE_SECONDS）；
# worker 到这一刻还没跑完就先把环写出，强杀后宿主照样能捡到。
FRAME_REPLAY_KILL_FLUSH_SECONDS = 60.0
FRAME_REPLAY_DIR_SUFFIX = ".replay"
FRAME_REPLAY_TIMELINE = "timeline.json"
# 写出前等后台编码追平的上限
_FLUSH_DRAIN_SECONDS = 2.0
# 画面有没有变：口径同启动画面稳定判定（runner._startup_screen_changed），隔 4 像素抽样，
# 通道差超过 16 的抽样点多于 8 个算变了
_SAMPLE_STRIDE = 4
_PIXEL_DELTA = 16
_CHANGED_PIXELS = 8


@dataclass
class _Frame:
    at: float
    task: str
    node: str
    image: Any = None  # 原图，编码完清掉
    png: bytes | None = None
    dropped: bool = False
    hit: str = ""
    box: list[int] | None = None
    action: str = ""
    action_failed: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def timeline_entry(self, file: str) -> dict[str, Any]:
        return {
            "file": file,
            "at": self.at,
            "task": self.task,
            "node": self.node,
            "hit": self.hit,
            "box": self.box,
            "action": self.action,
            "actionFailed": self.action_failed,
            **self.extra,
        }


def find_frame_replay_segments(directory: Path) -> list[Path]:
    """worker 在 ``directory`` 里写出的回放段，按写出先后。"""

    segments = [
        path
        for path in directory.glob(f"*{FRAME_REPLAY_DIR_SUFFIX}")
        if (path / FRAME_REPLAY_TIMELINE).is_file()
    ]
    return sorted(segments, key=lambda path: path.stat().st_mtime)


def _sample(image: Any) -> Any:
    return image[::_SAMPLE_STRIDE, ::_SAMPLE_STRIDE].astype(np.int16)


def _changed(previous: Any, sample: Any) -> bool:
    if previous is None or previous.shape != sample.shape:
        return True
    delta = np.abs(sample - previous)
    if delta.ndim == 3:
        delta = delta.max(axis=2)
    return int((delta > _PIXEL_DELTA).sum()) > _CHANGED_PIXELS


def _box(value: Any) -> list[int] | None:
    if (
        isinstance(value, (list, tuple))
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and value[2] > 0
        and value[3] > 0
    ):
        return [int(item) for item in value]
    return None


class FrameReplayRecorder:
    """内存环 + 后台编码线程。回调线程、主线程、截止计时器线程并发调用，内部加锁。"""

    def __init__(
        self,
        encode_png: Callable[[Any], bytes],
        *,
        max_bytes: int = FRAME_REPLAY_MAX_BYTES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._encode_png = encode_png
        self._max_bytes = max_bytes
        self._clock = clock
        self._cond = threading.Condition()
        self._frames: deque[_Frame] = deque()
        self._pending: deque[_Frame] = deque()
        self._encoding = 0
        self._bytes = 0
        self._last_sample: Any = None
        self._last_grab = float("-inf")
        self._last_pipeline_grab = float("-inf")
        self._task = ""
        self._node = ""
        # 本轮流水线取到的帧、最近一张 agent 截图：之后的识别、动作记到它们上面
        self._round: _Frame | None = None
        self._agent: _Frame | None = None
        self._closed = False
        self._segments: list[Path] = []
        self._thread = threading.Thread(
            target=self._encode_loop, name="maafw-frame-replay", daemon=True
        )
        self._thread.start()

    def set_task(self, name: str) -> None:
        with self._cond:
            self._task = name
            self._node = ""
            self._round = None
            self._agent = None

    def on_node(self, message: str, details: Any, grab: Callable[[], Any]) -> None:
        """context sink 的 ``Node.*``：每轮识别前取帧，识别命中与动作记到这一帧上。"""

        if not isinstance(details, dict):
            return
        name = str(details.get("name") or "")
        if message == "Node.NextList.Starting":
            with self._cond:
                self._node = name
            frame = self._grab(grab, pipeline=True)
            with self._cond:
                self._round = frame
            return
        if message == "Node.Action.Starting":
            # Custom 动作里 agent 自己截的图挂在这个节点名下
            with self._cond:
                self._node = name
            return
        with self._cond:
            frame = self._round
            if frame is None:
                return
            if message == "Node.Recognition.Succeeded":
                reco = details.get("reco_details")
                frame.hit = name
                frame.box = _box(reco.get("box")) if isinstance(reco, dict) else None
                frame.action = ""
                frame.action_failed = False
            elif message in ("Node.Action.Succeeded", "Node.Action.Failed"):
                if frame.hit != name:
                    return
                action = details.get("action_details")
                if isinstance(action, dict) and action.get("action"):
                    frame.action = str(action["action"])
                frame.action_failed = message.endswith("Failed")

    def on_controller(
        self, action: str, *, succeeded: bool, grab: Callable[[], Any]
    ) -> None:
        """controller sink：agent 截图按限流取帧，agent 的点击、滑动、按键记到最近那张上。"""

        if action == "screencap":
            if not succeeded:
                return
            frame = self._grab(grab, pipeline=False)
            if frame is not None:
                with self._cond:
                    self._agent = frame
            return
        if not action or action in _NON_INPUT_ACTIONS:
            return
        with self._cond:
            frame = self._agent
            if frame is None:
                return
            frame.action = action
            frame.action_failed = not succeeded

    def _grab(self, grab: Callable[[], Any], *, pipeline: bool) -> _Frame | None:
        """限流后复制一帧入队；画面和上一帧一样时返回上一帧，不存新的。

        流水线这一路只和自己比间隔，不让 agent 截图挤掉命中节点的那一轮；agent 这一路
        要离上一次取帧（哪一路都算）满 1 秒，只在流水线空下来（Custom 动作跑着）时补帧。
        """

        now = self._clock()
        with self._cond:
            if (
                self._closed
                or len(self._pending) >= FRAME_REPLAY_MAX_PENDING
                or (
                    now - self._last_pipeline_grab
                    < FRAME_REPLAY_PIPELINE_INTERVAL_SECONDS
                    if pipeline
                    else now - self._last_grab < FRAME_REPLAY_AGENT_INTERVAL_SECONDS
                )
            ):
                return None
            self._last_grab = now
            if pipeline:
                self._last_pipeline_grab = now
        try:
            image = grab()
        except Exception:
            return None
        if image is None or getattr(image, "size", 0) == 0:
            return None
        sample = _sample(image)
        with self._cond:
            if self._closed:
                return None
            last = self._frames[-1] if self._frames else None
            if last is not None and not _changed(self._last_sample, sample):
                # 画面没变：不存新帧，本轮的识别、动作记到上一帧上
                return last
            frame = _Frame(at=now, task=self._task, node=self._node, image=image)
            self._last_sample = sample
            self._frames.append(frame)
            self._pending.append(frame)
            self._cond.notify_all()
            return frame

    def _encode_loop(self) -> None:
        while True:
            with self._cond:
                while not self._pending and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                frame = self._pending.popleft()
                image, frame.image = frame.image, None
                self._encoding += 1
            try:
                png: bytes | None = self._encode_png(image)
            except Exception:
                png = None
            with self._cond:
                self._encoding -= 1
                if png and not frame.dropped:
                    frame.png = png
                    self._bytes += len(png)
                    self._evict()
                elif not frame.dropped:
                    frame.dropped = True
                    self._frames.remove(frame)
                self._cond.notify_all()

    def _evict(self) -> None:
        while self._bytes > self._max_bytes and self._frames:
            frame = self._frames.popleft()
            frame.dropped = True
            if frame.png:
                self._bytes -= len(frame.png)
            if frame is self._round:
                self._round = None
            if frame is self._agent:
                self._agent = None

    def flush(
        self, directory: Path, stem: str, *, final_png: bytes | None = None
    ) -> Path | None:
        """把环里的帧写成一段（``<stem>.replay/``）并清空环；没有帧时什么都不写。

        ``final_png`` 是失败当刻那张截图，接在最后。一次运行最多留
        ``FRAME_REPLAY_MAX_SEGMENTS`` 段，超了删最早写出的那段。
        """

        deadline = time.monotonic() + _FLUSH_DRAIN_SECONDS
        with self._cond:
            while self._pending or self._encoding:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            frames = [frame for frame in self._frames if frame.png]
            for frame in self._frames:
                frame.dropped = True
            self._frames.clear()
            self._pending.clear()
            self._bytes = 0
            self._last_sample = None
            self._round = None
            self._agent = None
            task, node = self._task, self._node
        if final_png:
            frames.append(
                _Frame(
                    at=self._clock(),
                    task=task,
                    node=node,
                    png=final_png,
                    extra={"final": True},
                )
            )
        if not frames:
            return None
        target = directory / f"{stem}{FRAME_REPLAY_DIR_SUFFIX}"
        target.mkdir(parents=True, exist_ok=True)
        timeline = []
        for index, frame in enumerate(frames):
            file = f"{index:04d}.png"
            (target / file).write_bytes(frame.png or b"")
            timeline.append(frame.timeline_entry(file))
        (target / FRAME_REPLAY_TIMELINE).write_text(
            json.dumps(timeline, ensure_ascii=False), encoding="utf-8"
        )
        with self._cond:
            self._segments.append(target)
            stale = self._segments[:-FRAME_REPLAY_MAX_SEGMENTS]
            del self._segments[:-FRAME_REPLAY_MAX_SEGMENTS]
        for path in stale:
            shutil.rmtree(path, ignore_errors=True)
        return target

    def close(self) -> None:
        with self._cond:
            self._closed = True
            for frame in self._frames:
                frame.dropped = True
            self._frames.clear()
            self._pending.clear()
            self._bytes = 0
            self._cond.notify_all()
        self._thread.join(timeout=_FLUSH_DRAIN_SECONDS)
