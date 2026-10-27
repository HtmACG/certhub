"""流水线接口"""
from __future__ import annotations

import hmac
import json
import time
import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, fail, get_current_user, ok, page_no
from ..models import Access, Certificate, History, Pipeline, User
from ..plugins import (ACCESS_CATEGORIES, ACCESS_TYPES, ACME_PROVIDERS, DNS_PROVIDERS,
                       NOTIFY_TYPES, PLUGIN_GROUPS, TASK_PLUGIN_MAP, TASK_PLUGINS)
from ..security import decrypt_json
from ..services import resources
from ..services.engine import is_running, run_pipeline_async
from ..services.scheduler import next_run

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def _content_domains(content: dict) -> list[str]:
    """从流水线内容里收集证书域名（签发类任务的 domains 入参）。

    卡片式列表要展示「这条流水线管哪些域名」，走 content 解析比让前端再请求一次强。
    """
    seen: list[str] = []
    for stage in content.get("stages") or []:
        for task in stage.get("tasks") or []:
            if not str(task.get("type", "")).startswith("CertApply"):
                continue
            domains = (task.get("input") or {}).get("domains")
            if isinstance(domains, str):
                domains = [domains]
            for item in domains or []:
                name = str(item).strip()
                if name and name not in seen:
                    seen.append(name)
    return seen


def _content_kinds(content: dict) -> list[str]:
    """流水线包含哪几类环节：cert（申请）/ deploy（部署）/ notify（通知）。

    列表页要用它给每条流水线打「申请 + 部署」这样的分类标签，
    让用户一眼看出这条流程走到哪一步；前端只负责把 key 映射成文案与颜色。
    """
    kinds: list[str] = []
    for stage in content.get("stages") or []:
        for task in stage.get("tasks") or []:
            # 停用的步骤运行时会跳过，不该出现在「申请 + 部署」这类标签里
            if task.get("enabled") is False:
                continue
            # 画布上没连线的步骤同样不会执行
            if task.get("linked") is False:
                continue
            task_type = str(task.get("type", ""))
            if task_type == "Notify":
                kind = "notify"
            elif task_type.startswith("CertApply"):
                kind = "cert"
            else:
                kind = "deploy"
            if kind not in kinds:
                kinds.append(kind)
    return kinds


def _serialize(p: Pipeline, detail: bool = False, last_status: str = "") -> dict:
    try:
        content = json.loads(p.content or "{}")
    except Exception:
        content = {}
    stages = content.get("stages") or []
    # 阶段开关（stage.enabled === false）关掉后整段不跑，里面的任务既不算「会执行的步骤」，
    # 也不算「未连线」—— 统一按停用计，列表页的数字才对得上实际执行。
    live_stages = [s for s in stages if s.get("enabled") is not False]
    off_stages = [s for s in stages if s.get("enabled") is False]
    data = {
        "id": p.id, "title": p.title, "remark": p.remark or "",
        "disabled": bool(p.disabled), "type": p.type,
        "keepHistoryCount": p.keep_history_count,
        "lastHistoryTime": _fmt(p.last_history_time),
        "nextRunTime": _fmt(p.next_run_time),
        "validTime": _fmt(p.valid_time),
        "createTime": _fmt(p.create_time),
        "updateTime": _fmt(p.update_time),
        "running": is_running(p.id),
        "stageCount": len(stages),
        "stepCount": sum(
            1 for stage in live_stages
            for task in stage.get("tasks") or []
            if task.get("enabled") is not False and task.get("linked") is not False),
        #: 停用的步骤数（界面上单独提示，别让「4 个任务」和实际执行对不上）
        "stepDisabledCount": (
            sum(1 for stage in live_stages
                for task in stage.get("tasks") or [] if task.get("enabled") is False)
            + sum(len(stage.get("tasks") or []) for stage in off_stages)),
        #: 画布上没连线的步骤数：不连线就不会执行，列表里也要能看出差别
        "stepUnlinkedCount": sum(
            1 for stage in live_stages
            for task in stage.get("tasks") or []
            if task.get("enabled") is not False and task.get("linked") is False),
        "taskCount": sum(len(stage.get("tasks") or []) for stage in stages),
        "triggerCount": len(content.get("triggers") or []),
        # 卡片式列表用：域名标签 + 上次执行结果 + 流程分类
        "domains": _content_domains(content),
        "kinds": _content_kinds(content),
        "lastStatus": last_status,
    }
    if detail:
        data["content"] = content
    return data


