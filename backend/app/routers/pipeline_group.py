"""流水线分组接口

一个分组 = 一串按顺序尝试的流水线；某条失败时可以指定「失败后执行」哪一条。
（分组本身不跑证书任务，只负责调度已有的流水线，和手动运行共用同一套执行历史。）
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, fail, get_current_user, ok, page_no
from ..models import Pipeline, PipelineGroup, PipelineGroupRun, User
from ..services import group_runner

router = APIRouter(prefix="/api/pipeline-group", tags=["pipeline-group"])


def _fmt(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


class GroupItem(BaseModel):
    pipelineId: int
    onFailurePipelineId: int = 0


class GroupParams(BaseModel):
    name: str
    remark: str = ""
    enabled: bool = True
    items: list[GroupItem] = []


def _titles(db: Session, user_id: int) -> dict[int, str]:
    rows = db.query(Pipeline).filter(Pipeline.user_id == user_id).all()
    return {row.id: row.title for row in rows}


def _serialize(row: PipelineGroup, titles: dict[int, str], last_run=None) -> dict:
    try:
        items = json.loads(row.items or "[]")
    except Exception:  # noqa: BLE001
        items = []
    return {
        "id": row.id,
        "name": row.name,
        "remark": row.remark or "",
        "enabled": bool(row.enabled),
        "items": [{
            "pipelineId": int(item.get("pipelineId") or 0),
            "pipelineTitle": titles.get(int(item.get("pipelineId") or 0),
                                        f"流水线 #{item.get('pipelineId')}"),
            "onFailurePipelineId": int(item.get("onFailurePipelineId") or 0),
            "onFailurePipelineTitle": titles.get(int(item.get("onFailurePipelineId") or 0), ""),
        } for item in items if isinstance(item, dict)],
        "lastRun": ({
            "id": last_run.id, "status": last_run.status,
            "startTime": _fmt(last_run.start_time), "endTime": _fmt(last_run.end_time),
        } if last_run else None),
        "createTime": _fmt(row.create_time),
    }


def _clean_items(db: Session, user_id: int, items: list[GroupItem]) -> tuple[str, str]:
    """校验并规整成员：流水线必须存在且属于当前用户，返回 (json 文本, 错误)。"""
    if not items:
        return "", "请至少添加一条流水线"
    seen: set[int] = set()
    cleaned: list[dict] = []
    for item in items:
        pipeline_id = int(item.pipelineId or 0)
        if not pipeline_id:
            return "", "请选择流水线"
        row = db.get(Pipeline, pipeline_id)
        if not row or row.user_id != user_id:
            return "", f"流水线 #{pipeline_id} 不存在"
        if pipeline_id in seen:
            return "", f"「{row.title}」重复添加了"
        seen.add(pipeline_id)
        on_failure = int(item.onFailurePipelineId or 0)
        if on_failure:
            target = db.get(Pipeline, on_failure)
            if not target or target.user_id != user_id:
                return "", f"「失败后执行」选的流水线 #{on_failure} 不存在"
            if on_failure == pipeline_id:
                return "", "「失败后执行」不能选自己"
        cleaned.append({"pipelineId": pipeline_id, "onFailurePipelineId": on_failure})
    if len(cleaned) > 1:
        # 顺序尝试语义下，后面的成员只有在前面失败时才会被轮到；提示一次别配错
        pass
    return json.dumps(cleaned, ensure_ascii=False), ""


@router.get("/list")
def list_groups(page: int = Depends(page_no), size: int = Query(20), keyword: str = "",
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(PipelineGroup).filter(PipelineGroup.user_id == user.id)
    keyword = (keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(PipelineGroup.name.like(like),
                                 PipelineGroup.remark.like(like)))
    total = query.count()
    rows = query.order_by(PipelineGroup.id.desc()).offset((page - 1) * size).limit(size).all()
    titles = _titles(db, user.id)
    runs = {}
    if rows:
        run_rows = (db.query(PipelineGroupRun)
                    .filter(PipelineGroupRun.user_id == user.id,
                            PipelineGroupRun.group_id.in_([row.id for row in rows]))
                    .order_by(PipelineGroupRun.id.desc()).all())
        for run in run_rows:
            runs.setdefault(run.group_id, run)
    return ok({"records": [_serialize(row, titles, runs.get(row.id)) for row in rows],
               "total": total, "current": page, "size": size})


@router.post("")
def create_group(params: GroupParams, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    name = (params.name or "").strip()
    if not name:
        return fail("请填写分组名称")
    items_text, error = _clean_items(db, user.id, params.items)
    if error:
        return fail(error)
    row = PipelineGroup(user_id=user.id, name=name, remark=params.remark.strip(),
                        enabled=bool(params.enabled), items=items_text)
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, user, "新增流水线分组", name)
    return ok({"id": row.id})


@router.put("/{group_id}")
def update_group(group_id: int, params: GroupParams,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(PipelineGroup, group_id)
    if not row or row.user_id != user.id:
        return fail("分组不存在")
    name = (params.name or "").strip()
    if not name:
        return fail("请填写分组名称")
    items_text, error = _clean_items(db, user.id, params.items)
    if error:
        return fail(error)
    row.name = name
    row.remark = params.remark.strip()
    row.enabled = bool(params.enabled)
    row.items = items_text
    db.commit()
    audit(db, user, "修改流水线分组", name)
    return ok(True)


@router.delete("/{group_id}")
def delete_group(group_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    row = db.get(PipelineGroup, group_id)
    if not row or row.user_id != user.id:
        return fail("分组不存在")
    db.query(PipelineGroupRun).filter(PipelineGroupRun.group_id == row.id).delete()
    name = row.name
    db.delete(row)
    db.commit()
    audit(db, user, "删除流水线分组", name)
    return ok(True)


@router.post("/{group_id}/run")
def run_group(group_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """执行分组：按顺序跑，某条成功就结束；失败则跳它配置的「失败后执行」。"""
    row = db.get(PipelineGroup, group_id)
    if not row or row.user_id != user.id:
        return fail("分组不存在")
    if not row.enabled:
        return fail("这个分组已停用")
    items = group_runner._load_items(row.items)
    if not items:
        return fail("分组里没有配置流水线")
    first = db.get(Pipeline, items[0]["pipelineId"])
    if not first or first.user_id != user.id:
        return fail("分组里第一条流水线不存在，请重新编辑分组")
    audit(db, user, "运行流水线分组", row.name)
    run_id = group_runner.start_group_run(row, user.id)
    return ok({"runId": run_id, "groupId": row.id})


@router.get("/run/list")
def list_runs(page: int = Depends(page_no), size: int = Query(20), groupId: int = Query(0),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(PipelineGroupRun).filter(PipelineGroupRun.user_id == user.id)
    if groupId:
        query = query.filter(PipelineGroupRun.group_id == groupId)
    total = query.count()
    rows = query.order_by(PipelineGroupRun.id.desc()).offset((page - 1) * size).limit(size).all()
    return ok({"records": [_serialize_run(row) for row in rows], "total": total,
               "current": page, "size": size})


def _serialize_run(row: PipelineGroupRun) -> dict:
    try:
        steps = json.loads(row.steps or "[]")
    except Exception:  # noqa: BLE001
        steps = []
    return {
        "id": row.id, "groupId": row.group_id, "groupName": row.group_name,
        "status": row.status, "steps": steps, "log": row.log or "",
        "startTime": _fmt(row.start_time), "endTime": _fmt(row.end_time),
    }


@router.get("/run/{run_id}")
def get_run(run_id: int, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    row = db.get(PipelineGroupRun, run_id)
    if not row or row.user_id != user.id:
        return fail("执行记录不存在")
    return ok(_serialize_run(row))
