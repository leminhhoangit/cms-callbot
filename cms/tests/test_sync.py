"""Đồng bộ chạy tay / theo lịch + so sánh không phụ thuộc thứ tự (dữ liệu thật H32, API iCC giả lập chạy thật)."""
import os
import random
import shutil
import sys
import time
from contextlib import closing
from datetime import datetime

import pytest

CMS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CMS)
from app import core, sync, training  # noqa: E402
from tests.test_cms import RAW, raw, subset  # noqa: E402,F401
from tests.test_training import env, mock_url  # noqa: E402,F401

pytestmark = pytest.mark.skipif(not os.path.exists(RAW), reason="thiếu data/H32_raw.json.gz")


def runner_from(path):
    def run(cmd, log):
        shutil.copy(path, cmd[cmd.index("--out") + 1])
        log.write("giả lập collect_tthc\n")
        return 0
    return run


def get_run(rid):
    with closing(core.connect()) as c:
        return next(r for r in sync.runs(c, "H32") if r["id"] == rid)


def test_order_only_changes_from_portal_are_not_changes(env, raw, tmp_path):
    """Cổng trả danh sách với thứ tự khác nhau giữa các lần gọi – không được báo Thay đổi (đo thật: 1.979 / 2.023 thủ tục)."""
    c = env
    p1, ids = subset(raw, n=30, tmp=str(tmp_path))
    core.import_raw(c, "H32", p1, "qa")
    core.set_review(c, "H32", ids[0], "qa")
    before = core.procedure(c, "H32", ids[0])["rows"]

    def shuffle(d):
        rnd = random.Random(7)
        for x in d.values():
            for k in ("legalBasisesDetails", "subjectTypesDetails", "resultsDetails", "departmentsExecuting"):
                if isinstance(x.get(k), list):
                    rnd.shuffle(x[k])
            if isinstance(x.get("executingAgencies"), str):
                parts = [s.strip() for s in x["executingAgencies"].split(",")]
                rnd.shuffle(parts)
                x["executingAgencies"] = ", ".join(parts)
    p2, _ = subset(raw, n=30, tmp=str(tmp_path), mutate=shuffle)
    r = core.import_raw(c, "H32", p2, "qa")
    assert (r["added"], r["changed"], r["removed"]) == (0, 0, 0)
    t = core.procedure(c, "H32", ids[0])
    assert t["review"] == "APPROVED" and t["rows"] == before            # giữ nguyên nội dung đã duyệt

    def real(d):
        d[ids[1]]["executionSteps"] = [{"name": "", "description": "Bước 1: nộp hồ sơ (đổi thật)"}]
    p3, _ = subset(raw, n=30, tmp=str(tmp_path), mutate=real)
    assert core.import_raw(c, "H32", p3, "qa")["changed"] == 1


def test_next_run_schedule():
    now = datetime(2026, 10, 22, 9, 0)
    assert sync.next_run({"freq": "DAILY", "at_time": "08:00", "weekday": 0, "monthday": 1}, now) == datetime(2026, 10, 23, 8, 0)
    assert sync.next_run({"freq": "DAILY", "at_time": "10:30", "weekday": 0, "monthday": 1}, now) == datetime(2026, 10, 22, 10, 30)
    assert sync.next_run({"freq": "WEEKLY", "at_time": "08:00", "weekday": 0, "monthday": 1}, now) == datetime(2026, 10, 26, 8, 0)   # Thứ Hai
    assert sync.next_run({"freq": "MONTHLY", "at_time": "08:00", "weekday": 0, "monthday": 1}, now) == datetime(2026, 11, 1, 8, 0)
    assert sync.next_run({"freq": "MONTHLY", "at_time": "08:00", "weekday": 0, "monthday": 31}, datetime(2026, 11, 5)) == datetime(2026, 11, 30, 8, 0)


def test_config_manual_vs_schedule(env):
    c = env
    cfg = sync.config(c, "H32")
    assert cfg["mode"] == "MANUAL" and cfg["next_run_at"] is None
    with pytest.raises(core.CmsError, match="HH:MM"):
        sync.save_config(c, "H32", "qa", "SCHEDULE", "TRAIN_ONLY", "DAILY", "25:00")
    cfg = sync.save_config(c, "H32", "qa", "SCHEDULE", "FULL_SYNC", "WEEKLY", "7:5", weekday=2)
    assert cfg["at_time"] == "07:05" and cfg["next_run_at"] and cfg["mode_vi"] == "Theo lịch"
    assert sync.save_config(c, "H32", "qa", "MANUAL", "TRAIN_ONLY")["next_run_at"] is None


