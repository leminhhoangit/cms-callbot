"""Lô train + job + trạng thái với API iCC GIẢ LẬP chạy thật (mock_icc, cổng tạm, tốc độ nhanh)."""
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

CMS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CMS)
from app import core, training  # noqa: E402
from tests.test_cms import RAW, raw, subset  # noqa: E402,F401

pytestmark = pytest.mark.skipif(not os.path.exists(RAW), reason="thiếu data/H32_raw.json.gz")


@pytest.fixture(scope="module")
def mock_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "MOCK_QUEUE_SECONDS": "0.3", "MOCK_ROWS_PER_SEC": "150"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "mock_icc.app:app", "--port", str(port)], cwd=CMS, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/health", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    yield url
    proc.terminate()
    proc.wait(10)


@pytest.fixture()
def env(tmp_path, monkeypatch, mock_url):
    monkeypatch.setenv("CMS_DATA_DIR", str(tmp_path / "cms"))
    monkeypatch.setenv("CMS_TRAIN_URL", mock_url)
    monkeypatch.delenv("CMS_PUBLIC_URL", raising=False)
    monkeypatch.delenv("CMS_TRAIN_PROVIDER", raising=False)
    c = core.connect()
    core.init(c)
    training.init(c)
    from app import sync
    sync.init(c)
    c.commit()
    yield c
    c.close()


def wait(bid, until=("SUCCEEDED", "FAILED"), timeout=20):
    b = None
    for _ in range(int(timeout / 0.2)):
        b = training.refresh(bid)
        if b["status"] in until:
            return b
        time.sleep(0.2)
    raise AssertionError(f"lô {bid} kẹt ở {b and b['status']}")


def test_only_approved_go_to_bot_and_state_tracks_job(env, raw, tmp_path):
    c = env
    p1, ids = subset(raw, n=12, tmp=str(tmp_path))
    core.import_raw(c, "H32", p1, "qa")
    c.commit()
    with pytest.raises(core.CmsError, match="Không có gì cần train"):
        training.create_batch(c, "H32", "qa")
    for f in ids[:3]:
        core.set_review(c, "H32", f, "qa")
    c.commit()
    s = training.summary(c, "H32")
    assert (s["need_train"], s["synced"], s["waiting_review"], s["on_bot"]) == (3, 0, 9, 0)
    b = training.create_batch(c, "H32", "qa")
    c.commit()
    assert b["status"] == "DRAFT" and b["upserts"] == 3 and b["id"].startswith("TB-H32-")
    with pytest.raises(core.CmsError, match="Đã có lô"):
        training.create_batch(c, "H32", "qa")
    with pytest.raises(core.CmsError, match="người thao tác"):
        training.submit(b["id"], "")
    sb = training.submit(b["id"], "Lê Minh Hoàng")
    assert sb["status"] in ("SUBMITTED", "QUEUED") and sb["remote_job_id"].startswith("job_")
    done = wait(b["id"])
    assert done["status"] == "SUCCEEDED" and done["progress"] == 100 and done["finished_at"]
    sts = [e["status"] for e in done["events"]]
    assert sts[0] == "DRAFT" and "TRAINING" in sts and sts[-1] == "SUCCEEDED"
    s = training.summary(c, "H32")
    assert (s["need_train"], s["synced"], s["on_bot"]) == (0, 3, 3)
    assert training.provider().knowledge(training.bot_id("H32"))["procedures"] == 3
    # sửa sau khi train -> chờ duyệt (bot giữ bản cũ), duyệt lại -> cần train đúng 1
    t = core.procedure(c, "H32", ids[0])
    core.edit_rows(c, "H32", ids[0], "qa", {t["rows"][0]["seq"]: ("Câu hỏi mới", "")})
    c.commit()
    assert training.summary(c, "H32")["need_train"] == 0
    core.set_review(c, "H32", ids[0], "qa")
    c.commit()
    assert training.summary(c, "H32")["need_train"] == 1


