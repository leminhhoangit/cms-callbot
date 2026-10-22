"""Test CMS trên dữ liệu THẬT (data/H32_raw.json.gz). Mỗi test dùng CSDL riêng trong thư mục tạm."""
import copy
import gzip
import json
import os
import subprocess
import sys
import time
from contextlib import closing

import pytest

CMS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CMS)
from app import core, source  # noqa: E402

RAW = os.path.join(core.RAW_DIR, "H32_raw.json.gz")
pytestmark = pytest.mark.skipif(not os.path.exists(RAW), reason="thiếu data/H32_raw.json.gz")


@pytest.fixture(scope="module")
def raw():
    return core._load_raw(RAW)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("CMS_DATA_DIR", str(tmp_path / "cms"))
    c = core.connect()
    core.init(c)
    c.commit()
    yield c
    c.close()


def subset(raw, n=40, tmp=None, drop=(), mutate=None, failures=None):
    ids = sorted(raw["details"])[:n]
    r = {"fetchedAt": raw["fetchedAt"], "provinceCode": "H32", "list": {i: raw["list"].get(i, {}) for i in ids},
         "details": {i: copy.deepcopy(raw["details"][i]) for i in ids if i not in drop}, "failures": failures or []}
    if mutate:
        mutate(r["details"])
    p = os.path.join(tmp, f"H32_raw_t{time.time_ns()}.json.gz")
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False)
    return p, ids


def test_import_review_keeps_questions_and_detects_changes(db, raw, tmp_path):
    p1, ids = subset(raw, tmp=tmp_path)
    with pytest.raises(core.CmsError, match="người thao tác"):
        core.import_raw(db, "H32", p1, "")
    r = core.import_raw(db, "H32", p1, "hoanglm")
    assert r["procedures"] == 40 and r["added"] == 40 and r["changed"] == 0 and r["removed"] == 0
    st = core.stats(db, "H32")
    assert st["procedures"] == 40 and st["need_review"] == 40 and st["rows"] == r["rows"] > 40 * 15
    a, b = ids[0], ids[1]
    t = core.procedure(db, "H32", a)
    assert core.edit_rows(db, "H32", a, "hoanglm", {t["rows"][0]["seq"]: ("Hỏi 1 ;  Hỏi 2\nHỏi 3", "tag")}) == 1
    assert core.procedure(db, "H32", a)["rows"][0]["questions"] == "Hỏi 1;Hỏi 2;Hỏi 3"
    core.set_review(db, "H32", a, "hoanglm")
    core.set_review(db, "H32", b, "hoanglm")
    # nhập lại cùng dữ liệu: không đổi, giữ duyệt + câu hỏi
    r2 = core.import_raw(db, "H32", p1, "hoanglm")
    assert (r2["added"], r2["changed"], r2["removed"]) == (0, 0, 0)
    t = core.procedure(db, "H32", a)
    assert t["review"] == "APPROVED" and t["change"] == "SAME" and t["rows"][0]["questions"] == "Hỏi 1;Hỏi 2;Hỏi 3"

    def mut(d):
        d[a]["executionSteps"] = [{"name": "", "description": "Bước 1: nộp hồ sơ (đã sửa)"}]
    p2, _ = subset(raw, tmp=tmp_path, drop=(ids[5],), mutate=mut)
    r3 = core.import_raw(db, "H32", p2, "hoanglm")
    assert (r3["added"], r3["changed"], r3["removed"]) == (0, 1, 1)
    t = core.procedure(db, "H32", a)
    assert t["change"] == "CHANGED" and t["review"] == "NEED_REVIEW" and t["rows"][0]["questions"] == "Hỏi 1;Hỏi 2;Hỏi 3"
    assert core.procedure(db, "H32", b)["review"] == "APPROVED"
    gone = core.procedure(db, "H32", ids[5])
    assert gone["status"] == "REMOVED"
    with pytest.raises(core.CmsError, match="đã gỡ"):
        core.set_review(db, "H32", ids[5], "hoanglm")
    # sửa TTHC đã duyệt -> cần duyệt lại
    t = core.procedure(db, "H32", b)
    core.edit_rows(db, "H32", b, "hoanglm", {t["rows"][1]["seq"]: ("Câu mới", "")})
    assert core.procedure(db, "H32", b)["review"] == "NEED_REVIEW"
    assert {x["action"] for x in core.audit_log(db)} >= {"import", "edit", "approve"}