def _latest_certs(db, user_id: int, ids: list[int]) -> dict[int, Certificate]:
    """每条流水线最近一张证书：列表页要显示「剩余有效期」，别让前端再逐行请求。"""
    if not ids:
        return {}
    rows = (db.query(Certificate)
            .filter(Certificate.user_id == user_id, Certificate.pipeline_id.in_(ids))
            .order_by(Certificate.id.desc()).all())
    latest: dict[int, Certificate] = {}
    for row in rows:
        if row.pipeline_id not in latest:
            latest[row.pipeline_id] = row
    return latest


def _check_content(content: dict) -> str:
    if not isinstance(content, dict):
        return "配置格式错误"
    stages = content.get("stages")
    if not isinstance(stages, list) or not stages:
        return "至少需要一个阶段"
    for stage in stages:
        for task in stage.get("tasks") or []:
            if task.get("type") not in TASK_PLUGIN_MAP:
                return f"未知任务类型：{task.get('type')}"
    # 「失败后跳转」只能指向排在后面的任务：执行顺序是线性展开的，往前跳会成环
    ordered: list[dict] = []
    for stage in stages:
        ordered.extend(stage.get("tasks") or [])
    pos = {str(t.get("id")): i for i, t in enumerate(ordered) if t.get("id")}
    for i, task in enumerate(ordered):
        target = str(task.get("onErrorTaskId") or "")
        if not target:
            continue
        if target not in pos:
            return f"「{task.get('title') or task.get('type')}」的失败后跳转目标不存在"
        if pos[target] <= i:
            return (f"「{task.get('title') or task.get('type')}」的失败后跳转"
                    f"只能指向它后面的任务")
    for tr in content.get("triggers") or []:
        if tr.get("type") == "timer" and tr.get("enabled", True):
            if not tr.get("cron"):
                return "定时触发器需要填写 cron 表达式"
            if not next_run(tr["cron"]):
                return f"cron 表达式不合法：{tr['cron']}"
    return ""


@router.get("/plugins")
def plugins(_: User = Depends(get_current_user)):
    return ok({
        "groups": PLUGIN_GROUPS,
        "plugins": TASK_PLUGINS,
        "accessTypes": ACCESS_TYPES,
        "accessCategories": ACCESS_CATEGORIES,
        "notifyTypes": NOTIFY_TYPES,
        "acmeProviders": ACME_PROVIDERS,
        "dnsProviders": DNS_PROVIDERS,
    })


class PluginOptionsParams(BaseModel):
    input: dict = {}


