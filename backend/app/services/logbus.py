"""执行日志总线
==============
流水线跑在后台线程里，日志原本只写数据库、前端靠轮询看——一次签发要几十秒到几分钟，
轮询既延迟高又浪费请求。

这里做一个进程内的发布/订阅：runner 每写一行日志就 publish，
SSE 接口按「从第 N 行开始」读取并阻塞等待新行，前端拿到的就是逐行实时输出。

设计上的几个取舍：

- **用 threading.Condition 而不是 asyncio.Queue**：runner 在 ThreadPoolExecutor 里跑，
  FastAPI 的同步生成器也在线程池里跑，两边都是同步代码，用条件变量最直接；
  如果改成 asyncio，就得处理跨线程调度（call_soon_threadsafe），反而更容易出错。
- **频道保留全量行**：SSE 断线重连时要能从头补，所以不丢弃已发出的行。
  一次执行几千行、几十 KB，可以接受；跑完的频道延迟清理。
- **频道是进程内的**：多 worker 部署时，SSE 必须落在跑任务的那个进程上。
  本项目默认单进程（uvicorn 单 worker），这点在 README 里注明。
"""
from __future__ import annotations

import threading
import time

#: 跑完的频道保留多久（秒）——留给「刚结束就打开详情」的场景
KEEP_AFTER_CLOSE = 300
#: 最多保留多少个频道，防止长时间运行后内存堆积
MAX_CHANNELS = 64


class Channel:
    def __init__(self, history_id: int):
        self.history_id = history_id
        self.lines: list[str] = []
        self.closed = False
        self.closed_at = 0.0
        # 任务进度快照：每完成一个任务更新一次，前端据此渲染左侧任务条，
        # 不用再另开一个轮询接口
        self.tasks: str = ""
        self.status: str = "running"
        self._cond = threading.Condition()

    def publish(self, line: str) -> None:
        with self._cond:
            self.lines.append(line)
            self._cond.notify_all()

    def publish_tasks(self, payload: str) -> None:
        with self._cond:
            self.tasks = payload
            self._cond.notify_all()

    def set_status(self, status: str) -> None:
        with self._cond:
            self.status = status
            self._cond.notify_all()

    def close(self) -> None:
        with self._cond:
            self.closed = True
            self.closed_at = time.time()
            self._cond.notify_all()

    def read_from(self, index: int, timeout: float = 15.0
                  ) -> tuple[list[str], bool, str, str]:
        """读取 index 之后的行；没有新行就最多等 timeout 秒。

        返回 (新增行, 是否已结束, 任务快照, 当前状态)。
        结束时会把剩余行一次性给完。
        """
        with self._cond:
            if len(self.lines) <= index and not self.closed:
                self._cond.wait(timeout)
            return self.lines[index:], self.closed, self.tasks, self.status


_channels: dict[int, Channel] = {}
_lock = threading.Lock()


def open_channel(history_id: int) -> Channel:
    with _lock:
        _evict()
        ch = Channel(history_id)
        _channels[history_id] = ch
        return ch


def get_channel(history_id: int) -> Channel | None:
    with _lock:
        return _channels.get(history_id)


def publish(history_id: int, line: str) -> None:
    ch = get_channel(history_id)
    if ch:
        ch.publish(line)


def close_channel(history_id: int) -> None:
    ch = get_channel(history_id)
    if ch:
        ch.close()


def _evict() -> None:
    """清理过期的已关闭频道，必要时按关闭时间淘汰最旧的。"""
    now = time.time()
    dead = [hid for hid, ch in _channels.items()
            if ch.closed and now - ch.closed_at > KEEP_AFTER_CLOSE]
    for hid in dead:
        _channels.pop(hid, None)
    if len(_channels) <= MAX_CHANNELS:
        return
    closed = sorted((ch for ch in _channels.values() if ch.closed),
                    key=lambda c: c.closed_at)
    for ch in closed[: len(_channels) - MAX_CHANNELS]:
        _channels.pop(ch.history_id, None)
