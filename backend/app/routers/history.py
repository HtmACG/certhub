"""执行历史接口"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import fail, get_current_user, ok, page_no
from ..models import History, User
from ..services import engine, logbus

router = APIRouter(prefix="/api/history", tags=["history"])


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


@router.get("/list")
def list_history(page: int = Depends(page_no), size: int = Query(10),
                 pipelineId: int = Query(0), status: str = "",
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(History).filter(History.user_id == user.id)
    if pipelineId:
        query = query.filter(History.pipeline_id == pipelineId)
    if status:
        query = query.filter(History.status == status)
    total = query.count()
    rows = query.order_by(History.id.desc()).offset((page - 1) * size).limit(size).all()
    records = []
    for r in rows:
        try:
            tasks = json.loads(r.tasks or "[]")
        except Exception:
            tasks = []
        duration = 0
        if r.end_time and r.start_time:
            duration = int((r.end_time - r.start_time).total_seconds())
        records.append({
            "id": r.id, "pipelineId": r.pipeline_id, "pipelineTitle": r.pipeline_title,
            "status": r.status, "triggerType": r.trigger_type,
            "startTime": _fmt(r.start_time), "endTime": _fmt(r.end_time),
            "duration": duration, "taskCount": len(tasks),
        })
    return ok({"records": records, "total": total, "current": page, "size": size})


@router.get("/{history_id}")
def get_history(history_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    h = db.get(History, history_id)
    if not h or h.user_id != user.id:
        return fail("记录不存在")
    try:
        tasks = json.loads(h.tasks or "[]")
    except Exception:
        tasks = []
    return ok({
        "id": h.id, "pipelineId": h.pipeline_id, "pipelineTitle": h.pipeline_title,
        "status": h.status, "triggerType": h.trigger_type,
        "startTime": _fmt(h.start_time), "endTime": _fmt(h.end_time),
        "tasks": tasks, "log": h.log or "",
    })


@router.delete("/{history_id}")
def delete_history(history_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    h = db.get(History, history_id)
    if not h or h.user_id != user.id:
        return fail("记录不存在")
    db.delete(h)
    db.commit()
    return ok(True)


@router.get("/{history_id}/stream")
def stream_history(history_id: int, offset: int = 0,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """SSE：把执行日志逐行推给前端。

    - 运行中的任务从内存频道读，写完一行就能看到，不再等 1 秒一次的落库节流；
    - 已结束（或服务重启后频道不存在）的记录，直接回放数据库里的日志再结束。
    """
    h = db.get(History, history_id)
    if not h or h.user_id != user.id:
        return fail("记录不存在")

    channel = logbus.get_channel(history_id)
    replay = [] if channel else (h.log or "").splitlines()
    start = max(offset, 0)

    def gen():
        index = start
        if channel is None:
            for line in replay[index:]:
                yield _sse({"line": line})
            yield _sse({"tasks": _load_tasks(h.tasks), "status": h.status},
                       event="tasks")
            yield _sse({"status": h.status}, event="end")
            return
        last_tasks = ""
        last_status = ""
        while True:
            lines, closed, tasks, status = channel.read_from(index)
            for line in lines:
                yield _sse({"line": line})
            index += len(lines)
            if tasks and tasks != last_tasks:
                last_tasks = tasks
                yield _sse({"tasks": _load_tasks(tasks), "status": status}, event="tasks")
            if status != last_status:
                last_status = status
                yield _sse({"status": status}, event="status")
            if closed and not lines:
                yield _sse({"status": status}, event="end")
                return
            if not lines:
                # 长时间没输出时发个注释行，避免中间层把连接当空闲掐掉
                yield ": keepalive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


@router.post("/{history_id}/stop")
def stop_history(history_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """请求停止一次执行。

    停止是协作式的：任务之间、以及 ACME 轮询的每一轮都会检查标志位，
    正在进行的单次 HTTP 请求不会被强行打断。
    """
    h = db.get(History, history_id)
    if not h or h.user_id != user.id:
        return fail("记录不存在")
    if h.status != "running":
        return fail("该记录不在运行中")
    engine.request_stop(history_id)
    return ok(True)


def _sse(payload: dict, event: str = "") -> str:
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _load_tasks(raw) -> list:
    """数据库里存的是 JSON 字符串，内存频道里也是字符串，统一转成 list。"""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


@router.post("/clear")
def clear_history(pipelineId: int = Query(0), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    query = db.query(History).filter(History.user_id == user.id)
    if pipelineId:
        query = query.filter(History.pipeline_id == pipelineId)
    query.delete()
    db.commit()
    return ok(True)