def test_partial_file_does_not_mark_removed(db, raw, tmp_path):
    p1, ids = subset(raw, tmp=tmp_path)
    core.import_raw(db, "H32", p1, "qa")
    p2, _ = subset(raw, n=10, tmp=tmp_path)
    r = core.import_raw(db, "H32", p2, "qa")
    assert r["removed"] == 0 and "không đánh dấu Đã gỡ" in r["note"]
    p3, _ = subset(raw, tmp=tmp_path, drop=(ids[0],), failures=["timeout"])
    assert core.import_raw(db, "H32", p3, "qa")["removed"] == 0
    with pytest.raises(core.CmsError, match="không phải H19"):
        core.import_raw(db, "H19", p1, "qa")


def test_export_kinds_and_format(db, raw, tmp_path):
    from openpyxl import load_workbook
    p1, ids = subset(raw, tmp=tmp_path)
    core.import_raw(db, "H32", p1, "qa")
    with pytest.raises(core.CmsError, match="Không có TTHC"):
        core.export(db, "H32", "APPROVED", "qa")
    core.set_review(db, "H32", ids[0], "qa")
    e = core.export(db, "H32", "APPROVED", "qa")
    assert e["procedures"] == 1
    full = core.export(db, "H32", "FULL", "qa")
    ws = load_workbook(core.export_path(full["file"]), read_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    assert list(rows[0]) == core.HEADER and len(rows) - 1 == full["rows"] == core.stats(db, "H32")["rows"]
    assert json.loads(rows[1][4])["type"] == 3
    ch = core.export(db, "H32", "CHANGES", "qa")
    wb = load_workbook(core.export_path(ch["file"]), read_only=True)
    assert wb.sheetnames == ["Sheet0", "TongHop"] and ch["procedures"] == 40


def test_rebuild_after_address_change(db, raw, tmp_path):
    p1, ids = subset(raw, tmp=tmp_path)
    core.import_raw(db, "H32", p1, "qa")
    for i in ids:
        core.set_review(db, "H32", i, "qa")
    core.update_province(db, "H32", "qa", center_address="Địa chỉ QA thử nghiệm")
    r = core.rebuild(db, "H32", "qa")
    assert r["changed"] == 40 and r["removed"] == 0
    t = core.procedure(db, "H32", ids[0])
    assert t["review"] == "NEED_REVIEW" and any("Địa chỉ QA thử nghiệm" in (x["content"] or "") for x in t["rows"])
    with pytest.raises(core.CmsError, match="Tiền tố"):
        core.update_province(db, "H32", "qa", file_prefix="x")


def test_suggest_questions_only_fills_empty(db, raw, tmp_path):
    p1, ids = subset(raw, n=5, tmp=tmp_path)
    core.import_raw(db, "H32", p1, "qa")
    t = core.procedure(db, "H32", ids[0])
    seq_addr = next(r["seq"] for r in t["rows"] if r["title"].startswith("Địa chỉ tiếp nhận"))
    core.edit_rows(db, "H32", ids[0], "qa", {seq_addr: ("Câu tay", "")})
    n = core.suggest_questions(db, "H32", ids[0], "qa")
    t = core.procedure(db, "H32", ids[0])
    assert n > 0 and next(r for r in t["rows"] if r["seq"] == seq_addr)["questions"] == "Câu tay"


def test_collect_job_trial_does_not_import(db, raw, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "RAW_DIR", str(tmp_path))
    src, _ = subset(raw, n=3, tmp=tmp_path)

    def runner(cmd, log):
        out = cmd[cmd.index("--out") + 1]
        os.replace(src, out)
        log.write("ok\n")
        return 0
    j = source.start_collect("H32", "qa", limit=3, runner=runner)
    for _ in range(100):
        if j["status"] != "RUNNING":
            break
        time.sleep(0.05)
    assert j["status"] == "SUCCEEDED" and j["result"] == {"trial": True, "procedures": 3, "failures": 0}
    assert core.stats(db, "H32")["procedures"] == 0


def test_health_reports_api_change():
    def post(url, body):
        if "list-provinces" in url:
            return 200, json.dumps({"code": "BAD_REQUEST", "message": "agencyType must be one of"})
        if "formality/list" in url:
            return 403, "<html>blocked</html>"
        return 200, json.dumps({"code": "OK", "data": {}})
    h = {x["name"]: x for x in source.health("x", post=post)}
    assert h["Chi tiết TTHC"]["ok"] and not h["Danh sách tỉnh"]["ok"] and "đổi" in h["Danh sách tỉnh"]["detail"]
    assert "HTML" in h["Danh sách TTHC"]["detail"]


def test_api_flow(db, raw, tmp_path):
    from urllib.parse import quote
    from fastapi.testclient import TestClient
    from app.main import app
    p1, ids = subset(raw, n=5, tmp=tmp_path)
    core.import_raw(db, "H32", p1, "qa")
    db.commit()
    cl = TestClient(app)
    pv = {p["code"]: p for p in cl.get("/api/provinces").json()["provinces"]}
    assert pv["H32"]["stats"]["procedures"] == 5 and pv["H19"]["stats"] is None and len(pv) == 34
    r = cl.post(f"/api/p/H32/t/{ids[0]}/review", json={"approve": True})
    assert r.status_code == 400 and "người thao tác" in r.json()["detail"]
    h = {"X-Actor": quote("Lê Minh Hoàng")}
    r = cl.post(f"/api/p/H32/t/{ids[0]}/review", json={"approve": True}, headers=h)
    assert r.json()["review"] == "APPROVED" and r.json()["reviewed_by"] == "Lê Minh Hoàng"
    lst = cl.get("/api/p/H32/procedures", params={"review": "APPROVED"}).json()
    assert lst["total"] == 1 and lst["items"][0]["fid"] == ids[0]
    seq = core.procedure(db, "H32", ids[1])["rows"][0]["seq"]
    r = cl.put(f"/api/p/H32/t/{ids[1]}/rows", json={"edits": [{"seq": seq, "questions": "Thủ tục này làm ở đâu", "tags": ""}]}, headers=h)
    assert r.json()["changed"] == 1 and r.json()["procedure"]["rows"][0]["questions"] == "Thủ tục này làm ở đâu"
    assert cl.post("/api/p/H32/review-bulk", json={"fids": ids[1:3]}, headers=h).json() == {"approved": 2}
    e = cl.post("/api/p/H32/exports", json={"kind": "APPROVED"}, headers=h).json()
    assert e["procedures"] == 3 and cl.get(f"/api/exports/{e['file']}").content[:2] == b"PK"
    assert cl.post("/api/p/H32/exports", json={"kind": "XX"}, headers=h).status_code == 400
    assert cl.get("/api/p/H99").status_code == 400
    assert [a["action"] for a in cl.get("/api/audit").json()["rows"]][:2] == ["export", "approve"]
    assert cl.get("/api/jobs/khong-co").status_code == 404
    r = cl.get("/p/H32/list")                                                    # đường dẫn giao diện -> index.html (hoặc báo chưa build)
    assert r.status_code in (200, 503)


@pytest.mark.slow
def test_full_export_matches_existing_tool(db, tmp_path):
    """Bộ đầy đủ H32 từ CMS == file Excel của scripts/build_callbot_excel.py (cùng raw)."""
    from openpyxl import load_workbook
    ref = tmp_path / "ref.xlsx"
    subprocess.run([sys.executable, os.path.join(core.SCRIPTS, "build_callbot_excel.py"), "--raw", RAW, "--province", "H32", "--out", str(ref)],
                   check=True, capture_output=True, env={**os.environ, "PYTHONUTF8": "1"})
    core.import_raw(db, "H32", RAW, "qa")
    e = core.export(db, "H32", "FULL", "qa")
    a = [r[:2] + (r[4],) for r in load_workbook(ref, read_only=True).active.iter_rows(min_row=2, values_only=True)]
    b = [r[:2] + (r[4],) for r in load_workbook(core.export_path(e["file"]), read_only=True).active.iter_rows(min_row=2, values_only=True)]
    assert len(a) == len(b) == 72875
    assert sorted(a) == sorted(b)
