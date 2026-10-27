"""流水线分组执行

一个分组里是一串「按顺序尝试」的流水线：跑第一条，成功了就结束；
失败了就看你给它配的「失败后执行」是哪条，有就去跑那条，没有就判整个分组失败。

典型场景：主 CA 流水线失败（限流 / 验证不过）→ 自动转备用 CA 那条流水线。
执行细节：
  * 每条流水线都走 engine.run_pipeline_async（和手动运行同一套：状态、日志、历史都一致）；
  * 本模块在自己的线程里轮询执行历史，等它结束再决定下一步，不占 engine 的线程池；
  * 同一个分组里同一条流水线只跑一次（防止 A→B→A 这种互相指向转不出来）。
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time

from ..db import SessionLocal
from ..models import History, Pipeline, PipelineGroup, PipelineGroupRun
from . import engine

#: 单条流水线最长等多久（秒）：分组是串行等待，卡死时也别把线程永远占住
_WAIT_TIMEOUT = 6 * 3600
#: 轮询执行历史的间隔（秒）
_POLL_INTERVAL = 2.0


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_items(raw: str) -> list[dict]:
    try:
        items = json.loads(raw or "[]")
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            pipeline_id = int(item.get("pipelineId") or 0)
        except (TypeError, ValueError):
            continue
        if not pipeline_id:
            continue
        try:
            on_failure = int(item.get("onFailurePipelineId") or 0)
        except (TypeError, ValueError):
            on_failure = 0
        result.append({"pipelineId": pipeline_id, "onFailurePipelineId": on_failure})
    return result


def _pipeline_title(pipeline_id: int) -> str:
    db = SessionLocal()
    try:
        row = db.get(Pipeline, pipeline_id)
        return row.title if row else f"流水线 #{pipeline_id}（已删除）"
    finally:
        db.close()


def _save_run(run_id: int, status: str, steps: list[dict], log: list[str],
              finished: bool = False) -> None:
    db = SessionLocal()
    try:
        row = db.get(PipelineGroupRun, run_id)
        if not row:
            return
        row.status = status
        row.steps = json.dumps(steps, ensure_ascii=False)
        row.log = "\n".join(log[-500:])
        if finished:
            row.end_time = dt.datetime.now()
        db.commit()
    finally:
        db.close()


def _wait_history(history_id: int, timeout: int = _WAIT_TIMEOUT) -> str:
    """等一条执行历史结束，返回 success / failed / canceled / timeout。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        db = SessionLocal()
        try:
            row = db.get(History, history_id)
            status = row.status if row else "failed"
        finally:
            db.close()
        if status != "running":
            return status
        time.sleep(_POLL_INTERVAL)
    return "timeout"


def _execute(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(PipelineGroupRun, run_id)
        if not run:
            return
        user_id, group_id = run.user_id, run.group_id
        group = db.get(PipelineGroup, group_id)
        items = _load_items(group.items if group else "[]")
    finally:
        db.close()

    by_pipeline = {item["pipelineId"]: item for item in items}
    steps: list[dict] = []
    log: list[str] = [f"[{_now_text()}] 开始执行分组（共 {len(items)} 条流水线）"]

    def record(index: int, pipeline_id: int, status: str, message: str = "",
               history_id: int = 0, started: str = "", ended: str = "") -> dict:
        step = {
            "index": index,
            "pipelineId": pipeline_id,
            "pipelineTitle": _pipeline_title(pipeline_id),
            "historyId": history_id,
            "status": status,
            "message": message,
            "startTime": started,
            "endTime": ended,
        }
        steps.append(step)
        return step

    if not items:
        record(0, 0, "failed", "分组里没有配置流水线")
        _save_run(run_id, "failed", steps, log + ["分组里没有配置流水线"], finished=True)
        return

    visited: set[int] = set()
    status = "failed"
    current_id = items[0]["pipelineId"]
    index = 0

    while current_id:
        index += 1
        title = _pipeline_title(current_id)
        if current_id in visited:
            log.append(f"[{_now_text()}] 跳过「{title}」：本次分组里已经执行过，避免互相指向转不出来")
            record(index, current_id, "skipped", "本次分组里已执行过，跳过（防止死循环）")
            break
        visited.add(current_id)

        started = _now_text()
        log.append(f"[{_now_text()}] 执行「{title}」（第 {index} 条）")
        _save_run(run_id, "running", steps + [{
            "index": index, "pipelineId": current_id, "pipelineTitle": title,
            "historyId": 0, "status": "running", "message": "正在执行",
            "startTime": started, "endTime": "",
        }], log)

        history_id = 0
        result = "failed"
        message = ""
        try:
            history_id = engine.run_pipeline_async(current_id, "group", user_id=user_id)
            result = _wait_history(history_id)
            if result == "timeout":
                message = "等待执行结束超时（超过 6 小时）"
            elif result == "canceled":
                message = "执行被手动停止"
        except Exception as exc:  # noqa: BLE001 - 单条失败不影响分组收尾，错误转成一句话
            message = str(exc)

        ended = _now_text()
        log.append(f"[{_now_text()}] 「{title}」结果：{result}" + (f"（{message}）" if message else ""))
        record(index, current_id, result, message, history_id=history_id,
               started=started, ended=ended)

        if result == "success":
            status = "success"
            log.append(f"[{_now_text()}] 分组执行成功，停止后续尝试")
            break

        next_id = int(by_pipeline.get(current_id, {}).get("onFailurePipelineId") or 0)
        if next_id:
            next_title = _pipeline_title(next_id)
            steps[-1]["nextPipelineId"] = next_id
            steps[-1]["nextPipelineTitle"] = next_title
            log.append(f"[{_now_text()}] 失败后转去执行「{next_title}」")
            current_id = next_id
            continue

        status = "failed"
        log.append(f"[{_now_text()}] 没有配置「失败后执行」的流水线，分组执行失败")
        break

    _save_run(run_id, status, steps, log, finished=True)


def start_group_run(group: PipelineGroup, user_id: int, trigger: str = "group") -> int:
    """建一条分组执行记录并丢到后台线程，立刻返回 run_id（前端可马上轮询进度）。"""
    db = SessionLocal()
    try:
        row = PipelineGroupRun(user_id=user_id, group_id=group.id, group_name=group.name,
                               status="running", steps="[]", log="",
                               start_time=dt.datetime.now())
        db.add(row)
        db.commit()
        db.refresh(row)
        run_id = row.id
    finally:
        db.close()

    threading.Thread(target=_execute, args=(run_id,), name=f"group-run-{run_id}",
                     daemon=True).start()
    return run_id
