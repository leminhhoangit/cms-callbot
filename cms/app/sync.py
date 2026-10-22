"""Đồng bộ dữ liệu DVC -> CMS -> train bot: chạy TAY hoặc THEO LỊCH, cấu hình theo từng tỉnh (docs/01_THIET_KE_TRAIN_BOT.md mục 9).

Phạm vi một lần chạy:
  TRAIN_ONLY  – gửi phần ĐÃ DUYỆT chưa lên bot (không tải cổng)
  FULL_SYNC   – kiểm tra cổng -> tải dữ liệu mới -> nhập + so sánh (Mới / Thay đổi -> Cần duyệt) -> train phần đã duyệt
Luật: lịch KHÔNG BAO GIỜ tự duyệt; tỉnh đang có lượt đồng bộ / lô train chạy -> bỏ qua (SKIPPED); không có gì cần train -> NO_CHANGE,
không tạo lô rỗng. Mỗi lượt ghi từng bước (thời điểm, kết quả) vào sync_runs. Lỡ giờ (CMS tắt) -> chạy bù 1 lần khi bật lại.
"""
import json
import threading
import time
from calendar import monthrange
from contextlib import closing
from datetime import datetime, timedelta

from . import core, source, training

SCOPE_VI = {"TRAIN_ONLY": "Chỉ train phần đã duyệt", "FULL_SYNC": "Đồng bộ đầy đủ (tải cổng DVC + nhập + train)"}
FREQ_VI = {"DAILY": "Hằng ngày", "WEEKLY": "Hằng tuần", "MONTHLY": "Hằng tháng"}
RUN_VI = {"RUNNING": "Đang chạy", "SUCCEEDED": "Thành công", "NO_CHANGE": "Không có gì cần train", "SKIPPED": "Bỏ qua", "FAILED": "Lỗi"}
SCHED_ACTOR = "Lịch tự động"
WAIT_TRAIN = 3 * 3600

SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_configs (province TEXT PRIMARY KEY, mode TEXT NOT NULL DEFAULT 'MANUAL', scope TEXT NOT NULL DEFAULT 'TRAIN_ONLY',
  freq TEXT NOT NULL DEFAULT 'MONTHLY', at_time TEXT NOT NULL DEFAULT '08:00', weekday INTEGER DEFAULT 0, monthday INTEGER DEFAULT 1,
  next_run_at TEXT, updated_by TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS sync_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, province TEXT NOT NULL, trigger TEXT NOT NULL, scope TEXT NOT NULL,
  status TEXT NOT NULL, actor TEXT, started_at TEXT, finished_at TEXT, steps TEXT, import_id INTEGER, batch_id TEXT, message TEXT);
