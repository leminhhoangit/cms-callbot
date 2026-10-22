"""CMS dữ liệu Callbot TTHC – API JSON (FastAPI) + giao diện React / Ant Design build sẵn ở app/static (không cần Node khi chạy).

Chạy:  cms\\start_cms.bat   (hoặc  .venv\\Scripts\\python -m uvicorn app.main:app --port 8780  trong thư mục cms)
Người thao tác: header X-Actor (giao diện gửi tên đã nhập, mã hoá URL). MVP chưa đăng nhập – chờ chốt SSO / phân quyền.
"""
import os
from contextlib import closing
from typing import Optional
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import core, source, sync, training

app = FastAPI(title="CMS dữ liệu Callbot TTHC")
STATIC = os.path.join(os.path.dirname(__file__), "static")


def conn():
    c = core.connect()
    core.init(c)
    training.init(c)
    sync.init(c)
    return c


@app.on_event("startup")
def _start_poller():
    if not os.environ.get("CMS_NO_POLLER"):
        training.start_poller()
        sync.start_scheduler()


def actor(req: Request):
    return unquote(req.headers.get("x-actor", ""))[:80]


def run(fn, write=True):
    """Một giao dịch; lỗi nghiệp vụ -> 400 với câu báo cho người dùng."""
    try:
        with closing(conn()) as c:
            if not write:
                return fn(c)
            with c:
                return fn(c)
    except core.CmsError as e:
        raise HTTPException(400, str(e))


def _prov(c, code):
    return core.province(c, code)["code"]


# ------------------------------------------------------------------ tỉnh / tổng quan
@app.get("/api/health")
def api_health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    return {"review": core.REVIEW_VI, "change": core.CHANGE_VI, "export": core.EXPORT_VI, "province_fields": list(core.PROV_FIELDS)}


@app.get("/api/provinces")
def provinces():
    def f(c):
        has = {r[0] for r in c.execute("SELECT DISTINCT province FROM procedures")}
        return {"provinces": [{**p, "stats": core.stats(c, p["code"]) if p["code"] in has else None} for p in core.provinces(c)],
                "raws": core.raw_files(), "jobs": source.jobs()[:5]}
    return run(f, write=False)


@app.get("/api/p/{code}")
def province(code: str):
    def f(c):
        pc = _prov(c, code)
        return {"province": core.province(c, pc), "stats": core.stats(c, pc), "categories": core.categories(c, pc)}
    return run(f, write=False)


class SettingsIn(BaseModel):
    display: Optional[str] = Field(None, max_length=200)
    short: Optional[str] = Field(None, max_length=120)
    ubnd: Optional[str] = Field(None, max_length=200)
    in_phrase: Optional[str] = Field(None, max_length=200)
    center_address: Optional[str] = Field(None, max_length=3000)
    file_prefix: Optional[str] = Field(None, max_length=6)
    with_conditions: Optional[bool] = None


@app.put("/api/p/{code}/settings")
def save_settings(code: str, body: SettingsIn, request: Request):
    return run(lambda c: core.update_province(c, code, actor(request), **body.model_dump()))


@app.post("/api/p/{code}/rebuild")
def rebuild(code: str, request: Request):
    return run(lambda c: core.rebuild(c, code, actor(request)))


# ------------------------------------------------------------------ thủ tục
@app.get("/api/p/{code}/procedures")
def procedures(code: str, q: str = "", review: str = "", change: str = "", category: str = "", status: str = "ACTIVE", page: int = 1, size: int = 50):
    size = max(10, min(size, 200))
    return run(lambda c: core.search(c, _prov(c, code), q, review, change, category, status, page, size), write=False)


@app.get("/api/p/{code}/t/{fid}")
def procedure(code: str, fid: str):
    return run(lambda c: core.procedure(c, _prov(c, code), fid), write=False)


class RowEdit(BaseModel):
    seq: int
    questions: str = Field("", max_length=4000)
    tags: str = Field("", max_length=1000)


class RowsIn(BaseModel):
    edits: list[RowEdit] = Field(..., max_length=500)