def test_failed_job_keeps_old_version_and_retry(env, raw, tmp_path):
    c = env
    p1, ids = subset(raw, n=4, tmp=str(tmp_path))
    core.import_raw(c, "H32", p1, "qa")
    t = core.procedure(c, "H32", ids[0])
    core.edit_rows(c, "H32", ids[0], "qa", {t["rows"][0]["seq"]: ("hỏi", "[[FAIL]]")})
    core.set_review(c, "H32", ids[0], "qa")
    c.commit()
    b = training.create_batch(c, "H32", "qa")
    c.commit()
    training.submit(b["id"], "qa")
    done = wait(b["id"])
    assert done["status"] == "FAILED" and "TRAIN_ERROR" in done["error"]
    s = training.summary(c, "H32")
    assert s["need_train"] == 1 and s["on_bot"] == 0
    r = training.retry(b["id"], "qa")
    assert r["attempt"] == 2 and r["parent_id"] == b["id"] and r["status"] == "DRAFT"
    with pytest.raises(core.CmsError, match="Chỉ gửi lại"):
        training.retry(r["id"], "qa")
    assert training.cancel(r["id"], "qa")["status"] == "CANCELLED"


def test_removed_procedure_is_deleted_from_bot(env, raw, tmp_path):
    c = env
    p1, ids = subset(raw, n=12, tmp=str(tmp_path))
    core.import_raw(c, "H32", p1, "qa")
    for f in ids:
        core.set_review(c, "H32", f, "qa")
    c.commit()
    b = training.create_batch(c, "H32", "qa")
    c.commit()
    training.submit(b["id"], "qa")
    assert wait(b["id"])["status"] == "SUCCEEDED"
    p2, _ = subset(raw, n=12, tmp=str(tmp_path), drop=(ids[0],))
    core.import_raw(c, "H32", p2, "qa")
    c.commit()
    s = training.summary(c, "H32")
    assert s["need_delete"] == 1 and s["need_train"] == 0
    b2 = training.create_batch(c, "H32", "qa")
    c.commit()
    assert (b2["upserts"], b2["deletes"]) == (0, 1)
    training.submit(b2["id"], "qa")
    assert wait(b2["id"])["status"] == "SUCCEEDED"
    assert training.summary(c, "H32")["need_delete"] == 0


def test_callback_signature(env, raw, tmp_path):
    c = env
    p1, ids = subset(raw, n=3, tmp=str(tmp_path))
    core.import_raw(c, "H32", p1, "qa")
    core.set_review(c, "H32", ids[0], "qa")
    c.commit()
    b = training.create_batch(c, "H32", "qa")
    c.commit()
    sb = training.submit(b["id"], "qa")
    body = json.dumps({"job_id": sb["remote_job_id"], "status": "TRAINING", "progress": 40, "message": "cb"}).encode()
    with pytest.raises(core.CmsError, match="Chữ ký"):
        training.callback(body, "sai")
    r = training.callback(body, hmac.new(b"mock-secret", body, hashlib.sha256).hexdigest())
    assert r["status"] == "SUCCEEDED" or any(e["source"] == "CALLBACK" for e in r["events"])
    assert wait(b["id"])["status"] == "SUCCEEDED"


def test_provider_down_keeps_draft(env, raw, tmp_path, monkeypatch):
    c = env
    p1, ids = subset(raw, n=2, tmp=str(tmp_path))
    core.import_raw(c, "H32", p1, "qa")
    core.set_review(c, "H32", ids[0], "qa")
    c.commit()
    b = training.create_batch(c, "H32", "qa")
    c.commit()
    monkeypatch.setenv("CMS_TRAIN_URL", "http://127.0.0.1:1")
    with pytest.raises(training.ProviderError, match="Không kết nối"):
        training.submit(b["id"], "qa")
    b2 = training.batch(c, b["id"])
    assert b2["status"] == "DRAFT" and "Gửi lỗi" in b2["events"][-1]["message"]
    monkeypatch.setenv("CMS_TRAIN_PROVIDER", "icc")
    with pytest.raises(core.CmsError, match="Chưa có bộ kết nối"):
        training.provider()