"""


def init(c):
    c.executescript(SCHEMA)


def _cfg_row(c, code):
    r = c.execute("SELECT * FROM sync_configs WHERE province=?", (code,)).fetchone()
    return dict(r) if r else {"province": code, "mode": "MANUAL", "scope": "TRAIN_ONLY", "freq": "MONTHLY", "at_time": "08:00", "weekday": 0,
                              "monthday": 1, "next_run_at": None, "updated_by": None, "updated_at": None}


def next_run(cfg, now=None):
    """Lần chạy kế tiếp sau `now` theo tần suất (giờ máy chủ)."""
    now = now or datetime.now()
    hh, mm = (int(x) for x in cfg["at_time"].split(":"))
    if cfg["freq"] == "DAILY":
        t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return t if t > now else t + timedelta(days=1)
    if cfg["freq"] == "WEEKLY":
        t = now.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(days=(int(cfg["weekday"]) - now.weekday()) % 7)
        return t if t > now else t + timedelta(days=7)
    day = int(cfg["monthday"])
    y, m = now.year, now.month
    for _ in range(2):
        t = datetime(y, m, min(day, monthrange(y, m)[1]), hh, mm)
        if t > now:
            return t
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return t


def config(c, code):
    code = core.province(c, code)["code"]
    cfg = _cfg_row(c, code)
    return {**cfg, "mode_vi": "Theo lịch" if cfg["mode"] == "SCHEDULE" else "Chạy tay", "scope_vi": SCOPE_VI[cfg["scope"]], "freq_vi": FREQ_VI[cfg["freq"]]}


def save_config(c, code, actor, mode, scope, freq="MONTHLY", at_time="08:00", weekday=0, monthday=1):
    actor = core._actor(actor)
    code = core.province(c, code)["code"]
    if mode not in ("MANUAL", "SCHEDULE") or scope not in SCOPE_VI or freq not in FREQ_VI:
        raise core.CmsError("Cấu hình không hợp lệ")
    try:
        hh, mm = (int(x) for x in at_time.split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except (ValueError, AssertionError):
        raise core.CmsError("Giờ chạy dạng HH:MM")
    if not (0 <= int(weekday) <= 6) or not (1 <= int(monthday) <= 31):
        raise core.CmsError("Thứ 0–6 (Thứ Hai = 0), ngày 1–31")
    cfg = {"freq": freq, "at_time": f"{hh:02d}:{mm:02d}", "weekday": int(weekday), "monthday": int(monthday)}
    nxt = next_run(cfg).isoformat(timespec="seconds") if mode == "SCHEDULE" else None
    c.execute("INSERT INTO sync_configs(province, mode, scope, freq, at_time, weekday, monthday, next_run_at, updated_by, updated_at)"
              " VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(province) DO UPDATE SET mode=excluded.mode, scope=excluded.scope, freq=excluded.freq,"
              " at_time=excluded.at_time, weekday=excluded.weekday, monthday=excluded.monthday, next_run_at=excluded.next_run_at,"
              " updated_by=excluded.updated_by, updated_at=excluded.updated_at",
              (code, mode, scope, freq, cfg["at_time"], cfg["weekday"], cfg["monthday"], nxt, actor, core.now()))
    core.audit(c, actor, "sync_config", code, detail=("Theo lịch: " + FREQ_VI[freq] + f" {cfg['at_time']}, " if mode == "SCHEDULE" else "Chạy tay, ")
               + SCOPE_VI[scope])
    return config(c, code)


def runs(c, code, limit=50):
    out = []
    for r in c.execute("SELECT * FROM sync_runs WHERE province=? ORDER BY id DESC LIMIT ?", (code, limit)):
        d = dict(r)
        d["steps"] = json.loads(d["steps"] or "[]")
        d["status_vi"], d["scope_vi"] = RUN_VI[d["status"]], SCOPE_VI[d["scope"]]
        out.append(d)
    return out


# ------------------------------------------------------------------ một lượt đồng bộ
_LOCK = threading.Lock()


class _Run:
    def __init__(self, code, trigger, scope, actor):
        self.code, self.actor, self.steps = code, actor, []
        with closing(core.connect()) as c, c:
            self.id = c.execute("INSERT INTO sync_runs(province, trigger, scope, status, actor, started_at, steps) VALUES (?,?,?,?,?,?,?)",
                                (code, trigger, scope, "RUNNING", actor, core.now(), "[]")).lastrowid

    def step(self, name, ok, detail=""):
        self.steps.append({"at": core.now(), "step": name, "ok": ok, "detail": str(detail)[:500]})
        self._save()

    def _save(self, **kw):
        sets = ", ".join(["steps=?"] + [f"{k}=?" for k in kw])
        with closing(core.connect()) as c, c:
            c.execute(f"UPDATE sync_runs SET {sets} WHERE id=?", (json.dumps(self.steps, ensure_ascii=False), *kw.values(), self.id))

    def finish(self, status, message="", **kw):
        self._save(status=status, message=message[:1000], finished_at=core.now(), **kw)
        return status


def run(code, actor, trigger="MANUAL", scope=None, collect_runner=None, prov=None, wait_seconds=WAIT_TRAIN, poll=5.0):
    """Chạy một lượt (chặn đến khi xong). Trả id lượt chạy."""
    with closing(core.connect()) as c:
        code = core.province(c, code)["code"]
        scope = scope or _cfg_row(c, code)["scope"]
        busy = c.execute("SELECT id FROM sync_runs WHERE province=? AND status='RUNNING'", (code,)).fetchone()
    if scope not in SCOPE_VI:
        raise core.CmsError("Phạm vi không hợp lệ")
    r = _Run(code, trigger, scope, actor)
    if busy:
        r.step("Kiểm tra", False, f"Đang có lượt đồng bộ #{busy[0]} chạy")
        r.finish("SKIPPED", f"Bỏ qua – lượt #{busy[0]} đang chạy")
        return r.id
    try:
        with closing(core.connect()) as c:
            act = c.execute(f"SELECT id FROM training_batches WHERE province=? AND status IN ('DRAFT', {','.join('?' * len(training.ACTIVE))})",
                            (code, *training.ACTIVE)).fetchone()
        if act:
            r.step("Kiểm tra", False, f"Lô {act[0]} đang chờ gửi / đang train")
            r.finish("SKIPPED", f"Bỏ qua – lô {act[0]} chưa xong (gửi hoặc huỷ lô đó trước)")
            return r.id
        p = prov or training.provider()
        try:
            p.knowledge(training.bot_id(code))
            r.step("Kết nối bot", True, f"{p.name} · {training.bot_id(code)}")
        except training.ProviderError as e:
            r.step("Kết nối bot", False, e)
            return _end(r, "FAILED", f"Không kết nối được bot: {e}")
        import_id = None
        if scope == "FULL_SYNC":
            job = source.start_collect(code, actor, runner=collect_runner, wait=True)
            if job["status"] != "SUCCEEDED":
                r.step("Tải dữ liệu cổng DVC + nhập", False, job["error"])
                return _end(r, "FAILED", f"Đồng bộ cổng DVC lỗi: {job['error']}")
            im = job["result"]
            import_id = im["id"]
            r.step("Tải dữ liệu cổng DVC + nhập", True,
                   f"{im['procedures']} thủ tục – Mới {im['added']}, Thay đổi {im['changed']}, Đã gỡ {im['removed']} (Mới / Thay đổi chờ người duyệt)")
        with closing(core.connect()) as c, c:
            s = training.summary(c, code)
            r.step("Kiểm tra cần train", True, f"Cần train {s['need_train']}, cần xoá {s['need_delete']}, chờ duyệt {s['waiting_review']}")
            if not s["need_train"] and not s["need_delete"]:
                return _end(r, "NO_CHANGE", "Không có nội dung đã duyệt nào cần train", import_id=import_id)
            b = training.create_batch(c, code, actor)
        r.step("Tạo lô train", True, f"{b['id']}: {b['upserts']} cập nhật, {b['deletes']} xoá")
        sb = training.submit(b["id"], actor, prov=p)
        r.step("Gửi train", True, f"job {sb['remote_job_id']}")
        t0 = time.time()
        while True:
            cur = training.refresh(b["id"], prov=p)
            if cur["status"] in training.FINAL:
                break
            if time.time() - t0 > wait_seconds:
                r.step("Theo dõi job", False, f"Quá {wait_seconds // 60} phút – lô vẫn được theo dõi tự động")
                return _end(r, "SUCCEEDED", f"Đã gửi {b['id']}; chưa train xong khi hết thời gian chờ của lượt", import_id=import_id, batch_id=b["id"])
            time.sleep(poll)
        ok = cur["status"] == "SUCCEEDED"
        r.step("Train", ok, f"{training.STATUS_VI[cur['status']]} {cur['progress']}%" + (f" – {cur['error']}" if cur.get("error") else ""))
        return _end(r, "SUCCEEDED" if ok else "FAILED", f"Lô {b['id']}: {training.STATUS_VI[cur['status']]}", import_id=import_id, batch_id=b["id"])
    except core.CmsError as e:
        r.step("Lỗi", False, e)
        return _end(r, "FAILED", str(e))
    except Exception as e:  # noqa: BLE001 – lượt chạy không được treo ở RUNNING
        r.step("Lỗi hệ thống", False, repr(e))
        return _end(r, "FAILED", f"Lỗi hệ thống: {e!r}")


def _end(r, status, message, **kw):
    r.finish(status, message, **kw)
    with closing(core.connect()) as c, c:
        core.audit(c, r.actor, "sync_run", r.code, detail=f"#{r.id} {RUN_VI[status]}: {message}")
    return r.id


def start(code, actor, scope=None, trigger="MANUAL", **kw):
    """Chạy tay từ giao diện: kiểm tra nhanh rồi chạy nền, trả id lượt."""
    actor = core._actor(actor)
    holder = {}

    def go():
        holder["id"] = run(code, actor, trigger, scope, **kw)
    t = threading.Thread(target=go, daemon=True)
    t.start()
    for _ in range(50):                     # chờ lượt được ghi để trả id
        with closing(core.connect()) as c:
            r = c.execute("SELECT id FROM sync_runs WHERE province=? ORDER BY id DESC LIMIT 1", (core.province(c, code)["code"],)).fetchone()
        if r:
            return r[0]
        time.sleep(0.05)
    return None


# ------------------------------------------------------------------ bộ hẹn giờ
_sched = None


def due(c, now=None):
    now = (now or datetime.now()).isoformat(timespec="seconds")
    return [dict(r) for r in c.execute("SELECT * FROM sync_configs WHERE mode='SCHEDULE' AND next_run_at IS NOT NULL AND next_run_at<=?", (now,))]


def tick(now=None, **kw):
    """Một nhịp hẹn giờ: chạy các tỉnh đến giờ (kể cả lỡ giờ khi CMS tắt – chạy bù 1 lần), đặt giờ kế tiếp TRƯỚC khi chạy."""
    started = []
    with closing(core.connect()) as c, c:
        for cfg in due(c, now):
            c.execute("UPDATE sync_configs SET next_run_at=? WHERE province=?", (next_run(cfg, now).isoformat(timespec="seconds"), cfg["province"]))
            started.append(cfg)
    for cfg in started:
        threading.Thread(target=run, args=(cfg["province"], SCHED_ACTOR, "SCHEDULE", cfg["scope"]), kwargs=kw, daemon=True).start()
    return [c["province"] for c in started]


def start_scheduler(interval=30.0):
    global _sched
    if _sched and _sched.is_alive():
        return
    with closing(core.connect()) as c, c:          # lượt RUNNING còn sót do CMS tắt giữa chừng -> đánh dấu lỗi
        init(c)
        c.execute("UPDATE sync_runs SET status='FAILED', finished_at=?, message='CMS tắt khi đang chạy' WHERE status='RUNNING'", (core.now(),))

    def loop():
        while True:
            try:
                tick()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(interval)
    _sched = threading.Thread(target=loop, daemon=True, name="sync-scheduler")
    _sched.start()
