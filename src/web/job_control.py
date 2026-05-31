from __future__ import annotations

from typing import Any, Callable


def job_stop_requested(
    job_id: str,
    *,
    read_job: Callable[[str], dict[str, Any]],
    safe_str: Callable[[Any, str], str],
) -> bool:
    # 统一判断任务是否被请求停止，避免 app.py 重复读取 job 状态。
    token = safe_str(job_id)
    if not token:
        return False
    try:
        job = read_job(token)
    except Exception:
        return False
    status = safe_str(job.get("status")).lower()
    if status in {"stopping", "stopped", "cancelled", "canceled"}:
        return True
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    return bool(result.get("stop_requested"))


def job_pause_requested(
    job_id: str,
    *,
    read_job: Callable[[str], dict[str, Any]],
    safe_str: Callable[[Any, str], str],
) -> bool:
    # 暂停只依赖 job 当前状态，单独抽成 helper 方便后台任务复用。
    token = safe_str(job_id)
    if not token:
        return False
    try:
        job = read_job(token)
    except Exception:
        return False
    status = safe_str(job.get("status")).lower()
    return status in {"paused", "pause"}


def sync_control_progress(
    result: dict[str, Any],
    *,
    phase: str,
    stop_requested: bool,
    safe_str: Callable[[Any, str], str],
) -> dict[str, Any]:
    # 保留已有 progress 字段，只覆盖同步阶段和停止标记。
    progress = result.get("progress") if isinstance(result.get("progress"), dict) else {}
    merged = dict(progress)
    merged["phase"] = safe_str(phase, "running")
    merged["stop_requested"] = bool(stop_requested)
    return merged


def request_capture_job_control(
    job_id: str,
    action: str,
    *,
    read_job: Callable[[str], dict[str, Any]],
    update_job: Callable[..., dict[str, Any]],
    append_log: Callable[[str, str], None],
    safe_str: Callable[[Any, str], str],
    normalize_sync_status: Callable[[Any], str],
    module2_request_capture_job_step: str,
    sync_control_progress: Callable[..., dict[str, Any]],
) -> None:
    # 父同步任务需要控制子抓包任务的暂停、恢复和停止，这里统一收口。
    token = safe_str(job_id)
    mode = safe_str(action).lower()
    if not token or mode not in {"stop", "pause", "resume"}:
        return

    try:
        job = read_job(token)
    except Exception:
        return

    if safe_str(job.get("step")) != module2_request_capture_job_step:
        return

    current_status = normalize_sync_status(job.get("status"))
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    merged_result = dict(result)
    progress = merged_result.get("progress") if isinstance(merged_result.get("progress"), dict) else {}
    phase = safe_str(progress.get("phase"), "capturing")

    if mode == "pause":
        if current_status != "running":
            return
        merged_result["stop_requested"] = bool(merged_result.get("stop_requested"))
        merged_result["progress"] = sync_control_progress(
            merged_result,
            phase=phase,
            stop_requested=bool(merged_result.get("stop_requested")),
        )
        try:
            update_job(job_id=token, status="paused", result=merged_result)
            append_log(token, "pause requested by parent sync job")
        except Exception:
            return
        return

    if mode == "resume":
        if current_status != "paused":
            return
        merged_result["stop_requested"] = False
        merged_result["progress"] = sync_control_progress(
            merged_result,
            phase=phase,
            stop_requested=False,
        )
        try:
            update_job(job_id=token, status="running", result=merged_result)
            append_log(token, "resume requested by parent sync job")
        except Exception:
            return
        return

    if current_status in {"done", "failed", "stopped"}:
        return
    merged_result["stop_requested"] = True
    merged_result["progress"] = sync_control_progress(
        merged_result,
        phase=phase,
        stop_requested=True,
    )
    try:
        if current_status in {"queued", "paused"}:
            update_job(job_id=token, status="stopped", result=merged_result)
        else:
            update_job(job_id=token, status="running", result=merged_result)
        append_log(token, "stop requested by parent sync job")
    except Exception:
        return
