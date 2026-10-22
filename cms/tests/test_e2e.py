"""E2E giao diện (Chromium thật) – server CMS riêng, CSDL tạm, dữ liệu thật (40 thủ tục Khánh Hòa).

Mã test khớp bộ test case QA của dự án (Công ty AI › callbot-tthc › Thiết kế test case): TC-E2E-01..06.
Bỏ qua khi chưa build giao diện (app/static) hoặc thiếu Playwright / dữ liệu.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import closing

import pytest

CMS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CMS)
from app import core  # noqa: E402

pw = pytest.importorskip("playwright.sync_api")
RAW = os.path.join(core.RAW_DIR, "H32_raw.json.gz")
pytestmark = pytest.mark.skipif(not (os.path.exists(RAW) and os.path.exists(os.path.join(CMS, "app", "static", "index.html"))),
                                reason="thiếu dữ liệu H32 hoặc chưa build giao diện")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    from tests.test_cms import subset
    d = tmp_path_factory.mktemp("e2e")
    os.environ["CMS_DATA_DIR"] = str(d / "cms")
    c = core.connect()
    core.init(c)
    p, ids = subset(core._load_raw(RAW), n=40, tmp=str(d))
    core.import_raw(c, "H32", p, "e2e")
    c.commit()
    c.close()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "PYTHONUTF8": "1", "CMS_DATA_DIR": str(d / "cms")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=CMS, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.2)
    yield url, ids, str(d / "cms")
    proc.terminate()
    proc.wait(10)
    os.environ.pop("CMS_DATA_DIR", None)


@pytest.fixture(scope="module")
def page(server):
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900}, accept_downloads=True)
        yield pg
        b.close()


def test_e2e_01_overview_and_actor_required(server, page):
    url, _, _ = server
    page.goto(url + "/")
    page.wait_for_selector("text=Tiến độ duyệt nội dung")
    assert page.get_by_text("Nhập tên người thao tác").is_visible()
    page.get_by_label("Người thao tác").fill("QA E2E")
    page.get_by_role("button", name="Lưu").click()
    page.wait_for_timeout(300)
    assert not page.get_by_text("Nhập tên người thao tác").is_visible()
    assert "40" in page.text_content("body")


def test_e2e_02_search_and_open_detail(server, page):
    url, _, _ = server
    page.goto(url + "/#/p/H32/list")
    page.wait_for_selector(".ant-table-row")
    page.get_by_label("Tìm thủ tục").fill("giấy phép")
    page.keyboard.press("Enter")
    page.wait_for_timeout(800)
    rows = page.locator(".ant-table-row")
    assert rows.count() >= 1
    rows.first.locator("a").click()
    page.wait_for_selector(".ant-drawer textarea")
    assert page.locator(".ant-drawer").get_by_text("Cổng Dịch vụ công Quốc gia").is_visible()


def test_e2e_03_edit_questions_then_approve(server, page):
    url, _, data_dir = server
    d = page.locator(".ant-drawer")
    d.get_by_label("Câu hỏi dòng 1").fill("Thủ tục này do ai ban hành; Ban hành ở đâu")
    d.get_by_role("button", name="Lưu (1)").click()
    page.wait_for_selector("text=Đã lưu 1 dòng")
    d.get_by_role("button", name="Duyệt nội dung").click()
    page.wait_for_selector("text=Đã duyệt nội dung")
    assert d.get_by_text("QA E2E").first.is_visible()
    os.environ["CMS_DATA_DIR"] = data_dir
    with closing(core.connect()) as c:
        r = c.execute("SELECT questions FROM rows WHERE province='H32' AND questions IS NOT NULL").fetchall()
        a = c.execute("SELECT actor, action FROM audit ORDER BY id DESC LIMIT 2").fetchall()
    assert [x[0] for x in r] == ["Thủ tục này do ai ban hành;Ban hành ở đâu"]
    assert [tuple(x) for x in a] == [("QA E2E", "approve"), ("QA E2E", "edit")]
    page.locator(".ant-drawer-close").click()


def test_e2e_04_bulk_approve(server, page):
    url, _, _ = server
    page.goto(url + "/#/p/H32/list")
    page.wait_for_selector(".ant-table-row")
    boxes = page.locator(".ant-table-row .ant-checkbox-input:not([disabled])")
    boxes.nth(0).check()
    boxes.nth(1).check()
    page.get_by_role("button", name="Duyệt 2 đã chọn").click()
    page.locator(".ant-modal").get_by_role("button", name="Duyệt").click()
    page.wait_for_selector("text=Đã duyệt 2 thủ tục")


def test_e2e_05_export_approved_downloads_excel(server, page, tmp_path):
    from openpyxl import load_workbook
    url, _, _ = server
    page.goto(url + "/#/p/H32/export")
    page.wait_for_selector("text=Xuất và tải về")
    page.get_by_text("Chỉ thủ tục đã duyệt").first.click()
    with page.expect_download() as dl:
        page.get_by_role("button", name="Xuất và tải về").click()
    f = tmp_path / dl.value.suggested_filename
    dl.value.save_as(f)
    rows = list(load_workbook(f, read_only=True).active.iter_rows(values_only=True))
    assert list(rows[0]) == core.HEADER
    assert len({r[4] for r in rows[1:]}) == 3                                  # 3 thủ tục đã duyệt (1 + 2 hàng loạt)
    assert any(r[2] == "Thủ tục này do ai ban hành;Ban hành ở đâu" for r in rows[1:])


def test_e2e_06_settings_and_audit(server, page):
    url, _, _ = server
    page.goto(url + "/#/p/H32/settings")
    page.wait_for_selector("text=Dựng lại nội dung")
    page.get_by_label("Tiền tố file").fill("x")
    page.get_by_role("button", name="Lưu cấu hình").click()
    page.wait_for_selector("text=2–6 chữ in hoa / số")
    page.goto(url + "/#/audit")
    page.wait_for_selector(".ant-table-row")
    body = page.text_content("body")
    assert "Duyệt" in body and "Sửa câu hỏi / tags" in body and "Xuất Excel" in body
