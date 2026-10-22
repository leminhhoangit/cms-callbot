"""Nguồn dữ liệu: kiểm tra sức khoẻ Cổng DVCQG + chạy thu thập nền (collect_tthc.py) rồi tự nhập vào CMS.

Bài học 22/10/2026: cổng đổi API không báo trước (list-provinces đòi thêm tham số). Vì vậy:
- trước mỗi lần thu thập gọi thử 3 API (1 bản ghi mỗi API); lỗi -> dừng, báo rõ lỗi của cổng, không chạy 15–30 phút rồi hỏng;
- mỗi lần thu thập là 1 job có nhật ký riêng; chỉ 1 job chạy cùng lúc (tôn trọng cổng: 4 luồng như script gốc).
"""
import json
import os
import subprocess
import sys
import threading
from contextlib import closing
from datetime import datetime

from . import core

BASE = "https://dichvucong.gov.vn/api/v1"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*", "Origin": "https://dichvucong.gov.vn",
           "Referer": "https://dichvucong.gov.vn/co-quan"}
CHECKS = [
    ("Danh sách TTHC", "/submitting/formality/list-all-public-formality-by-citizen",
     {"limit": 1, "lastId": "", "q": "", "categoryId": "", "departmentCode": "", "level": "PROVINCE"}),
    ("Danh sách tỉnh", "/organizing/citizen/list-provinces-with-formality-count",
     {"departmentLevel": "PROVINCE", "departmentType": "PROVINCE", "agencyType": "UBND_TINH"}),
]
DETAIL = ("Chi tiết TTHC", "/configuring/formality/get-formality-by-citizen")


def health(sample_fid=None, post=None):
    """[{name, ok, detail, ms}] – post(url, body) -> (status, text) để test thay được."""
    import time
    if post is None:
        import requests

        def post(url, body):
            r = requests.post(url, data=json.dumps(body), headers=HEADERS, timeout=20)
            return r.status_code, r.text
    checks = list(CHECKS)
    if sample_fid:
        checks.append((DETAIL[0], DETAIL[1], {"id": sample_fid}))
    out = []
    for name, path, body in checks:
        t = time.time()
        try:
            st, txt = post(BASE + path, body)
            if txt.lstrip().startswith("<"):
                ok, detail = False, f"Cổng trả HTML (HTTP {st}) – có thể bị chặn / WAF. Dùng scripts/browser_collector.js"
            else:
                j = json.loads(txt)
                ok = j.get("code") == "OK"
                detail = "OK" if ok else f"{j.get('code')}: {(j.get('message') or '')[:300]} – API cổng có thể đã đổi"
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"Không kết nối được: {str(e)[:200]}"
        out.append({"name": name, "ok": ok, "detail": detail, "ms": int((time.time() - t) * 1000)})
    return out


# ------------------------------------------------------------------ job thu thập
_JOBS = {}
_LOCK = threading.Lock()


def jobs():
    return sorted(_JOBS.values(), key=lambda j: j["started"], reverse=True)


def running():
    return next((j for j in _JOBS.values() if j["status"] == "RUNNING"), None)


def start_collect(code, actor, limit=0, include_internal=False, runner=None, wait=False):
    """Chạy collect_tthc.py -> cms/data/raw/<MÃ>_raw_cms_<thời điểm>.json.gz -> nhập vào CMS. runner(cmd, log) để test thay được.
    wait=True: chạy ngay trong luồng gọi và trả job đã xong (dùng cho đồng bộ theo lịch)."""
    actor = core._actor(actor)
    with closing(core.connect()) as c:
        core.init(c)
        prov = core.province(c, code)
        sample = c.execute("SELECT fid FROM procedures WHERE province=? LIMIT 1", (prov["code"],)).fetchone()
    with _LOCK:
        if running():
            raise core.CmsError("Đang có lần thu thập chạy – chờ xong")
        if runner is None:
            bad = [h for h in health(sample[0] if sample else None) if not h["ok"]]
            if bad:
                raise core.CmsError("Cổng DVCQG lỗi, không thu thập: " + "; ".join(f"{h['name']}: {h['detail']}" for h in bad))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = os.path.join(core.cms_raw_dir(), f"{prov['code']}_raw_cms_{stamp}{'_thu' if limit else ''}.json.gz")
        logs = os.path.join(core.data_dir(), "logs")
        os.makedirs(logs, exist_ok=True)
        job = {"id": f"{prov['code']}_{stamp}", "province": prov["code"], "status": "RUNNING", "started": core.now(), "finished": None,
               "actor": actor, "raw": os.path.basename(out), "log": os.path.join(logs, f"collect_{prov['code']}_{stamp}.log"), "result": None, "error": None}
        _JOBS[job["id"]] = job
    cmd = [sys.executable, os.path.join(core.SCRIPTS, "collect_tthc.py"), "--province", prov["code"], "--out", out]
    if limit:
        cmd += ["--limit", str(int(limit))]
    if include_internal:
        cmd.append("--include-internal")

    def run():
        try:
            with open(job["log"], "w", encoding="utf-8") as log:
                rc = (runner or _subprocess)(cmd, log)
            if rc != 0 or not os.path.exists(out):
                raise core.CmsError(f"Thu thập lỗi (mã {rc}) – xem nhật ký")
            if limit:   # chạy thử: chỉ kiểm tra thu thập được, KHÔNG nhập (bộ thiếu sẽ làm sai trạng thái)
                raw = core._load_raw(out)
                job["result"] = {"trial": True, "procedures": len(raw.get("details") or {}), "failures": len(raw.get("failures") or [])}
            else:
                with closing(core.connect()) as c, c:
                    core.init(c)
                    job["result"] = core.import_raw(c, prov["code"], out, actor, note="Thu thập từ CMS")
            job["status"] = "SUCCEEDED"
        except Exception as e:  # noqa: BLE001
            job["status"], job["error"] = "FAILED", str(e)[:500]
        job["finished"] = core.now()

    if wait:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()
    return job


def _subprocess(cmd, log):
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=core.ROOT, env=env).returncode


def log_tail(job_id, n=60):
    j = _JOBS.get(job_id)
    if not j or not os.path.exists(j["log"]):
        return ""
    with open(j["log"], encoding="utf-8", errors="replace") as f:
        return "".join(f.readlines()[-n:])
