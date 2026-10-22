"""Train callbot sau khi duyệt – lô train, job, trạng thái (thiết kế: docs/01_THIET_KE_TRAIN_BOT.md).

Bot "biết" bản nào của thủ tục: procedures.trained_hash (băm nội dung đã train thành công). So với băm nội dung hiện tại:
  Cần train = đã duyệt và băm khác · Cần xoá = đã gỡ khỏi cổng mà bot còn giữ · Chờ duyệt = chưa duyệt (bot giữ bản cũ).
Lô train chụp lại nội dung lúc tạo; một tỉnh chỉ một lô đang hoạt động; chỉ SUCCEEDED mới cập nhật trained_hash.
Bộ kết nối: MockIccProvider (API giả lập cms/mock_icc) – thay bằng IccProvider khi iCC cung cấp API thật.
"""
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta

from . import core

STATUS_VI = {"DRAFT": "Chờ gửi", "SUBMITTED": "Đã gửi", "QUEUED": "Xếp hàng", "TRAINING": "Đang train", "SUCCEEDED": "Train xong",
             "FAILED": "Lỗi", "CANCELLED": "Đã huỷ"}
ACTIVE = ("SUBMITTED", "QUEUED", "TRAINING")
FINAL = ("SUCCEEDED", "FAILED", "CANCELLED")
TIMEOUT = timedelta(hours=float(os.environ.get("CMS_TRAIN_TIMEOUT_HOURS", "2")))

SCHEMA = """
CREATE TABLE IF NOT EXISTS training_batches (id TEXT PRIMARY KEY, province TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
  progress INTEGER DEFAULT 0, remote_job_id TEXT, provider TEXT, bot_id TEXT, upserts INTEGER, deletes INTEGER, rows INTEGER,
  created_by TEXT, created_at TEXT, submitted_by TEXT, submitted_at TEXT, started_at TEXT, finished_at TEXT, last_update TEXT,
  message TEXT, error TEXT, attempt INTEGER DEFAULT 1, parent_id TEXT);
CREATE TABLE IF NOT EXISTS training_items (batch_id TEXT NOT NULL, fid TEXT NOT NULL, action TEXT NOT NULL, content_hash TEXT,
  name TEXT, code TEXT, rows INTEGER, payload TEXT, PRIMARY KEY (batch_id, fid));
CREATE TABLE IF NOT EXISTS training_events (id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL, at TEXT, status TEXT,
  progress INTEGER, source TEXT, message TEXT);
"""


def init(c):
    c.executescript(SCHEMA)
    cols = {r[1] for r in c.execute("PRAGMA table_info(procedures)")}
    for col in ("trained_hash", "trained_batch", "trained_at"):
        if col not in cols:
            c.execute(f"ALTER TABLE procedures ADD COLUMN {col} TEXT")


# ------------------------------------------------------------------ bộ kết nối
class ProviderError(core.CmsError):
    """Bên bot (iCC) từ chối / không kết nối được."""


class MockIccProvider:
    name = "mock-icc"

    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/"), key

    def _call(self, method, path, body=None):
        r = urllib.request.Request(self.url + path, method=method, data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                                   headers={"Content-Type": "application/json", "X-Api-Key": self.key})
        try:
            with urllib.request.urlopen(r, timeout=30) as x:
                return json.loads(x.read())
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read()).get("detail")
            except ValueError:
                detail = ""
            raise ProviderError(f"iCC trả lỗi {e.code}: {detail or e.reason}")
        except OSError as e:
            raise ProviderError(f"Không kết nối được iCC ({self.url}): {e}")

    def submit(self, bot_id, items, callback_url=None, reference=None):
        return self._call("POST", f"/api/v1/bots/{bot_id}/train-jobs", {"items": items, "callback_url": callback_url, "reference": reference})

    def status(self, job_id):
        return self._call("GET", f"/api/v1/train-jobs/{job_id}")

    def cancel(self, job_id):
        return self._call("POST", f"/api/v1/train-jobs/{job_id}/cancel")

    def knowledge(self, bot_id):
        return self._call("GET", f"/api/v1/bots/{bot_id}/knowledge")


_provider_override = None


