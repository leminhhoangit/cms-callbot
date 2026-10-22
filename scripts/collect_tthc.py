#!/usr/bin/env python3
"""
Thu thập dữ liệu thủ tục hành chính (TTHC) áp dụng cho một tỉnh/thành từ
Cổng Dịch vụ công Quốc gia (https://dichvucong.gov.vn - phiên bản mới, API /api/v1).

Kết quả: file raw JSON gzip  {fetchedAt, provinceCode, list:{id:item}, details:{id:detail}}
Dùng build_callbot_excel.py để chuyển raw -> Excel 5 cột cho callbot.

Ví dụ:
    python collect_tthc.py --province H19 --out data/H19_raw.json.gz
    python collect_tthc.py --province H19 --out data/H19_raw.json.gz --include-internal
    python collect_tthc.py --province H19 --out data/H19_raw.json.gz --resume

Phạm vi TTHC lấy cho 1 tỉnh (mặc định):
  * TTHC STANDARD (chuẩn hoá toàn quốc) có cấp thực hiện Tỉnh hoặc Xã
  * TTHC INTERCONNECTED (liên thông) cấp Tỉnh/Xã
  * TTHC SPECIFIC (đặc thù) do chính UBND tỉnh đó công bố (departmentCode = mã tỉnh)
  * (tuỳ chọn) STANDARD_INTERNAL - TTHC nội bộ giữa các cơ quan nhà nước
TTHC đặc thù của tỉnh khác bị loại bỏ.

Chỉ cần thư viện chuẩn + requests (pip install requests).
"""
import argparse
import gzip
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("Cần cài requests:  pip install requests")

BASE = "https://dichvucong.gov.vn/api/v1"
LIST_URL = BASE + "/submitting/formality/list-all-public-formality-by-citizen"
DETAIL_URL = BASE + "/configuring/formality/get-formality-by-citizen"
PROVINCES_URL = BASE + "/organizing/citizen/list-provinces-with-formality-count"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://dichvucong.gov.vn",
    "Referer": "https://dichvucong.gov.vn/co-quan",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
}


def post(session, url, body, retries=5, pause=1.5):
    last = None
    for attempt in range(retries):
        try:
            r = session.post(url, data=json.dumps(body), headers=HEADERS, timeout=40)
            txt = r.text
            if txt.lstrip().startswith("<"):
                # WAF / rate limit trả về HTML -> nghỉ rồi thử lại
                raise RuntimeError(f"HTML response (HTTP {r.status_code})")
            j = json.loads(txt)
            if j.get("code") == "OK":
                return j["data"]
            if j.get("code") == "OBJECT_NOT_FOUND":
                return None
            raise RuntimeError(f"{j.get('code')}: {j.get('message')}")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(pause * (attempt + 1))
    raise RuntimeError(f"POST {url} thất bại sau {retries} lần: {last}")


def list_provinces(session):
    # Cổng đổi API (10/2026): bắt buộc departmentLevel + departmentType + agencyType, body rỗng -> BAD_REQUEST
    data = post(session, PROVINCES_URL, {"departmentLevel": "PROVINCE", "departmentType": "PROVINCE", "agencyType": "UBND_TINH"})
    return data.get("rows", [])


def list_all(session, level=None, department_code="", page_size=100, log=print):
    """Duyệt toàn bộ danh sách TTHC theo cursor lastId."""
    items, last_id, page = [], "", 0
    while True:
        body = {"limit": page_size, "lastId": last_id, "q": "", "categoryId": "",
                "departmentCode": department_code}
        if level:
            body["level"] = level
        data = post(session, LIST_URL, body)
        batch = data.get("items", [])
        items.extend(batch)
        page += 1
        log(f"  list level={level or '-'} dept={department_code or '-'} trang {page}: "
            f"+{len(batch)} (tổng {len(items)}/{data.get('total')})")
        new_last = data.get("lastId")
        if not batch or not new_last or new_last == last_id:
            break
        last_id = new_last
    return items