def test_manual_train_only_run(env, raw, tmp_path):
    c = env
    p1, ids = subset(raw, n=8, tmp=str(tmp_path))
    core.import_raw(c, "H32", p1, "qa")
    c.commit()
    r0 = get_run(sync.run("H32", "qa", scope="TRAIN_ONLY", poll=0.2))
    assert r0["status"] == "NO_CHANGE" and r0["batch_id"] is None              # chưa duyệt gì -> không tạo lô
    for f in ids[:2]:
        core.set_review(c, "H32", f, "qa")
    c.commit()
    r1 = get_run(sync.run("H32", "qa", scope="TRAIN_ONLY", poll=0.2))
    assert r1["status"] == "SUCCEEDED" and r1["batch_id"].startswith("TB-H32-")
    assert [s["step"] for s in r1["steps"]] == ["Kết nối bot", "Kiểm tra cần train", "Tạo lô train", "Gửi train", "Train"]
    assert training.summary(c, "H32")["synced"] == 2
    training.create_batch(c, "H32", "qa") if training.summary(c, "H32")["need_train"] else None


def test_full_sync_imports_then_trains_only_approved(env, raw, tmp_path):
    c = env
    p1, ids = subset(raw, n=10, tmp=str(tmp_path))
    core.import_raw(c, "H32", p1, "qa")
    core.set_review(c, "H32", ids[0], "qa")
    c.commit()

    def real(d):
        d[ids[1]]["executionSteps"] = [{"name": "", "description": "Bước mới từ cổng"}]
    p2, _ = subset(raw, n=10, tmp=str(tmp_path), mutate=real)
    r = get_run(sync.run("H32", "Lịch tự động", trigger="SCHEDULE", scope="FULL_SYNC", collect_runner=runner_from(p2), poll=0.2))
    assert r["status"] == "SUCCEEDED" and r["import_id"]
    imp = next(s for s in r["steps"] if s["step"].startswith("Tải dữ liệu"))
    assert "Thay đổi 1" in imp["detail"] and imp["ok"]
    s = training.summary(c, "H32")
    assert s["synced"] == 1 and s["waiting_review"] == 9                      # thủ tục đổi -> chờ người duyệt, KHÔNG tự train
    b = training.batch(c, r["batch_id"], items=True)
    assert [i["fid"] for i in b["items"]] == [ids[0]] and b["created_by"] == "Lịch tự động"


def test_skip_when_draft_batch_and_tick_runs_due(env, raw, tmp_path):
    c = env
    p1, ids = subset(raw, n=4, tmp=str(tmp_path))
    core.import_raw(c, "H32", p1, "qa")
    core.set_review(c, "H32", ids[0], "qa")
    c.commit()
    b = training.create_batch(c, "H32", "qa")
    c.commit()
    r = get_run(sync.run("H32", "qa", scope="TRAIN_ONLY", poll=0.2))
    assert r["status"] == "SKIPPED" and b["id"] in r["message"]
    training.cancel(b["id"], "qa")
    sync.save_config(c, "H32", "qa", "SCHEDULE", "TRAIN_ONLY", "DAILY", "08:00")
    c.execute("UPDATE sync_configs SET next_run_at='2026-01-01T08:00:00' WHERE province='H32'")      # lỡ giờ -> chạy bù
    c.commit()
    assert sync.tick(poll=0.2) == ["H32"]
    assert sync.config(c, "H32")["next_run_at"] > datetime.now().isoformat()
    assert sync.tick() == []                                                                       # không chạy trùng
    for _ in range(100):
        rs = sync.runs(c, "H32")
        if rs[0]["trigger"] == "SCHEDULE" and rs[0]["status"] != "RUNNING":
            break
        time.sleep(0.2)
    assert rs[0]["trigger"] == "SCHEDULE" and rs[0]["status"] == "SUCCEEDED" and rs[0]["actor"] == "Lịch tự động"