@app.put("/api/p/{code}/t/{fid}/rows")
def edit_rows(code: str, fid: str, body: RowsIn, request: Request):
    def f(c):
        n = core.edit_rows(c, _prov(c, code), fid, actor(request), {e.seq: (e.questions, e.tags) for e in body.edits})
        return {"changed": n, "procedure": core.procedure(c, _prov(c, code), fid)}
    return run(f)


@app.post("/api/p/{code}/t/{fid}/suggest")
def suggest(code: str, fid: str, request: Request):
    def f(c):
        n = core.suggest_questions(c, _prov(c, code), fid, actor(request))
        return {"changed": n, "procedure": core.procedure(c, _prov(c, code), fid)}
    return run(f)


class ReviewIn(BaseModel):
    approve: bool = True


@app.post("/api/p/{code}/t/{fid}/review")
def review(code: str, fid: str, body: ReviewIn, request: Request):
    def f(c):
        core.set_review(c, _prov(c, code), fid, actor(request), body.approve)
        return core.procedure(c, _prov(c, code), fid)
    return run(f)


class BulkIn(BaseModel):
    fids: list[str] = Field(..., min_length=1, max_length=500)


@app.post("/api/p/{code}/review-bulk")
def review_bulk(code: str, body: BulkIn, request: Request):
    def f(c):
        for fid in body.fids:
            core.set_review(c, _prov(c, code), fid, actor(request), True)
        return {"approved": len(body.fids)}
    return run(f)


# ------------------------------------------------------------------ dữ liệu nguồn
@app.get("/api/p/{code}/data")
def data(code: str):
    def f(c):
        pc = _prov(c, code)
        return {"raws": core.raw_files(pc), "imports": core.imports(c, pc), "jobs": [j for j in source.jobs() if j["province"] == pc],
                "running": source.running()}
    return run(f, write=False)


class ImportIn(BaseModel):
    file: str = Field(..., max_length=200)


@app.post("/api/p/{code}/import")
def do_import(code: str, body: ImportIn, request: Request):
    return run(lambda c: core.import_raw(c, code, core.raw_path(body.file), actor(request), note="Nhập từ CMS"))


class CollectIn(BaseModel):
    limit: int = Field(0, ge=0, le=500)


@app.post("/api/p/{code}/collect")
def do_collect(code: str, body: CollectIn, request: Request):
    try:
        return source.start_collect(code, actor(request), limit=body.limit)
    except core.CmsError as e:
        raise HTTPException(400, str(e))


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    j = next((x for x in source.jobs() if x["id"] == job_id), None)
    if not j:
        raise HTTPException(404, "Không có lần thu thập này")
    return {**j, "log_tail": source.log_tail(job_id)}


@app.get("/api/source-health")
def source_health():
    with closing(conn()) as c:
        s = c.execute("SELECT fid FROM procedures LIMIT 1").fetchone()
    return {"checks": source.health(s[0] if s else None)}


# ------------------------------------------------------------------ xuất
@app.get("/api/p/{code}/exports")
def exports(code: str):
    def f(c):
        pc = _prov(c, code)
        return {"exports": core.exports(c, pc), "stats": core.stats(c, pc), "removed": core.search(c, pc, status="REMOVED", size=500)["items"]}
    return run(f, write=False)


class ExportIn(BaseModel):
    kind: str
    only_approved: bool = False


@app.post("/api/p/{code}/exports")
def do_export(code: str, body: ExportIn, request: Request):
    return run(lambda c: core.export(c, code.upper(), body.kind, actor(request), body.only_approved))