def provider():
    """Theo biến môi trường; khoá chỉ ở môi trường, không vào CSDL / nhật ký."""
    if _provider_override:
        return _provider_override
    kind = os.environ.get("CMS_TRAIN_PROVIDER", "mock")
    if kind != "mock":
        raise core.CmsError(f"Chưa có bộ kết nối '{kind}' – iCC chưa cung cấp API train thật (xem docs/01_THIET_KE_TRAIN_BOT.md)")
    return MockIccProvider(os.environ.get("CMS_TRAIN_URL", "http://127.0.0.1:8790"), os.environ.get("CMS_TRAIN_API_KEY", "mock-key"))


def bot_id(code):
    return os.environ.get(f"CMS_TRAIN_BOT_{code}", f"callbot-tthc-{code.lower()}")


def config():
    kind = os.environ.get("CMS_TRAIN_PROVIDER", "mock")
    return {"provider": kind, "mock": kind == "mock", "url": os.environ.get("CMS_TRAIN_URL", "http://127.0.0.1:8790"),
            "callback": bool(os.environ.get("CMS_PUBLIC_URL"))}


# ------------------------------------------------------------------ trạng thái train của thủ tục
def _hash(rows):
    blob = json.dumps([[r["title"], r["content"] or "", r["questions"] or "", r["tags"] or ""] for r in rows], ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def _rows_by_fid(c, code, fids):
    """Dòng nội dung của các thủ tục chỉ định (đọc theo từng nhóm, không quét cả tỉnh)."""
    out, fids = {}, list(fids)
    for i in range(0, len(fids), 500):
        part = fids[i:i + 500]
        for r in c.execute(f"SELECT fid, title, content, questions, tags FROM rows WHERE province=? AND fid IN ({','.join('?' * len(part))})"
                           " ORDER BY fid, seq", (code, *part)):
            out.setdefault(r["fid"], []).append(dict(r))
    return out


def plan(c, code, with_rows=False):
    """Danh sách cần train / cần xoá ngay lúc này. Băm nội dung lấy từ procedures.content_hash (tính lại khi nội dung đổi)."""
    procs = c.execute("SELECT fid, name, code, status, review, trained_hash, content_hash FROM procedures WHERE province=?", (code,)).fetchall()
    approved = [p for p in procs if p["status"] == "ACTIVE" and p["review"] == "APPROVED"]
    stale = [p["fid"] for p in approved if not p["content_hash"]]
    hashes = {p["fid"]: p["content_hash"] for p in approved}
    if stale:
        for fid, rs in _rows_by_fid(c, code, stale).items():
            hashes[fid] = _hash(rs)
            c.execute("UPDATE procedures SET content_hash=? WHERE province=? AND fid=?", (hashes[fid], code, fid))
        c.commit()
    need = [p["fid"] for p in approved if hashes.get(p["fid"]) != p["trained_hash"]]
    rows = _rows_by_fid(c, code, need) if with_rows else {}
    upserts, synced, waiting, deletes = [], 0, 0, []
    for p in procs:
        if p["status"] == "REMOVED":
            if p["trained_hash"]:
                deletes.append({"fid": p["fid"], "name": p["name"], "code": p["code"]})
            continue
        if p["review"] != "APPROVED":
            waiting += 1
            continue
        h = hashes.get(p["fid"])
        if h == p["trained_hash"]:
            synced += 1
        else:
            upserts.append({"fid": p["fid"], "name": p["name"], "code": p["code"], "hash": h, "rows": rows.get(p["fid"], []),
                            "n_rows": len(rows[p["fid"]]) if with_rows else None, "first_time": not p["trained_hash"]})
    return {"upserts": upserts, "deletes": deletes, "synced": synced, "waiting_review": waiting,
            "trained_any": sum(1 for p in procs if p["trained_hash"])}


def summary(c, code):
    p = plan(c, code)
    act = c.execute(f"SELECT id FROM training_batches WHERE province=? AND status IN ({','.join('?' * len(ACTIVE))})", (code, *ACTIVE)).fetchone()
    last = c.execute("SELECT id, status, finished_at FROM training_batches WHERE province=? AND status='SUCCEEDED' ORDER BY finished_at DESC LIMIT 1",
                     (code,)).fetchone()
    return {"need_train": len(p["upserts"]), "need_delete": len(p["deletes"]), "synced": p["synced"], "waiting_review": p["waiting_review"],
            "on_bot": p["trained_any"], "active_batch": act[0] if act else None, "last_success": dict(last) if last else None,
            "bot_id": bot_id(code), **config()}


# ------------------------------------------------------------------ lô train
def _event(c, bid, status, progress, source, message=""):
    c.execute("INSERT INTO training_events(batch_id, at, status, progress, source, message) VALUES (?,?,?,?,?,?)",
              (bid, core.now(), status, progress, source, (message or "")[:1000]))


def _new_id(c, code):
    day = datetime.now().strftime("%Y%m%d")
    n = c.execute("SELECT COUNT(*) FROM training_batches WHERE id LIKE ?", (f"TB-{code}-{day}-%",)).fetchone()[0]
    return f"TB-{code}-{day}-{n + 1:03d}"


def create_batch(c, code, actor, parent_id=None):
    actor = core._actor(actor)
    code = core.province(c, code)["code"]
    if c.execute(f"SELECT 1 FROM training_batches WHERE province=? AND status IN ('DRAFT', {','.join('?' * len(ACTIVE))})",
                 (code, *ACTIVE)).fetchone():
        raise core.CmsError("Đã có lô chờ gửi / đang train cho tỉnh này – gửi hoặc huỷ lô đó trước")
    p = plan(c, code, with_rows=True)
    if not p["upserts"] and not p["deletes"]:
        raise core.CmsError("Không có gì cần train: mọi thủ tục đã duyệt đều đã train đúng bản" +
                            (f" ({p['waiting_review']} thủ tục còn chờ duyệt)" if p["waiting_review"] else ""))
    bid = _new_id(c, code)
    attempt = 1
    if parent_id:
        attempt = (c.execute("SELECT attempt FROM training_batches WHERE id=?", (parent_id,)).fetchone() or [0])[0] + 1
    n_rows = sum(len(u["rows"]) for u in p["upserts"])
    c.execute("INSERT INTO training_batches(id, province, mode, status, upserts, deletes, rows, created_by, created_at, attempt, parent_id, bot_id,"
              " last_update) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (bid, code, "DELTA", "DRAFT", len(p["upserts"]), len(p["deletes"]), n_rows, actor, core.now(), attempt, parent_id, bot_id(code), core.now()))
    c.executemany("INSERT INTO training_items(batch_id, fid, action, content_hash, name, code, rows, payload) VALUES (?,?,?,?,?,?,?,?)",
                  [(bid, u["fid"], "UPSERT", u["hash"], u["name"], u["code"], len(u["rows"]),
                    json.dumps([{k: r[k] for k in ("title", "content", "questions", "tags")} for r in u["rows"]], ensure_ascii=False))
                   for u in p["upserts"]] + [(bid, d["fid"], "DELETE", None, d["name"], d["code"], 0, "[]") for d in p["deletes"]])
    _event(c, bid, "DRAFT", 0, "USER", f"{actor} tạo lô: {len(p['upserts'])} cập nhật, {len(p['deletes'])} xoá, {n_rows} dòng")
    core.audit(c, actor, "train_batch_create", code, detail=f"{bid}: {len(p['upserts'])} cập nhật, {len(p['deletes'])} xoá")
    return batch(c, bid)


def batch(c, bid, items=False):
    r = c.execute("SELECT * FROM training_batches WHERE id=?", (bid,)).fetchone()
    if not r:
        raise core.CmsError(f"Không có lô {bid}")
    b = dict(r)
    b["status_vi"] = STATUS_VI[b["status"]]
    b["events"] = [dict(e) for e in c.execute("SELECT at, status, progress, source, message FROM training_events WHERE batch_id=? ORDER BY id", (bid,))]
    if items:
        b["items"] = [dict(i) for i in c.execute("SELECT fid, action, name, code, rows FROM training_items WHERE batch_id=? ORDER BY action, name", (bid,))]
    return b


def batches(c, code, limit=50):
    return [{**dict(r), "status_vi": STATUS_VI[r["status"]]} for r in
            c.execute("SELECT * FROM training_batches WHERE province=? ORDER BY created_at DESC LIMIT ?", (code, limit))]


def submit(bid, actor, prov=None):
    """Gửi lô sang bot. Gọi mạng NGOÀI giao dịch CSDL; ghi kết quả sau."""
    actor = core._actor(actor)
    prov = prov or provider()
    with closing(core.connect()) as c:
        b = batch(c, bid)
        if b["status"] != "DRAFT":
            raise core.CmsError(f"Lô đang {STATUS_VI[b['status']]} – chỉ gửi được lô Chờ gửi")
        if c.execute(f"SELECT 1 FROM training_batches WHERE province=? AND id<>? AND status IN ({','.join('?' * len(ACTIVE))})",
                     (b["province"], bid, *ACTIVE)).fetchone():
            raise core.CmsError("Tỉnh này đang có lô train chạy – chờ xong")
        items = [{"fid": i["fid"], "action": i["action"], "rows": json.loads(i["payload"] or "[]")}
                 for i in c.execute("SELECT fid, action, payload FROM training_items WHERE batch_id=?", (bid,))]
    cb = os.environ.get("CMS_PUBLIC_URL")
    try:
        r = prov.submit(b["bot_id"], items, callback_url=f"{cb.rstrip('/')}/api/training/callback" if cb else None, reference=bid)
    except ProviderError as e:
        with closing(core.connect()) as c, c:
            c.execute("UPDATE training_batches SET error=?, last_update=? WHERE id=?", (str(e), core.now(), bid))
            _event(c, bid, "DRAFT", 0, "SYSTEM", f"Gửi lỗi: {e}")
        raise
    with closing(core.connect()) as c, c:
        c.execute("UPDATE training_batches SET status='SUBMITTED', remote_job_id=?, provider=?, submitted_by=?, submitted_at=?, error=NULL,"
                  " message=?, last_update=? WHERE id=?", (r["job_id"], prov.name, actor, core.now(), r.get("message"), core.now(), bid))
        _event(c, bid, "SUBMITTED", 0, "USER", f"{actor} gửi – job {r['job_id']}")
        core.audit(c, actor, "train_submit", b["province"], detail=f"{bid} -> job {r['job_id']}")
        _apply(c, bid, r, "SUBMIT")
        return batch(c, bid)


def _apply(c, bid, st, source):
    """Áp trạng thái job nhận được (poll / callback). Chỉ ghi sự kiện khi trạng thái hoặc tiến độ đổi."""
    b = batch(c, bid)
    if b["status"] in FINAL:
        return b
    s = st.get("status")
    if s not in ("QUEUED", "TRAINING", "SUCCEEDED", "FAILED", "CANCELLED"):
        return b
    prog = int(st.get("progress") or 0)
    if s == b["status"] and prog == b["progress"]:
        c.execute("UPDATE training_batches SET last_update=? WHERE id=?", (core.now(), bid))
        return b
    c.execute("UPDATE training_batches SET status=?, progress=?, message=?, started_at=COALESCE(started_at, ?), finished_at=?, error=?, last_update=?"
              " WHERE id=?", (s, prog, st.get("message"), st.get("started_at") if s != "QUEUED" else None,
                              st.get("finished_at") or (core.now() if s in FINAL else None), st.get("message") if s == "FAILED" else None,
                              core.now(), bid))
    _event(c, bid, s, prog, source, st.get("message") or "")
    if s == "SUCCEEDED":
        now = core.now()
        for i in c.execute("SELECT fid, action, content_hash FROM training_items WHERE batch_id=?", (bid,)).fetchall():
            c.execute("UPDATE procedures SET trained_hash=?, trained_batch=?, trained_at=? WHERE province=? AND fid=?",
                      (i["content_hash"] if i["action"] == "UPSERT" else None, bid, now, b["province"], i["fid"]))
        core.audit(c, "iCC", "train_succeeded", b["province"], detail=f"{bid}: bot đã train {b['upserts']} cập nhật, {b['deletes']} xoá")
    elif s == "FAILED":
        core.audit(c, "iCC", "train_failed", b["province"], detail=f"{bid}: {st.get('message')}")
    return batch(c, bid)


def refresh(bid, prov=None, source="POLL"):
    """Hỏi trạng thái job ngay (nút "Cập nhật" hoặc luồng nền). Quá TIMEOUT không tiến triển -> FAILED."""
    prov = prov or provider()
    with closing(core.connect()) as c:
        b = batch(c, bid)
    if b["status"] not in ACTIVE or not b["remote_job_id"]:
        return b
    try:
        st = prov.status(b["remote_job_id"])
    except ProviderError as e:
        st = None
        err = str(e)
    with closing(core.connect()) as c, c:
        if st is None:
            started = datetime.fromisoformat(b["submitted_at"])
            if datetime.now() - started > TIMEOUT:
                return _apply(c, bid, {"status": "FAILED", "progress": b["progress"], "message": f"TIMEOUT – không liên lạc được iCC: {err}"}, "SYSTEM")
            c.execute("UPDATE training_batches SET message=?, last_update=? WHERE id=?", (f"Không hỏi được trạng thái: {err}", core.now(), bid))
            return batch(c, bid)
        if st.get("status") in ("QUEUED", "TRAINING") and datetime.now() - datetime.fromisoformat(b["submitted_at"]) > TIMEOUT:
            st = {**st, "status": "FAILED", "message": f"TIMEOUT – quá {TIMEOUT} chưa xong"}
        return _apply(c, bid, st, source)


def cancel(bid, actor, prov=None):
    actor = core._actor(actor)
    with closing(core.connect()) as c:
        b = batch(c, bid)
    if b["status"] == "DRAFT":
        pass
    elif b["status"] in ("SUBMITTED", "QUEUED"):
        (prov or provider()).cancel(b["remote_job_id"])
    else:
        raise core.CmsError(f"Không huỷ được lô đang {STATUS_VI[b['status']]}")
    with closing(core.connect()) as c, c:
        c.execute("UPDATE training_batches SET status='CANCELLED', finished_at=?, last_update=? WHERE id=?", (core.now(), core.now(), bid))
        _event(c, bid, "CANCELLED", b["progress"], "USER", f"{actor} huỷ")
        core.audit(c, actor, "train_cancel", b["province"], detail=bid)
        return batch(c, bid)


def retry(bid, actor):
    """Gửi lại sau lỗi / huỷ: tạo lô mới từ những gì CÒN cần train lúc này."""
    with closing(core.connect()) as c, c:
        b = batch(c, bid)
        if b["status"] not in ("FAILED", "CANCELLED"):
            raise core.CmsError("Chỉ gửi lại lô Lỗi / Đã huỷ")
        return create_batch(c, b["province"], actor, parent_id=bid)


def callback(body: bytes, signature: str):
    """iCC gọi lại khi job đổi trạng thái. Kiểm chữ ký HMAC-SHA256."""
    secret = os.environ.get("CMS_TRAIN_CALLBACK_SECRET", "mock-secret" if config()["mock"] else "")
    if not secret or not hmac.compare_digest(hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), signature or ""):
        raise core.CmsError("Chữ ký callback không hợp lệ")
    st = json.loads(body)
    with closing(core.connect()) as c, c:
        r = c.execute("SELECT id FROM training_batches WHERE remote_job_id=?", (st.get("job_id"),)).fetchone()
        if not r:
            raise core.CmsError("Không có lô ứng với job này")
        return _apply(c, r[0], st, "CALLBACK")


# ------------------------------------------------------------------ luồng nền theo dõi job
_poller = None


def start_poller(interval=5.0):
    global _poller
    if _poller and _poller.is_alive():
        return

    def loop():
        while True:
            try:
                with closing(core.connect()) as c:
                    core.init(c)
                    init(c)
                    c.commit()
                    ids = [r[0] for r in c.execute(f"SELECT id FROM training_batches WHERE status IN ({','.join('?' * len(ACTIVE))})", ACTIVE)]
                for bid in ids:
                    try:
                        refresh(bid)
                    except core.CmsError:
                        pass
            except Exception:  # noqa: BLE001 – luồng nền không được chết
                pass
            time.sleep(interval)

    _poller = threading.Thread(target=loop, daemon=True, name="train-poller")
    _poller.start()
