"""API iCC GIẢ LẬP – nạp dữ liệu + train callbot (docs/01_THIET_KE_TRAIN_BOT.md mục 6).

iCC chưa cung cấp API train thật; máy giả lập này cho CMS phát triển + kiểm thử luồng lô train / trạng thái job.
Chạy:  .venv\\Scripts\\python -m uvicorn mock_icc.app:app --port 8790   (trong thư mục cms)
Cấu hình (biến môi trường):
  MOCK_ICC_API_KEY   khoá hợp lệ (mặc định "mock-key")      MOCK_QUEUE_SECONDS  thời gian xếp hàng (mặc định 3)
  MOCK_ROWS_PER_SEC  tốc độ train (mặc định 4000 dòng/giây)   MOCK_FAIL_RATE      xác suất lỗi 0..1 (mặc định 0)
  MOCK_CALLBACK_SECRET  khoá ký HMAC callback (mặc định "mock-secret")
Thủ tục có nội dung chứa "[[FAIL]]" -> job lỗi (để kiểm thử).
"""
import hashlib
import hmac
import json
import os
import random
import threading
import time
import urllib.request
import uuid
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="iCC giả lập – train callbot")
JOBS, KB = {}, {}            # job_id -> job ; bot_id -> {fid: rows}
LOCK = threading.Lock()


def _cfg(k, d):
    return type(d)(os.environ.get(k, d))


def _auth(key):
    if key != _cfg("MOCK_ICC_API_KEY", "mock-key"):
        raise HTTPException(401, "Sai API key")


def _now():
    return datetime.now().isoformat(timespec="seconds")


class Row(BaseModel):
    title: str
    content: str = ""
    questions: str | None = None
    tags: str | None = None


class Item(BaseModel):
    fid: str
    action: str = Field(..., pattern="^(UPSERT|DELETE)$")
    rows: list[Row] = Field(default_factory=list)


class JobIn(BaseModel):
    items: list[Item] = Field(..., min_length=1)
    callback_url: str | None = None
    reference: str | None = None          # mã lô bên CMS


def _public(j):
    return {k: j[k] for k in ("job_id", "bot_id", "reference", "status", "progress", "message", "created_at", "started_at", "finished_at",
                              "upserts", "deletes", "rows")}


def _callback(j):
    if not j.get("callback_url"):
        return
    body = json.dumps(_public(j), ensure_ascii=False).encode()
    sig = hmac.new(_cfg("MOCK_CALLBACK_SECRET", "mock-secret").encode(), body, hashlib.sha256).hexdigest()
    try:
        urllib.request.urlopen(urllib.request.Request(j["callback_url"], data=body, method="POST",
                                                      headers={"Content-Type": "application/json", "X-Signature": sig}), timeout=5)
    except OSError:
        pass                                    # bên nhận lỗi -> CMS vẫn có đường poll


def _set(j, **kw):
    with LOCK:
        j.update(kw)
    _callback(j)


def _run(j, items):
    time.sleep(_cfg("MOCK_QUEUE_SECONDS", 3.0))
    if j["status"] == "CANCELLED":
        return
    _set(j, status="TRAINING", started_at=_now(), progress=0, message="Đang train")
    total = max(j["rows"], 1)
    speed = max(_cfg("MOCK_ROWS_PER_SEC", 4000.0), 1.0)
    steps = 5
    fail = any("[[FAIL]]" in (r.content + (r.questions or "") + (r.tags or "")) for it in items for r in it.rows) \
        or random.random() < _cfg("MOCK_FAIL_RATE", 0.0)
    for i in range(1, steps + 1):
        time.sleep(total / speed / steps)
        if fail and i == 3:
            _set(j, status="FAILED", progress=60, finished_at=_now(), message="TRAIN_ERROR: nội dung không hợp lệ (giả lập)")
            return
        if i < steps:
            _set(j, progress=int(100 * i / steps))
    with LOCK:
        kb = KB.setdefault(j["bot_id"], {})
        for it in items:
            if it.action == "DELETE":
                kb.pop(it.fid, None)
            else:
                kb[it.fid] = [r.model_dump() for r in it.rows]
    _set(j, status="SUCCEEDED", progress=100, finished_at=_now(), message="Train xong")


@app.post("/api/v1/bots/{bot_id}/train-jobs")
def create_job(bot_id: str, body: JobIn, x_api_key: str = Header("")):
    _auth(x_api_key)
    with LOCK:
        if any(j["bot_id"] == bot_id and j["status"] in ("QUEUED", "TRAINING") for j in JOBS.values()):
            raise HTTPException(409, "Bot đang có job train chạy")
    j = {"job_id": "job_" + uuid.uuid4().hex[:12], "bot_id": bot_id, "reference": body.reference, "status": "QUEUED", "progress": 0,
         "message": "Đã nhận dữ liệu, chờ train", "created_at": _now(), "started_at": None, "finished_at": None,
         "upserts": sum(i.action == "UPSERT" for i in body.items), "deletes": sum(i.action == "DELETE" for i in body.items),
         "rows": sum(len(i.rows) for i in body.items), "callback_url": body.callback_url}
    JOBS[j["job_id"]] = j
    threading.Thread(target=_run, args=(j, body.items), daemon=True).start()
    return _public(j)


@app.get("/api/v1/train-jobs/{job_id}")
def get_job(job_id: str, x_api_key: str = Header("")):
    _auth(x_api_key)
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Không có job")
    return _public(j)


@app.post("/api/v1/train-jobs/{job_id}/cancel")
def cancel_job(job_id: str, x_api_key: str = Header("")):
    _auth(x_api_key)
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Không có job")
    if j["status"] != "QUEUED":
        raise HTTPException(409, f"Không huỷ được job đang {j['status']}")
    _set(j, status="CANCELLED", finished_at=_now(), message="Đã huỷ")
    return _public(j)


@app.get("/api/v1/bots/{bot_id}/knowledge")
def knowledge(bot_id: str, x_api_key: str = Header("")):
    _auth(x_api_key)
    kb = KB.get(bot_id, {})
    return {"bot_id": bot_id, "procedures": len(kb), "rows": sum(len(v) for v in kb.values())}


@app.get("/health")
def health():
    return {"status": "ok", "mock": True}
