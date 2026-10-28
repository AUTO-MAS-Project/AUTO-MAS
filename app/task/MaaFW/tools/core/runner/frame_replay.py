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

写出的一段是一个目录：``0000.png`` 起的帧加 ``timeline.json``（每帧的时刻、任务，以及这一
画面上依次发生的各步：节点、命中、识别框、动作）。宿主把它合成 WebM 挂到历史记录上（``tools/embedded/frame_replay_video``）。

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
# 同一画面上最多记几步（原地点个不停时只留最后这些）
FRAME_REPLAY_MAX_STEPS = 30
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
class _Step:
    """一帧画面上的一步：哪个节点、命中了谁、识别框、做了什么动作。"""

    at: float
    node: str
    hit: str = ""
    box: list[int] | None = None
    action: str = ""
    action_failed: bool = False

    def entry(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "node": self.node,
            "hit": self.hit,
            "box": self.box,
            "action": self.action,
            "actionFailed": self.action_failed,
        }


@dataclass
class _Frame:
    at: float
    task: str
    image: Any = None  # 原图，编码完清掉
    png: bytes | None = None
    dropped: bool = False
    final: bool = False
    # 画面不变时连续几轮的识别、动作都记在这一帧上，一步一条，不互相覆盖
    steps: list[_Step] = field(default_factory=list)

    def step(self, at: float, node: str) -> _Step:
        """接下来的识别、动作记到哪一步：最后一步还没命中也没动作就沿用（等待中的轮询
        不刷出一串），否则新开一步。"""

        last = self.steps[-1] if self.steps else None
        if last is not None and not last.hit and not last.action:
            last.node = node or last.node
            return last
        step = _Step(at=at, node=node)
        self.steps.append(step)
        del self.steps[:-FRAME_REPLAY_MAX_STEPS]
        return step

    def timeline_entry(self, file: str) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "file": file,
            "at": self.at,
            "task": self.task,
            "steps": [step.entry() for step in self.steps],
        }
        if self.final:
            entry["final"] = True
        return entry


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
        # 两路最近一次看画面（复制过 cached_image）与流水线最近一次存新帧的时刻
        self._last_look = float("-inf")
        self._last_pipeline_frame = float("-inf")
        self._task = ""
        self._node = ""
        # 本轮流水线的那一步：之后的识别、动作记到它上面
        self._round: _Step | None = None
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
            # 换任务后哪怕画面没变也开新帧，字幕里的任务名不挂到上一个任务的帧上
            self._last_sample = None

    def on_node(self, message: str, details: Any, grab: Callable[[], Any]) -> None:
        """context sink 的 ``Node.*``：每轮识别前取帧，识别命中与动作记到这一轮的那一步上。"""

        if not isinstance(details, dict):
            return
        name = str(details.get("name") or "")
        if message == "Node.NextList.Starting":
            with self._cond:
                self._node = name
            frame = self._grab(grab, pipeline=True)
            with self._cond:
                self._round = (
                    frame.step(self._clock(), name) if frame is not None else None
                )
            return
        if message == "Node.Action.Starting":
            # Custom 动作里 agent 自己截的图挂在这个节点名下
            with self._cond:
                self._node = name
            return
        with self._cond:
            step = self._round
            if step is None:
                return
            if message == "Node.Recognition.Succeeded":
                reco = details.get("reco_details")
                step.hit = name
                step.box = _box(reco.get("box")) if isinstance(reco, dict) else None
            elif message in ("Node.Action.Succeeded", "Node.Action.Failed"):
                if step.hit != name:
                    return
                action = details.get("action_details")
                if isinstance(action, dict) and action.get("action"):
                    step.action = str(action["action"])
                step.action_failed = message.endswith("Failed")

    def on_controller(
        self, action: str, *, succeeded: bool, grab: Callable[[], Any]
    ) -> None:
        """controller sink：agent 截图按限流取帧，agent 的点击、滑动、按键记到环里最新那帧上。

        最新那帧是此刻已知最近的画面；流水线在跑时 agent 截图大多轮不到取帧，记到
        「agent 上次取到的帧」会落到一张早已过去的旧画面上。
        """

        if action == "screencap":
            if not succeeded:
                return
            frame = self._grab(grab, pipeline=False)
            if frame is not None:
                with self._cond:
                    frame.step(self._clock(), self._node)
            return
        if not action or action in _NON_INPUT_ACTIONS:
            return
        with self._cond:
            if not self._frames:
                return
            step = self._frames[-1].step(self._clock(), self._node)
            step.action = action
            step.action_failed = not succeeded

    def _grab(self, grab: Callable[[], Any], *, pipeline: bool) -> _Frame | None:
        """复制一帧比对：画面和上一帧一样就返回上一帧，变了就（限流内）存成新帧入队。

        流水线每轮都看（一轮至多复制一次，1–2 ms），这样画面没变时本轮的识别、动作
        总能记到上一帧上；新帧每秒最多 2 张。变了但离上一张流水线新帧不到 0.5 秒、或
        编码积压时返回 None——那一轮没有画面，它的识别不能记到旧画面上。agent 截图最高
        约 40 次/秒，离上一次看画面（哪一路都算）满 1 秒才看。
        """

        now = self._clock()
        with self._cond:
            if self._closed or (
                not pipeline
                and now - self._last_look < FRAME_REPLAY_AGENT_INTERVAL_SECONDS
            ):
                return None
            self._last_look = now
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
                return last
            if len(self._pending) >= FRAME_REPLAY_MAX_PENDING or (
                pipeline
                and now - self._last_pipeline_frame
                < FRAME_REPLAY_PIPELINE_INTERVAL_SECONDS
            ):
                return None
            if pipeline:
                self._last_pipeline_frame = now
            frame = _Frame(at=now, task=self._task, image=image)
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

    def flush(
        self, directory: Path, stem: str, *, final_png: bytes | None = None
    ) -> Path | None:
        """把环里的帧写成一段（``<stem>.replay/``）并清空环；没有帧时什么都不写。

        ``final_png`` 是失败当刻那张截图，接在最后。同名目录已在（同一秒同一任务又失败、
        截止计时器与主线程同时写出）时加 ``-2``、``-3`` 后缀，不覆盖。一次运行最多留
        ``FRAME_REPLAY_MAX_SEGMENTS`` 段，超了删最早写出的那段。``timeline.json`` 最后写，
        宿主只认有它的目录。
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
            task, node = self._task, self._node
        if final_png:
            now = self._clock()
            frames.append(
                _Frame(
                    at=now,
                    task=task,
                    png=final_png,
                    final=True,
                    steps=[_Step(at=now, node=node)],
                )
            )
        if not frames:
            return None
        with self._cond:
            # 在锁里挑名字并建目录：并发的两次写出拿到的一定是两个目录
            target = directory / f"{stem}{FRAME_REPLAY_DIR_SUFFIX}"
            suffix = 2
            while target.exists():
                target = directory / f"{stem}-{suffix}{FRAME_REPLAY_DIR_SUFFIX}"
                suffix += 1
            target.mkdir(parents=True)
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