@app.get("/api/exports/{name}")
def download(name: str):
    try:
        return FileResponse(core.export_path(name), filename=os.path.basename(name),
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except core.CmsError:
        raise HTTPException(404, "Không có file")


@app.get("/api/audit")
def audit(limit: int = 300):
    return run(lambda c: {"rows": core.audit_log(c, max(1, min(limit, 2000)))}, write=False)


# ------------------------------------------------------------------ train callbot (docs/01_THIET_KE_TRAIN_BOT.md)
@app.get("/api/p/{code}/training")
def training_overview(code: str):
    def f(c):
        pc = _prov(c, code)
        return {"summary": training.summary(c, pc), "batches": training.batches(c, pc), "status_vi": training.STATUS_VI}
    return run(f, write=False)


@app.get("/api/p/{code}/training/plan")
def training_plan(code: str):
    def f(c):
        p = training.plan(c, _prov(c, code))
        return {"upserts": [{k: u[k] for k in ("fid", "name", "code", "first_time")} | {"rows": len(u["rows"])} for u in p["upserts"]],
                "deletes": p["deletes"], "synced": p["synced"], "waiting_review": p["waiting_review"]}
    return run(f, write=False)


@app.post("/api/p/{code}/training/batches")
def training_create(code: str, request: Request):
    return run(lambda c: training.create_batch(c, code, actor(request)))


@app.get("/api/training/batches/{bid}")
def training_batch(bid: str):
    return run(lambda c: training.batch(c, bid, items=True), write=False)


def _tr(fn):
    try:
        return fn()
    except core.CmsError as e:
        raise HTTPException(400, str(e))


@app.post("/api/training/batches/{bid}/submit")
def training_submit(bid: str, request: Request):
    return _tr(lambda: training.submit(bid, actor(request)))


@app.post("/api/training/batches/{bid}/refresh")
def training_refresh(bid: str):
    return _tr(lambda: training.refresh(bid, source="USER"))


@app.post("/api/training/batches/{bid}/cancel")
def training_cancel(bid: str, request: Request):
    return _tr(lambda: training.cancel(bid, actor(request)))


@app.post("/api/training/batches/{bid}/retry")
def training_retry(bid: str, request: Request):
    return _tr(lambda: training.retry(bid, actor(request)))


@app.post("/api/training/callback")
async def training_callback(request: Request):
    body = await request.body()
    try:
        b = training.callback(body, request.headers.get("x-signature", ""))
    except core.CmsError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "batch": b["id"], "status": b["status"]}


# ------------------------------------------------------------------ đồng bộ: chạy tay / theo lịch
@app.get("/api/p/{code}/sync")
def sync_overview(code: str):
    def f(c):
        pc = _prov(c, code)
        return {"config": sync.config(c, pc), "runs": sync.runs(c, pc), "scopes": sync.SCOPE_VI, "freqs": sync.FREQ_VI, "run_status": sync.RUN_VI}
    return run(f, write=False)


class SyncConfigIn(BaseModel):
    mode: str = Field(..., pattern="^(MANUAL|SCHEDULE)$")
    scope: str = Field(..., pattern="^(TRAIN_ONLY|FULL_SYNC)$")
    freq: str = Field("MONTHLY", pattern="^(DAILY|WEEKLY|MONTHLY)$")
    at_time: str = Field("08:00", max_length=5)
    weekday: int = Field(0, ge=0, le=6)
    monthday: int = Field(1, ge=1, le=31)


@app.put("/api/p/{code}/sync")
def sync_save(code: str, body: SyncConfigIn, request: Request):
    return run(lambda c: sync.save_config(c, code, actor(request), **body.model_dump()))


class SyncRunIn(BaseModel):
    scope: Optional[str] = Field(None, pattern="^(TRAIN_ONLY|FULL_SYNC)$")


@app.post("/api/p/{code}/sync/run")
def sync_run(code: str, body: SyncRunIn, request: Request):
    return {"run_id": _tr(lambda: sync.start(code, actor(request), scope=body.scope))}


# ------------------------------------------------------------------ giao diện (build sẵn)
if os.path.isdir(os.path.join(STATIC, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC, "assets")), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    f = os.path.join(STATIC, path)
    if path and os.path.isfile(f):
        return FileResponse(f)
    index = os.path.join(STATIC, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return HTMLResponse("<h3>Chưa build giao diện</h3><p>Trong cms/web chạy: <code>npm install && npm run build</code></p>", status_code=503)
