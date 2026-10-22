"""Tra cứu cấu hình tỉnh/thành theo MÃ (H32) hoặc TÊN ("Khánh Hòa", "khanh hoa", "Đồng Nai").

Nếu tỉnh chưa có mục riêng trong provinces.json, cấu hình được sinh tự động từ bảng
"_codes" (tên UBND theo Cổng DVCQG). Địa chỉ tiếp nhận khi đó là câu chung chung,
nên bổ sung địa chỉ thật vào provinces.json khi có.
"""
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "provinces.json")


def norm(s):
    s = unicodedata.normalize("NFD", str(s)).replace("đ", "d").replace("Đ", "D")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"^(ubnd|uy ban nhan dan)\s+", "", s.strip())
    s = re.sub(r"^(tinh|thanh pho|tp\.?)\s+", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def _auto(code, ubnd):
    m = re.match(r"(?i)^UBND\s+(tỉnh|thành phố)\s+(.+)$", ubnd.strip())
    kind, short = (m.group(1).lower(), m.group(2)) if m else ("tỉnh", ubnd)
    display = ("Tỉnh " if kind == "tỉnh" else "Thành phố ") + short
    prefix = "".join(w[0] for w in norm_words(short)).upper()[:3] or code
    return {
        "display": display,
        "short": short,
        "ubnd": f"UBND {display[0].lower() + display[1:] if kind == 'tỉnh' else display}",
        "in_phrase": f"tại {display[0].lower() + display[1:] if kind == 'tỉnh' else display}",
        "center_address": f"Trung tâm Phục vụ hành chính công {display} (đối với TTHC cấp tỉnh); "
                          f"Trung tâm Phục vụ hành chính công các xã, phường thuộc {display} (đối với TTHC cấp xã)",
        "file_prefix": prefix,
        "_auto": True,
    }


def norm_words(s):
    s = unicodedata.normalize("NFD", s).replace("đ", "d").replace("Đ", "D")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return [w for w in re.split(r"\W+", s) if w]


def load(path=DEFAULT_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve(arg, path=DEFAULT_PATH):
    """Trả về (code, cấu hình). Dừng chương trình nếu không tìm thấy."""
    provs = load(path)
    codes = provs.get("_codes", {})
    a = arg.strip()
    code = a.upper() if re.fullmatch(r"(?i)H\d{2}", a) else None
    if not code:
        key = norm(a)
        for c, name in codes.items():
            if norm(name) == key:
                code = c
                break
        if not code:
            for c, cfg in provs.items():
                if c.startswith("_"):
                    continue
                if key in (norm(cfg.get("short", "")), norm(cfg.get("display", ""))):
                    code = c
                    break
    if not code:
        sys.exit(f"Không tìm thấy tỉnh/thành '{arg}'. Xem danh sách mã: "
                 f"python collect_tthc.py --list-provinces")
    if code in provs:
        cfg = provs[code]
    elif code in codes:
        cfg = _auto(code, codes[code])
        print(f"[!] {code} chưa có cấu hình riêng trong provinces.json -> dùng cấu hình tự sinh "
              f"('{cfg['display']}'). Nên bổ sung địa chỉ Trung tâm Phục vụ HCC thật.")
    else:
        sys.exit(f"Mã {code} không có trong provinces.json (_codes).")
    all_names = [load_short(n) for n in codes.values()]
    return code, cfg, all_names


def load_short(ubnd):
    return re.sub(r"(?i)^UBND\s+(tỉnh|thành phố)\s+", "", ubnd).strip()
