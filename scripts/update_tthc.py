#!/usr/bin/env python3
"""
Cập nhật dữ liệu callbot: tải lại dữ liệu mới nhất từ Cổng DVCQG, so với bộ dữ liệu cũ
và chỉ xuất những thủ tục MỚI / ĐÃ THAY ĐỔI / ĐÃ BỊ GỠ.

    python update_tthc.py "Khánh Hòa" --old out/KHA_Noi_dung_callbot_H32.xlsx
    python update_tthc.py "Khánh Hòa"                       # tự tìm bộ cũ trong data/ hoặc out/
    python update_tthc.py "Khánh Hòa" --since 2026-10-01    # chỉ lấy thay đổi cập nhật trên cổng từ ngày này
    python update_tthc.py "Khánh Hòa" --full                # xuất thêm bộ đầy đủ mới (thay thế file cũ)
    python update_tthc.py "Khánh Hòa" --new data/H32_raw_20261105.json.gz   # đã tải sẵn, chỉ so sánh

Bộ cũ (--old) có thể là file Excel do bộ công cụ này tạo ra, hoặc file raw .json.gz.
Cột "Câu hỏi liên quan" và "Tags" bạn đã điền tay ở file Excel cũ được giữ lại cho dòng có cùng Tiêu đề.

Kết quả trong out/:
  <PREFIX>_CapNhat_<MÃ>_<YYYYMMDD>.xlsx
     - Sheet0   : chỉ các dòng của TTHC mới + TTHC thay đổi (đúng định dạng 5 cột, nạp thẳng vào tập train)
     - TongHop  : danh sách TTHC Mới / Thay đổi / Đã gỡ, ngày cập nhật trên cổng, các trường thay đổi
  (--full) <PREFIX>_Noi_dung_callbot_<MÃ>_<YYYYMMDD>.xlsx  - toàn bộ dữ liệu mới nhất
Raw mới được lưu ở data/<MÃ>_raw_<YYYYMMDD>.json.gz và sẽ là "bộ cũ" cho lần cập nhật sau.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import province_config  # noqa: E402
import build_callbot_excel as B  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.styles import Font  # noqa: E402

VN = timezone(timedelta(hours=7))


def field_of(title, name):
    i = title.find(name)
    return title[:i].strip() if i > 0 else title


def group_excel(path):
    """Excel cũ -> {uri: {"name":..., "rows":[(title, content)], "extra":{title:(q, tags)}}}."""
    wb = load_workbook(path, read_only=True)
    ws = wb.active
    out = OrderedDict()
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or not r or not r[0]:
            continue
        title, content, q, tags, ident = (list(r) + [None] * 5)[:5]
        try:
            info = json.loads(ident)
            uri, name = info["uri"], info.get("title", "")
        except Exception:  # noqa: BLE001
            continue
        g = out.setdefault(uri, {"name": name, "rows": [], "extra": {}})
        g["rows"].append((B.clean(title), B.clean(content)))
        if q or tags:
            g["extra"][B.clean(title)] = (q, tags)
    return out


def group_generated(gen):
    out = OrderedDict()
    for fid, d, rows, N in gen:
        uri = json.loads(rows[0][2])["uri"]
        out[uri] = {"name": N, "rows": [(B.clean(t), B.clean(c)) for t, c, _ in rows], "detail": d,
                    "ident": rows[0][2], "extra": {}}
    return out


def find_old(code, prefix):
    cands = sorted(glob.glob(os.path.join("data", f"{code}_raw*.json.gz")), key=os.path.getmtime)
    if cands:
        return cands[-1]
    cands = sorted(glob.glob(os.path.join("out", f"{prefix}_Noi_dung_callbot_{code}*.xlsx")), key=os.path.getmtime)
    return cands[-1] if cands else None


def ts(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, VN).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("province", help='Tên hoặc mã tỉnh/thành, vd. "Khánh Hòa" hoặc H32')
    ap.add_argument("--old", help="Bộ dữ liệu cũ: file .xlsx hoặc raw .json.gz (mặc định: bản mới nhất trong data/ hoặc out/)")
    ap.add_argument("--new", help="Raw mới đã tải sẵn (bỏ qua bước tải)")
    ap.add_argument("--since", help="Chỉ giữ thay đổi có ngày cập nhật trên cổng >= YYYY-MM-DD (TTHC mới luôn giữ)")
    ap.add_argument("--full", action="store_true", help="Xuất thêm bộ dữ liệu đầy đủ mới nhất")
    ap.add_argument("--no-conditions", action="store_true")
    ap.add_argument("--workers", default="4")
    args = ap.parse_args()

    code, prov, all_names = province_config.resolve(args.province)
    today = datetime.now(VN).strftime("%Y%m%d")
    old_path = args.old or find_old(code, prov["file_prefix"])
    if not old_path or not os.path.exists(old_path):
        sys.exit("Không tìm thấy bộ dữ liệu cũ. Truyền --old <file .xlsx hoặc .json.gz>, "
                 "hoặc chạy run_all.py lần đầu.")
    print(f"== Cập nhật {prov['display']} ({code}) — so với: {old_path}")

    # 1. Tải dữ liệu mới
    new_path = args.new or os.path.join("data", f"{code}_raw_{today}.json.gz")
    if not args.new:
        if os.path.abspath(new_path) == os.path.abspath(old_path):
            new_path = os.path.join("data", f"{code}_raw_{datetime.now(VN).strftime('%Y%m%d_%H%M')}.json.gz")
        subprocess.run([sys.executable, os.path.join(HERE, "collect_tthc.py"), "--province", code,
                        "--out", new_path, "--workers", args.workers], check=True)

    # 2. Dựng nội dung theo cùng một quy tắc cho cả bộ cũ và bộ mới
    if old_path.endswith((".xlsx", ".xlsm")):
        old = group_excel(old_path)
        no_cond = args.no_conditions or not any(
            t.startswith("Yêu cầu, điều kiện") for g in old.values() for t, _ in g["rows"])
    else:
        no_cond = args.no_conditions
        old = group_generated(B.generate(B.load_raw(old_path), prov, all_names, not no_cond))
    new = group_generated(B.generate(B.load_raw(new_path), prov, all_names, not no_cond))

    since_ms = None
    if args.since:
        since_ms = int(datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=VN).timestamp() * 1000)

    added, changed, removed = [], [], []
    for uri, g in new.items():
        if uri not in old:
            added.append(uri)
            continue
        if g["rows"] != old[uri]["rows"]:
            upd = g["detail"].get("updatedAt") or 0
            if since_ms and upd and upd < since_ms:
                continue
            changed.append(uri)
    removed = [u for u in old if u not in new]

    # 3. Ghi file cập nhật
    os.makedirs("out", exist_ok=True)
    out_path = os.path.join("out", f"{prov['file_prefix']}_CapNhat_{code}_{today}.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet0"
    ws.append(B.HEADER)
    n = 0
    for uri in added + changed:
        g, extra = new[uri], old.get(uri, {}).get("extra", {})
        for t, c in g["rows"]:
            q, tags = extra.get(t, (None, None))
            ws.append([t, c, q, tags, g["ident"]])
            n += 1
    for col, w in zip("ABCDE", (60, 100, 30, 20, 60)):
        ws.column_dimensions[col].width = w
    for c in ws[1]:
        c.font = Font(bold=True)

    sm = wb.create_sheet("TongHop")
    sm.append(["Trạng thái", "Mã TTHC", "Tên thủ tục", "Lĩnh vực", "Ngày cập nhật trên cổng",
               "Các trường thay đổi", "URI"])
    for uri in added + changed + removed:
        if uri in new:
            g, d = new[uri], new[uri]["detail"]
            status = "Mới" if uri in added else "Thay đổi"
            fields = ""
            if status == "Thay đổi":
                o = {field_of(t, g["name"]): c for t, c in old[uri]["rows"]}
                nn = {field_of(t, g["name"]): c for t, c in g["rows"]}
                fields = "; ".join(sorted({k for k in set(o) | set(nn) if o.get(k) != nn.get(k)}))
            sm.append([status, d.get("codeNotation") or d.get("code"), g["name"],
                       (d.get("category") or {}).get("name") or "; ".join(B.names(d.get("categoriesDetails"))), ts(d.get("updatedAt")), fields, uri])
        else:
            sm.append(["Đã gỡ / không còn trên cổng", "", old[uri]["name"], "", "", "", uri])
    for col, w in zip("ABCDEFG", (22, 14, 80, 30, 20, 60, 60)):
        sm.column_dimensions[col].width = w
    for c in sm[1]:
        c.font = Font(bold=True)
    wb.save(out_path)

    print(f"\nKết quả so sánh: {len(added)} TTHC mới, {len(changed)} TTHC thay đổi, {len(removed)} TTHC đã gỡ")
    print(f"-> {out_path}  ({n} dòng cần bổ sung/cập nhật vào tập train)")

    if args.full:
        full = os.path.join("out", f"{prov['file_prefix']}_Noi_dung_callbot_{code}_{today}.xlsx")
        wb2 = Workbook()
        w2 = wb2.active
        w2.title = "Sheet0"
        w2.append(B.HEADER)
        for uri, g in new.items():
            extra = old.get(uri, {}).get("extra", {})
            for t, c in g["rows"]:
                q, tags = extra.get(t, (None, None))
                w2.append([t, c, q, tags, g["ident"]])
        wb2.save(full)
        print(f"-> {full}  (bộ đầy đủ mới nhất)")
    print(f"Raw mới (bộ cũ cho lần sau): {new_path}")


if __name__ == "__main__":
    main()