def select_scope(all_items, province_code, include_internal=False):
    keep_types = {"STANDARD", "INTERCONNECTED"}
    if include_internal:
        keep_types.add("STANDARD_INTERNAL")
    out = {}
    for it in all_items.values():
        t = it.get("type")
        if t in keep_types:
            out[it["id"]] = it
        elif t == "SPECIFIC" and province_code in it.get("_levels", []):
            out[it["id"]] = it
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--province", default="", help='Mã hoặc tên tỉnh/thành, ví dụ H32 hoặc "Khánh Hòa"')
    ap.add_argument("--out", default="auto", help="File raw .json.gz (mặc định data/<MÃ>_raw.json.gz)")
    ap.add_argument("--include-internal", action="store_true", help="Lấy cả TTHC nội bộ (STANDARD_INTERNAL)")
    ap.add_argument("--workers", type=int, default=4, help="Số luồng tải chi tiết (mặc định 4, đừng để quá cao)")
    ap.add_argument("--resume", action="store_true", help="Tiếp tục từ file --out nếu đã có")
    ap.add_argument("--limit", type=int, default=0, help="Chỉ lấy N thủ tục đầu (để chạy thử)")
    ap.add_argument("--list-provinces", action="store_true", help="In danh sách mã tỉnh rồi thoát")
    args = ap.parse_args()

    s = requests.Session()

    if not args.list_provinces and not args.province:
        ap.error("cần --province (hoặc --list-provinces)")
    if args.list_provinces:
        for p in list_provinces(s):
            print(f"{p['code']}\t{p['name']}\t{p.get('formalityCount')}")
        return

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import province_config
    pc, _cfg, _ = province_config.resolve(args.province)
    if args.out == "auto":
        args.out = os.path.join("data", f"{pc}_raw.json.gz")
    print(f"[1/3] Lấy danh sách TTHC cho {pc} ...")
    all_items = {}
    for level, dept in (("PROVINCE", ""), ("COMMUNE", ""), (None, pc)):
        for it in list_all(s, level=level, department_code=dept):
            o = all_items.setdefault(it["id"], {**it, "_levels": []})
            o["_levels"].append(level or pc)
    scope = select_scope(all_items, pc, args.include_internal)
    ids = list(scope)
    if args.limit:
        ids = ids[: args.limit]
    print(f"  -> {len(all_items)} TTHC cấp tỉnh/xã toàn quốc, chọn {len(ids)} TTHC cho {pc}")

    details = {}
    if args.resume and os.path.exists(args.out):
        with gzip.open(args.out, "rt", encoding="utf-8") as f:
            details = json.load(f).get("details", {})
        print(f"  resume: đã có {len(details)} chi tiết")

    todo = [i for i in ids if i not in details]
    print(f"[2/3] Tải chi tiết {len(todo)} TTHC (workers={args.workers}) ...")
    fails = []

    def fetch(fid):
        return fid, post(s, DETAIL_URL, {"id": fid})

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(fetch, i) for i in todo]
        for fu in as_completed(futs):
            try:
                fid, d = fu.result()
                if d:
                    details[fid] = d
                else:
                    fails.append(fid)
            except Exception as e:  # noqa: BLE001
                fails.append(str(e)[:120])
            done += 1
            if done % 100 == 0 or done == len(todo):
                print(f"  {done}/{len(todo)}  (lỗi: {len(fails)})")

    print(f"[3/3] Ghi {args.out}")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    payload = {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "provinceCode": pc,
        "list": {i: scope[i] for i in ids},
        "details": details,
        "failures": fails,
    }
    with gzip.open(args.out, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"Xong: {len(details)} chi tiết, {len(fails)} lỗi.")
    if fails:
        print("Chạy lại với --resume để tải bù các TTHC lỗi.")


if __name__ == "__main__":
    main()