@router.post("/plugin/{task_type}/options/{field}")
def plugin_field_options(task_type: str, field: str, params: PluginOptionsParams | None = None,
                         user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """表单里的「远程下拉」：按当前选中的授权，把可选资源实时拉回来。

    比如宝塔的站点、雷池的证书 ID、K8s 的命名空间、CDN 的加速域名，
    用户不用去控制台抄一遍，也不存在「填错了才在运行时报错」。
    """
    plugin = TASK_PLUGIN_MAP.get(task_type)
    if not plugin:
        return fail("未知任务类型")
    item = next((i for i in plugin.get("inputs") or [] if i.get("key") == field), None)
    if not item or not item.get("remote"):
        return fail("该字段不支持自动拉取")
    form = (params.input if params else {}) or {}
    access_key = item.get("remoteFrom") or "accessId"
    access_id = form.get(access_key)
    if not access_id:
        return fail("请先选择对应授权，再刷新列表")
    row = db.get(Access, int(access_id))
    if not row or row.user_id != user.id:
        return fail("授权不存在")
    cfg = decrypt_json(row.config)
    items, error = resources.resolve(row.type, cfg, item["remote"])
    return ok({"kind": item["remote"], "accessType": row.type,
               "total": len(items), "items": items, "error": error})


@router.get("/list")
def list_pipelines(page: int = Depends(page_no), size: int = Query(10), keyword: str = "",
                   status: str = "", disabled: str = "",
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Pipeline).filter(Pipeline.user_id == user.id)
    if keyword:
        query = query.filter(or_(Pipeline.title.like(f"%{keyword}%"),
                                 Pipeline.remark.like(f"%{keyword}%")))
    if disabled in ("true", "false"):
        query = query.filter(Pipeline.disabled.is_(disabled == "true"))
    if status:
        # 状态取自最近一次执行：certd 列表按「最近一次结果」筛选，这里用相关子查询实现
        last_status = (db.query(History.status)
                       .filter(History.pipeline_id == Pipeline.id)
                       .order_by(History.id.desc()).limit(1).scalar_subquery())
        query = query.filter(last_status == status)
    total = query.count()
    rows = query.order_by(Pipeline.id.desc()).offset((page - 1) * size).limit(size).all()

    # 上次执行结果：只查当前页这几条，避免整表扫历史
    last_status: dict[int, str] = {}
    ids = [r.id for r in rows]
    if ids:
        histories = (db.query(History)
                     .filter(History.user_id == user.id, History.pipeline_id.in_(ids))
                     .order_by(History.id.desc()).limit(len(ids) * 5).all())
        for hist in histories:
            last_status.setdefault(hist.pipeline_id, hist.status)

    certs = _latest_certs(db, user.id, ids)
    records = []
    for row in rows:
        item = _serialize(row, last_status=last_status.get(row.id, ""))
        cert = certs.get(row.id)
        item["certDomains"] = [d for d in (cert.domains or "").split(",") if d] if cert else []
        item["certIssuer"] = (cert.issuer or "") if cert else ""
        item["certEffectiveTime"] = _fmt(cert.not_before) if cert else ""
        item["certExpiresTime"] = _fmt(cert.not_after) if cert else ""
        records.append(item)
    return ok({"records": records, "total": total, "current": page, "size": size})


# 注意：静态路径必须注册在 /{pipeline_id} 之前，否则会被当成 id 解析
@router.get("/templates")
def list_templates(user: User = Depends(get_current_user)):
    """流水线模板列表（仅返回骨架，不含任何用户凭据）"""
    from ..templates import PIPELINE_TEMPLATES

    return ok([
        {"id": t["id"], "name": t["name"], "desc": t["desc"],
         "tags": t.get("tags", []), "stageCount": len(t["content"]["stages"])}
        for t in PIPELINE_TEMPLATES
    ])


@router.get("/{pipeline_id}")
def get_pipeline(pipeline_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    p = db.get(Pipeline, pipeline_id)
    if not p or p.user_id != user.id:
        return fail("流水线不存在")
    data = _serialize(p, detail=True)

    # 最近一次执行的任务状态：编辑页的任务卡要能显示「上次成功/失败」
    last = (db.query(History)
            .filter(History.pipeline_id == pipeline_id, History.user_id == user.id)
            .order_by(History.id.desc()).first())
    if last:
        try:
            tasks_state = json.loads(last.tasks or "{}")
        except Exception:  # noqa: BLE001
            tasks_state = {}
        # tasks 落库时是列表（[{"taskId","status","duration",...}]），这里补一份按 id 索引的
        by_id = {}
        for item in tasks_state if isinstance(tasks_state, list) else []:
            if isinstance(item, dict) and item.get("taskId"):
                by_id[str(item["taskId"])] = item
        data["lastRun"] = {
            "id": last.id,
            "status": last.status,
            "startTime": _fmt(last.start_time),
            "endTime": _fmt(last.end_time),
            "duration": round((last.end_time - last.start_time).total_seconds(), 1)
            if last.end_time and last.start_time else None,
            "tasks": by_id,
        }
    return ok(data)


class PipelineParams(BaseModel):
    title: str
    remark: str = ""
    content: dict
    keepHistoryCount: int = 20
    type: str = "cert_apply"
    disabled: bool = False


@router.post("")
def create_pipeline(params: PipelineParams, request: Request,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    err = _check_content(params.content)
    if err:
        return fail(err)
    p = Pipeline(user_id=user.id, title=params.title,
                 content=json.dumps(params.content, ensure_ascii=False),
                 remark=params.remark, type=params.type,
                 keep_history_count=params.keepHistoryCount,
                 disabled=params.disabled)
    db.add(p)
    db.commit()
    db.refresh(p)
    audit(db, user, "新增流水线", params.title)
    return ok({"id": p.id})


@router.put("/{pipeline_id}")
def update_pipeline(pipeline_id: int, params: PipelineParams,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(Pipeline, pipeline_id)
    if not p or p.user_id != user.id:
        return fail("流水线不存在")
    err = _check_content(params.content)
    if err:
        return fail(err)
    p.title = params.title
    p.content = json.dumps(params.content, ensure_ascii=False)
    p.remark = params.remark
    p.type = params.type
    p.keep_history_count = params.keepHistoryCount
    p.disabled = params.disabled
    # 定时器可能被改过，同步刷新下次执行时间
    _sync_next_run(p)
    db.commit()
    audit(db, user, "修改流水线", params.title)
    return ok(True)


@router.delete("/{pipeline_id}")
def delete_pipeline(pipeline_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    p = db.get(Pipeline, pipeline_id)
    if not p or p.user_id != user.id:
        return fail("流水线不存在")
    if is_running(p.id):
        return fail("流水线正在运行，无法删除")
    db.query(History).filter(History.pipeline_id == p.id).delete()
    db.delete(p)
    db.commit()
    audit(db, user, "删除流水线", p.title)
    return ok(True)


@router.post("/{pipeline_id}/run")
def run(pipeline_id: int, user: User = Depends(get_current_user),
        db: Session = Depends(get_db)):
    p = db.get(Pipeline, pipeline_id)
    if not p or p.user_id != user.id:
        return fail("流水线不存在")
    try:
        history_id = run_pipeline_async(p.id, "manual", user.id)
    except Exception as exc:
        return fail(str(exc))
    audit(db, user, "运行流水线", p.title)
    # 返回 historyId：前端据此直接打开实时日志，不用去列表里猜哪条是新记录
    return ok({"historyId": history_id})


class StageRunParams(BaseModel):
    stageId: str = ""


@router.post("/{pipeline_id}/stage/run")
def run_stage(pipeline_id: int, params: StageRunParams,
              user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """只单独运行某一个阶段（阶段卡片上的「执行」按钮），返回 historyId。"""
    p = db.get(Pipeline, pipeline_id)
    if not p or p.user_id != user.id:
        return fail("流水线不存在")
    try:
        content = json.loads(p.content or "{}")
    except Exception:
        return fail("流水线配置格式错误")
    stage = next((s for s in (content.get("stages") or [])
                  if str(s.get("id") or "") == str(params.stageId)), None)
    if not stage:
        return fail("阶段不存在或已被删除")
    if not stage.get("tasks"):
        return fail("该阶段还没有任务，无法单独运行")
    # 阶段开关关掉后整段跳过。这里提前拦，给一句能看懂的提示，
    # 而不是让引擎跑起来再记一条「失败的执行历史」。
    if stage.get("enabled") is False:
        return fail("该阶段已停用，请先启用再单独运行")
    try:
        history_id = run_pipeline_async(p.id, "manual", user.id,
                                        only_stage_id=params.stageId)
    except Exception as exc:
        return fail(str(exc))
    audit(db, user, "单独运行阶段",
          f"{p.title} / {stage.get('title') or '未命名'}")
    return ok({"historyId": history_id})


@router.post("/{pipeline_id}/disable")
def toggle_disable(pipeline_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    p = db.get(Pipeline, pipeline_id)
    if not p or p.user_id != user.id:
        return fail("流水线不存在")
    p.disabled = not p.disabled
    db.commit()
    return ok({"disabled": p.disabled})


@router.post("/{pipeline_id}/copy")
def copy_pipeline(pipeline_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    p = db.get(Pipeline, pipeline_id)
    if not p or p.user_id != user.id:
        return fail("流水线不存在")
    new = Pipeline(user_id=user.id, title=f"{p.title} - 副本", content=p.content,
                   remark=p.remark, type=p.type, keep_history_count=p.keep_history_count)
    db.add(new)
    db.commit()
    db.refresh(new)
    return ok({"id": new.id})


@router.post("/{pipeline_id}/trigger")
def trigger_webhook(pipeline_id: int, body: dict | None = None,
                    db: Session = Depends(get_db)):
    """供外部 webhook 调用的无鉴权触发器（需携带 pipeline 的 triggerKey）"""
    p = db.get(Pipeline, pipeline_id)
    if not p:
        return fail("流水线不存在", 404)
    key = str((body or {}).get("key", "") or "")
    content = json.loads(p.content or "{}")
    expected = str(content.get("triggerKey", "") or "")
    # 常量时间比较，避免用响应耗时逐字节猜出触发密钥
    if not expected or not hmac.compare_digest(key, expected):
        return fail("触发密钥不正确", 403)
    run_pipeline_async(p.id, "webhook", p.user_id)
    return ok(True)


@router.get("/{pipeline_id}/certs")
def pipeline_certs(pipeline_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    rows = (db.query(Certificate)
            .filter(Certificate.pipeline_id == pipeline_id, Certificate.user_id == user.id)
            .order_by(Certificate.id.desc()).limit(20).all())
    return ok([{
        "id": r.id, "domains": r.domains, "issuer": r.issuer,
        "notAfter": _fmt(r.not_after), "createTime": _fmt(r.create_time),
    } for r in rows])


def _set_pipeline_notify(content: dict, notification_id: int) -> None:
    """把通知渠道写进流水线：有 Notify 任务就改，没有就补一个「通知」阶段。"""
    stages = content.setdefault("stages", [])
    for stage in stages:
        for task in stage.get("tasks") or []:
            if task.get("type") == "Notify":
                if notification_id:
                    task.setdefault("input", {})["notificationId"] = notification_id
                else:
                    stage["tasks"] = [t for t in stage["tasks"] if t is not task]
                    # 任务被移除后阶段就空了。空阶段会让前端「保存」直接拒绝
                    # （阶段没有任务），所以整段一起删掉。
                    if not stage["tasks"]:
                        stages.remove(stage)
                return
    if not notification_id:
        return
    stages.append({
        "id": f"stage-notify-{int(time.time() * 1000)}",
        "title": "发送通知",
        "tasks": [{
            "id": f"task-notify-{int(time.time() * 1000)}",
            "type": "Notify",
            "title": "发送通知",
            "input": {"notificationId": notification_id, "title": "证书任务执行结果",
                      "onlyOnError": False},
            "continueOnError": True,
        }],
    })


def _set_pipeline_cron(content: dict, cron: str) -> None:
    """设置定时触发：空 cron 表示移除定时器。"""
    triggers = [t for t in (content.get("triggers") or [])
                if t.get("type") != "timer"]
    if cron:
        triggers.append({"id": f"trigger-timer-{int(time.time() * 1000)}",
                         "type": "timer", "cron": cron, "enabled": True})
    content["triggers"] = triggers


def _sync_next_run(p) -> None:
    """按流水线当前的定时器重算下次执行时间。

    保存 / 批量设置定时之后立刻算出来，列表里就不用等调度器下一轮 tick。
    """
    try:
        content = json.loads(p.content or "{}")
    except Exception:  # noqa: BLE001
        p.next_run_time = None
        return
    if p.disabled:
        p.next_run_time = None
        return
    times = [
        t for t in (
            next_run(tr.get("cron", ""))
            for tr in (content.get("triggers") or [])
            if tr.get("type") == "timer" and tr.get("enabled", True)
        ) if t
    ]
    p.next_run_time = min(times) if times else None


@router.post("/batch")
def batch_action(body: dict, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """批量操作：run / enable / disable / delete / notify / cron

    逐条执行并返回每条结果，单条失败不影响其余条目。
    """
    action = (body or {}).get("action", "")
    ids = [int(i) for i in (body or {}).get("ids", []) if str(i).isdigit()]
    if not ids:
        return fail("请选择要操作的流水线")
    if action not in ("run", "enable", "disable", "delete", "notify", "cron"):
        return fail("不支持的操作类型")

    notification_id = int((body or {}).get("notificationId") or 0)
    cron = ((body or {}).get("cron") or "").strip()
    if action == "cron" and cron and not next_run(cron):
        return fail("cron 表达式不合法，示例：0 3 * * *（每天 3 点）")

    rows = db.query(Pipeline).filter(Pipeline.id.in_(ids),
                                     Pipeline.user_id == user.id).all()
    found = {r.id: r for r in rows}

    success, failed = [], []
    for pid in ids:
        p = found.get(pid)
        if not p:
            failed.append({"id": pid, "msg": "流水线不存在"})
            continue
        try:
            if action == "run":
                if is_running(p.id):
                    failed.append({"id": pid, "title": p.title, "msg": "正在运行中"})
                    continue
                run_pipeline_async(p.id, "manual", user.id)
            elif action in ("enable", "disable"):
                p.disabled = action == "disable"
                _sync_next_run(p)
            elif action == "notify":
                content = json.loads(p.content or "{}")
                _set_pipeline_notify(content, notification_id)
                p.content = json.dumps(content, ensure_ascii=False)
            elif action == "cron":
                content = json.loads(p.content or "{}")
                _set_pipeline_cron(content, cron)
                p.content = json.dumps(content, ensure_ascii=False)
                # 顺手把下次执行时间算出来，否则列表里要等调度器下一轮 tick 才更新
                _sync_next_run(p)
            elif action == "delete":
                if is_running(p.id):
                    failed.append({"id": pid, "title": p.title, "msg": "正在运行中，无法删除"})
                    continue
                db.query(History).filter(History.pipeline_id == p.id).delete()
                db.delete(p)
            success.append({"id": pid, "title": p.title})
        except Exception as exc:  # noqa: BLE001
            failed.append({"id": pid, "title": p.title, "msg": str(exc)})

    db.commit()
    label = {"run": "运行", "enable": "启用", "disable": "停用", "delete": "删除",
             "notify": "设置通知", "cron": "设置定时"}[action]
    audit(db, user, "批量" + label + "流水线",
          "成功 %d 条，失败 %d 条" % (len(success), len(failed)))
    return ok({"success": success, "failed": failed})


@router.post("/from-template")
def create_from_template(body: dict, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """按模板创建流水线，支持同时改标题"""
    from ..templates import find_template

    tpl = find_template((body or {}).get("templateId", ""))
    if not tpl:
        return fail("模板不存在")
    title = ((body or {}).get("title") or "").strip() or tpl["name"]
    p = Pipeline(user_id=user.id, title=title, type="cert_apply",
                 content=json.dumps(tpl["content"], ensure_ascii=False),
                 remark=tpl["desc"], keep_history_count=20, disabled=False)
    db.add(p)
    db.commit()
    db.refresh(p)
    audit(db, user, "按模板创建流水线", f"{tpl['name']} → {title}")
    return ok({"id": p.id, "title": p.title})


@router.post("/gen-key")
def gen_trigger_key(_: User = Depends(get_current_user)):
    return ok({"key": uuid.uuid4().hex})
