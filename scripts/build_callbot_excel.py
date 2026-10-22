#!/usr/bin/env python3
"""
Chuyển raw JSON (từ collect_tthc.py hoặc browser_collector.js) thành file Excel
dữ liệu huấn luyện callbot theo đúng định dạng mẫu (HYN_Nội_dung_callbot_H31.xlsx):

  Cột A  Tiêu đề        "<Trường> <Tên TTHC> của <Tỉnh/TP>"
  Cột B  Nội dung       "<Trường> <Tên TTHC> là: <giá trị>"
  Cột C  Câu hỏi liên quan (các câu cách nhau bởi dấu ";")   (để trống, hoặc --with-questions)
  Cột D  Tags           (để trống, hoặc --with-tags)
  Cột E  IdentificationInfo  {"uri": ..., "type": 3, "title": <Tên TTHC>}

Mỗi TTHC sinh ~25 dòng (một dòng / trường; "Cách thức thực hiện" một dòng / hình thức nộp;
"Thành phần hồ sơ" một dòng / trường hợp).

Ví dụ:
    python build_callbot_excel.py --raw data/H19_raw.json.gz --province H19 \
        --out "DNI_Noi_dung_callbot_H19.xlsx"
"""
import argparse
import gzip
import json
import os
import re
import sys

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
except ImportError:  # pragma: no cover
    sys.exit("Cần cài openpyxl:  pip install openpyxl")

HERE = os.path.dirname(os.path.abspath(__file__))
NA = "Không có thông tin"
MAX_CELL = 32000
DETAIL_PAGE = "https://dichvucong.gov.vn/thu-tuc-hanh-chinh/{id}"

HEADER = ["Tiêu đề", "Nội dung", 'Câu hỏi liên quan (các câu cách nhau bởi dấu ";")', "Tags",
          "IdentificationInfo"]

SUBMIT = {"DIRECT": "Trực tiếp", "ONLINE": "Trực tuyến", "POSTAL": "Dịch vụ bưu chính"}
SUBMIT_ORDER = {"DIRECT": 0, "ONLINE": 1, "POSTAL": 2}
UNIT = {"WORKING_DAY": "Ngày làm việc", "DAY": "Ngày", "HOUR": "Giờ", "MONTH": "Tháng",
        "WEEK": "Tuần", "YEAR": "Năm", "OTHER": "Khác"}
FTYPE = {"ASSIGNED_REGULATION": "TTHC được luật giao cho địa phương quy định hoặc quy định chi tiết",
         "NOT_ASSIGNED_REGULATION": "TTHC không được luật giao cho địa phương quy định hoặc quy định chi tiết",
         "OTHER": "TTHC khác"}
RETURN = {"AT_SUBMISSION_PLACE": "Trả kết quả tại bộ phận tiếp nhận và trả kết quả",
          "AT_HOME": "Trả kết quả qua dịch vụ bưu chính (tại nhà)",
          "ONLINE": "Trả kết quả trực tuyến"}
RETURN_TYPE = {"ONLINE": "Khi nộp trực tuyến", "OFFLINE": "Khi nộp trực tiếp/bưu chính"}

# Các trường không phụ thuộc địa phương khi giá trị là cơ quan cấp Bộ/Trung ương
CENTRAL_HINTS = ("Bộ ", "Bộ trưởng", "Chính phủ", "Thủ tướng", "Cục ", "Tổng cục", "Ngân hàng Nhà nước",
                 "Văn phòng Chính phủ", "Bảo hiểm xã hội Việt Nam", "Kho bạc Nhà nước", "Chủ tịch nước",
                 "Chi cục Hải quan", "Chi cục Thuế", "Hải quan", "Tòa án", "Viện kiểm sát", "Cảng vụ",
                 "Đội Thủ tục Biên phòng", "Biên phòng")


def clean(s):
    if s is None:
        return ""
    s = str(s).replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)  # ký tự điều khiển Excel không chấp nhận
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def or_na(s):
    s = clean(s)
    return s if s else NA


def uniq(seq):
    seen, out = set(), []
    for x in seq:
        x = clean(x)
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


OTHER_PROVINCE_NAMES = []  # nạp từ provinces.json -> "_all_province_names"

LOCAL_RULES = [  # (regex, thay bằng) — {P} = tên hiển thị tỉnh/TP, {U} = UBND tỉnh/TP
    (r"^(chủ tịch )(ủy|uỷ) ban nhân dân (cấp )?tỉnh.*$", "Chủ tịch {U}"),
    (r"^chủ tịch ubnd (cấp )?tỉnh.*$", "Chủ tịch {U}"),
    (r"^(ủy|uỷ) ban nhân dân (cấp tỉnh|tỉnh)( và thành phố trực thuộc trung ương)?\.?$", "{U}"),
    (r"^ubnd (cấp )?tỉnh\.?$", "{U}"),
    (r"^công an (cấp )?tỉnh\.?$", "Công an {P}"),
    (r"^bảo hiểm xã hội (cấp )?tỉnh\.?$", "Bảo hiểm xã hội {P}"),
    (r"^thuế tỉnh, thành phố\.?$", "Thuế {P}"),
    (r"^(chủ tịch )?(ủy|uỷ) ban nhân dân (cấp xã|xã)(, phường, thị trấn)?\.?$", "\\g<0> thuộc {P}"),
    (r"^(chủ tịch )?ubnd cấp xã\.?$", "\\g<0> thuộc {P}"),
    (r"^công an cấp xã\.?$", "Công an cấp xã thuộc {P}"),
]


def fix_other_province(text, prov):
    """Văn bản mô tả cơ quan dùng chung toàn quốc đôi khi ghi tên tỉnh khác
    ('Sở Y tế Thành phố Đồng Nai') -> thay bằng tỉnh đang build."""
    text = clean(text)
    for other in OTHER_PROVINCE_NAMES:
        text = re.sub(r"(?i)\b(thành phố|tỉnh|tp\.?)\s+" + re.escape(other) + r"\b", prov["display"], text)
    return text


def localize_agency(name, prov):
    """Địa phương hoá tên cơ quan:
    'Sở Giáo dục và Đào tạo' -> 'Sở Giáo dục và Đào tạo - Thành phố Đồng Nai' (giống mẫu H31),
    'Ủy ban nhân dân cấp tỉnh' -> 'UBND Thành phố Đồng Nai', 'Công an tỉnh' -> 'Công an Thành phố Đồng Nai'.
    Trả về None nếu tên cơ quan thuộc tỉnh/thành khác (bị loại)."""
    name = clean(name).rstrip(" .;")
    if not name:
        return None
    low = name.lower()
    for other in OTHER_PROVINCE_NAMES:
        if re.search(r"\b" + re.escape(other.lower()) + r"\b", low) and prov["short"].lower() not in low:
            return None
    if "tp.hcm" in low and prov["short"] != "Hồ Chí Minh":
        return None
    if prov["short"].lower() in low or name.startswith(CENTRAL_HINTS):
        return name
    for pat, rep in LOCAL_RULES:
        if re.match(pat, low, re.I):
            out = re.sub(pat, rep, name, flags=re.I)
            return out.replace("{P}", prov["display"]).replace("{U}", prov["ubnd"])
    name = re.sub(r"\s+(các|của các) tỉnh, thành phố( trực thuộc trung ương)?$", "", name, flags=re.I)
    if re.match(r"^(sở|ban quản lý|văn phòng đăng ký|chi nhánh văn phòng|chi cục|trung tâm|ban |thanh tra tỉnh|kho bạc nhà nước tỉnh)", name, re.I):
        return f"{name} - {prov['display']}"
    return name


def names(lst):
    return [x.get("name", "") for x in (lst or []) if isinstance(x, dict)]


def fmt_money(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return clean(v) or NA
    if v.is_integer():
        return f"{int(v):,}".replace(",", ".")
    return f"{v:,.2f}"


def subject_group(subjects):
    """Nhóm đối tượng ngắn gọn cho trường 'Mô tả đối tượng thực hiện' (giống mẫu: 'Tổ chức', 'Công dân', ...)."""
    groups = []
    for s in subjects:
        sl = s.lower()
        if "doanh nghiệp" in sl or "hợp tác xã" in sl or "htx" in sl:
            g = "Doanh nghiệp"
        elif "tổ chức" in sl or "cơ quan" in sl or "đơn vị" in sl:
            g = "Tổ chức"
        elif "người" in sl or "công dân" in sl or "cá nhân" in sl:
            g = "Công dân"
        else:
            g = s
        if g not in groups:
            groups.append(g)
    return ", ".join(groups)


def build_rows(d, item, prov, opts):
    """Sinh danh sách (tiêu_đề, nội_dung) cho 1 TTHC."""
    N = clean(d.get("name") or item.get("name"))
    T = lambda field: f"{field} {N} của {prov['display']}"  # noqa: E731
    rows = []
    add = lambda title, content: rows.append((title, content))  # noqa: E731

    is_specific = (d.get("type") or item.get("type")) == "SPECIFIC"
    promul = clean(d.get("departmentPromulgateName") or item.get("departmentPromulgate"))

    # 1. Địa phương, đơn vị ban hành
    add(T("Địa phương, đơn vị ban hành"),
        f"Địa phương, đơn vị ban hành {N} là: {prov['ubnd']}")
    # 2. Mã
    code = clean(d.get("codeNotation") or d.get("code") or item.get("codeNotation") or item.get("code"))
    add(T("Mã"), f"Mã {N} là : {or_na(code)}")
    # 3. Tên
    add(T("Tên thủ tục hành chính"), f"Tên thủ tục hành chính là: {N}")
    # 4. Cơ quan công bố
    pp = d.get("procedureProposal") or {}
    cq = promul or (pp.get("issuingAgency") or {}).get("name") or ""
    if is_specific:
        cq = cq or prov["ubnd"]
    dec = clean(pp.get("proposalNumber") or pp.get("decisionNumber") or d.get("decisionNo"))
    cq_txt = or_na(cq) + (f" (Quyết định công bố số {dec})" if dec else "")
    add(T("Cơ quan công bố thủ tục"), f"Cơ quan công bố thủ tục {N} là: {cq_txt}")
    # 5. Loại thủ tục
    add(T("Loại thủ tục"), f"Loại thủ tục {N} là: {FTYPE.get(d.get('formalityType'), NA)}")
    # 6. Mô tả đối tượng thực hiện
    subjects = uniq(names(d.get("subjectTypesDetails")) + list(item.get("formalityTargetType") or []))
    add(T("Mô tả đối tượng thực hiện"),
        f"Mô tả đối tượng thực hiện {N} là: {or_na(subject_group(subjects))}")
    # 7. Địa chỉ tiếp nhận
    addr = clean(d.get("dossierReceivingAddresses"))
    addr_txt = prov["center_address"] + (f"\n{addr}" if addr else "")
    add(T("Địa chỉ tiếp nhận"), f"Địa chỉ tiếp nhận {N} là: {addr_txt}")
    # 8-9. Mô tả cơ quan
    add(T("Mô tả cơ quan thực hiện"), f"Mô tả cơ quan thực hiện {N} là: {or_na(fix_other_province(d.get('executingAgencies'), prov))}")
    add(T("Mô tả cơ quan có thẩm quyền thực hiện"),
        f"Mô tả cơ quan có thẩm quyền thực hiện {N} là: {or_na(fix_other_province(d.get('delegatedAgencies'), prov))}")

    # 10-13. Cơ quan
    def agencies(*keys, extra=None):
        lst = []
        for k in keys:
            lst += names(d.get(k))
        if extra:
            lst.append(extra)
        return uniq(y for y in (localize_agency(x, prov) for x in lst) if y)

    executing = agencies("departmentsExecuting", "unitGroupsExecuting")
    if not executing and is_specific:
        executing = uniq(item.get("departments") or [])
    add(T("Cơ quan thực hiện"), f"Cơ quan thực hiện {N} là: {or_na(chr(10).join(executing))}")
    authority = agencies("departmentsAuthority", "unitGroupsAuthority")
    add(T("Cơ quan có thẩm quyền thực hiện"),
        f"Cơ quan có thẩm quyền thực hiện {N} là: {or_na(chr(10).join(authority))}")
    authorized = agencies("departmentsAuthorized", "unitGroupsAuthorized", extra=d.get("authorizedAgencies"))
    add(T("Cơ quan được ủy quyền thực hiện"),
        f"Cơ quan được ủy quyền thực hiện {N} là: {or_na(chr(10).join(authorized))}")
    coord = agencies("departmentsCoordinating", "unitGroupsCoordinating", extra=d.get("coordinatingAgencies"))
    add(T("Cơ quan phối hợp thực hiện"),
        f"Cơ quan phối hợp thực hiện {N} là: {or_na(chr(10).join(coord))}")

    # 14. Trình tự thực hiện
    steps = d.get("executionSteps") or []
    if steps:
        parts = [f"Trình tự thực hiện {N} {prov['in_phrase']}:"]
        for st in steps:
            parts.append(f"- Trường hợp {clean(st.get('name'))}:")
            parts.append(f"+ {clean(st.get('description')) or NA}")
        add(T("Trình tự thực hiện"), "\n".join(parts))
    else:
        add(T("Trình tự thực hiện"), f"Trình tự thực hiện {N} {prov['in_phrase']}: {NA}")

    # 15. Cấp thực hiện
    lv = []
    if d.get("isMinistry"):
        lv.append("Cấp Bộ")
    if d.get("isProvince"):
        lv.append("Cấp Tỉnh")
    if d.get("isWard"):
        lv.append("Cấp Xã")
    if d.get("isOtherAgency"):
        lv.append("Cơ quan khác")
    add(T("Cấp thực hiện"), f"Cấp thực hiện {N} là: {or_na(chr(10).join(lv))}")

    # 16. Lĩnh vực
    cats = uniq(names(d.get("categoriesDetails")) + list(item.get("categories") or []))
    add(T("Lĩnh vực thực hiện"), f"Lĩnh vực thực hiện {N} là: {or_na('; '.join(cats))}")

    # 17. Cách thức thực hiện (1 dòng / hình thức nộp)
    methods = sorted(d.get("executionMethods") or [], key=lambda m: SUBMIT_ORDER.get(m.get("submissionMethod"), 9))
    if not methods:
        add(T("Cách thức thực hiện"), f"Cách thức thực hiện {N}: {NA}")
    for m in methods:
        lines = [f"Cách thức thực hiện {N} - Hình thức nộp {SUBMIT.get(m.get('submissionMethod'), clean(m.get('submissionMethod')))}:",
                 "Thời gian:",
                 f"  - Thời gian giải quyết: {m.get('processingTime') if m.get('processingTime') not in (None, '') else NA}",
                 f"  - Đơn vị tính: {UNIT.get(m.get('processingTimeUnit'), clean(m.get('processingTimeUnit')) or NA)}",
                 f"  - Mô tả: {or_na(m.get('description'))}"]
        fees = m.get("fees") or []
        if fees:
            # gộp các mức phí trùng mô tả để nội dung gọn
            seen = []
            for f in fees:
                key = (clean(f.get("description")), f.get("value"))
                if key in seen:
                    continue
                seen.append(key)
                lines += ["  - Phí, lệ phí",
                          f"    + Đơn vị: {'Đồng' if 'Việt Nam' in (f.get('currencyName') or 'Việt Nam') or (f.get('currencyName') or '') in ('VND', '') else clean(f.get('currencyName'))}",
                          f"    + Số tiền: {fmt_money(f.get('value'))}",
                          f"    + Mô tả: {or_na(f.get('description'))}"]
        else:
            lines.append("  - Phí, lệ phí: Không có thông tin")
        add(T("Cách thức thực hiện"), "\n".join(lines) + "\n")

    # 18. Đối tượng thực hiện
    add(T("Đối tượng thực hiện"), f"Đối tượng thực hiện {N} là: {or_na(', '.join(subjects))}")

    # 19. Thành phần hồ sơ (1 dòng / trường hợp)
    page = DETAIL_PAGE.format(id=d.get("id") or item.get("id"))
    cases = d.get("executionCases") or []
    if not cases and d.get("profileComponents"):
        cases = [{"name": "", "profileComponents": d.get("profileComponents")}]
    if not cases:
        add(T("Thành phần hồ sơ của"), f"Thành phần hồ sơ {N}\n{NA}")
    for c in cases:
        cname = clean(c.get("name"))
        lines = [f"Thành phần hồ sơ {N}", cname if cname else "Bao gồm:"]
        comps = c.get("profileComponents") or []
        if not comps:
            lines.append(NA)
        for i, p in enumerate(comps, 1):
            att = [a for a in (p.get("attachments") or []) if isinstance(a, dict)]
            fnames = "; ".join(uniq(a.get("fileName") for a in att)) or NA
            lines += [f"{i}. Tên giấy tờ: {or_na(p.get('name'))}",
                      f"- Số bản chính: {p.get('originalQty') if p.get('originalQty') is not None else NA}",
                      f"- Số bản sao: {p.get('copyQty') if p.get('copyQty') is not None else NA}",
                      f"- Bắt buộc: {'Có' if p.get('required') else 'Không'}",
                      f"- Tên mẫu đơn: {fnames}",
                      f"- Mẫu đơn, tờ khai: {('Tải tại ' + page) if att else NA}",
                      f"- Mã giấy tờ: {or_na(p.get('code'))}"]
        add(T("Thành phần hồ sơ của"), "\n".join(lines) + "\n")

    # 20. Kết quả thực hiện
    res = d.get("resultsDetails") or []
    lines = [f"Kết quả thực hiện {N} là:"]
    if res:
        for i, r in enumerate(res, 1):
            lines += [f"{i}. Tên kết quả: {or_na(r.get('name'))}", f"- Mã kết quả: {or_na(r.get('code'))}"]
    else:
        lines.append(NA)
    rm = []
    for r in d.get("returningMethods") or []:
        vals = ", ".join(RETURN.get(v, v) for v in r.get("value") or [])
        if vals:
            rm.append(f"- {RETURN_TYPE.get(r.get('type'), r.get('type'))}: {vals}")
    if rm:
        lines += ["Hình thức nhận kết quả:"] + rm
    add(T("Kết quả thực hiện"), "\n".join(lines) + "\n")

    # 20b. Yêu cầu, điều kiện (bổ sung so với mẫu - có ích cho callbot)
    if opts.get("with_conditions", True):
        cond = clean(d.get("requirementsAndConditions") or d.get("description"))
        add(T("Yêu cầu, điều kiện thực hiện"), f"Yêu cầu, điều kiện thực hiện {N} là: {or_na(cond)}")

    # 21. Căn cứ pháp lý
    lb = d.get("legalBasisesDetails") or []
    lines = [f"Căn cứ pháp lý {N} là:"]
    if lb:
        for i, l in enumerate(lb, 1):
            lines += [f"{i}. Tên văn bản: {or_na(l.get('name'))}", f"- Số văn bản: {or_na(l.get('code'))}"]
    else:
        lines.append(NA)
    add(T("Căn cứ pháp lý"), "\n".join(lines) + "\n")

    # 22-23. TTHC liên quan / liên thông
    rel = []
    for g in d.get("procedureRelatedGroup") or []:
        if isinstance(g, dict):
            rel += [clean(x.get("name")) for x in (g.get("formalities") or g.get("items") or []) if isinstance(x, dict)]
            if g.get("name"):
                rel.append(clean(g.get("name")))
        elif isinstance(g, str):
            rel.append(clean(g))
    add(T("Thủ tục hành chính liên quan đến"),
        f"Thủ tục hành chính liên quan đến {N} là: {or_na('; '.join(uniq(rel)))}")
    lt = NA
    if (d.get("type") or item.get("type")) == "INTERCONNECTED":
        lt = "Đây là thủ tục hành chính liên thông" + (f": {clean(d.get('note'))}" if clean(d.get("note")) else "")
    add(T("Thủ tục hành chính liên thông đến"), f"Thủ tục hành chính liên thông đến {N} là: {lt}")

    ident = json.dumps({"uri": page, "type": 3, "title": N}, ensure_ascii=False)
    out = []
    for t, c in rows:  # Excel giới hạn 32.767 ký tự / ô -> tách thành nhiều dòng "(tiếp theo)"
        if len(c) <= MAX_CELL:
            out.append((t, c, ident))
            continue
        chunks, cur = [], ""
        for line in c.split("\n"):
            while len(line) > MAX_CELL:
                chunks.append(cur) if cur else None
                cur = ""
                chunks.append(line[:MAX_CELL])
                line = line[MAX_CELL:]
            if len(cur) + len(line) + 1 > MAX_CELL:
                chunks.append(cur)
                cur = line
            else:
                cur = f"{cur}\n{line}" if cur else line
        if cur:
            chunks.append(cur)
        for i, ch in enumerate(chunks):
            out.append((t if i == 0 else f"{t} (tiếp theo {i})", ch, ident))
    return out, N


def gen_questions(title_field, N):
    """Sinh vài câu hỏi mẫu (tuỳ chọn --with-questions)."""
    short = N if len(N) <= 90 else N[:90].rsplit(" ", 1)[0] + "..."
    m = {
        "Thành phần hồ sơ của": ["Hồ sơ {n} gồm những gì", "Làm {n} cần giấy tờ gì"],
        "Cách thức thực hiện": ["{n} mất bao lâu", "Lệ phí {n} là bao nhiêu", "Nộp hồ sơ {n} bằng cách nào"],
        "Trình tự thực hiện": ["Các bước thực hiện {n}", "Quy trình {n} như thế nào"],
        "Địa chỉ tiếp nhận": ["Nộp hồ sơ {n} ở đâu"],
        "Cơ quan thực hiện": ["Cơ quan nào giải quyết {n}"],
        "Kết quả thực hiện": ["Làm xong {n} thì nhận được gì"],
        "Căn cứ pháp lý": ["Căn cứ pháp lý của {n}"],
        "Yêu cầu, điều kiện thực hiện": ["Điều kiện để {n} là gì"],
        "Đối tượng thực hiện": ["Ai được thực hiện {n}"],
    }
    return ";".join(q.format(n=short) for q in m.get(title_field, []))


def load_raw(path):
    with gzip.open(path, "rt", encoding="utf-8") if path.endswith(".gz") else open(path, encoding="utf-8") as f:
        return json.load(f)


def generate(raw, prov, all_names, with_conditions=True):
    """Dùng chung cho build & update: trả về list (fid, detail, rows, tên TTHC) theo thứ tự ổn định."""
    OTHER_PROVINCE_NAMES[:] = [n for n in all_names if n != prov["short"]]
    lst, det = raw.get("list", {}), raw.get("details", {})
    out = []
    for fid in sorted(det, key=lambda i: ((det[i].get("category") or {}).get("name") or "", clean(det[i].get("name")))):
        d, item = det[fid], lst.get(fid, {})
        promul = d.get("departmentPromulgateName") or ""
        if re.match(r"^(UBND|Ủy ban)", promul) and prov["short"] not in promul:
            continue
        rows, N = build_rows(d, item, prov, {"with_conditions": with_conditions})
        out.append((fid, d, rows, N))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--province", required=True, help='Mã hoặc tên tỉnh/thành, ví dụ H32 hoặc "Khánh Hòa"')
    ap.add_argument("--out", default="auto", help="File .xlsx đầu ra (mặc định out/<PREFIX>_Noi_dung_callbot_<MÃ>.xlsx)")
    ap.add_argument("--provinces", default=os.path.join(HERE, "provinces.json"))
    ap.add_argument("--no-conditions", action="store_true", help="Bỏ dòng 'Yêu cầu, điều kiện thực hiện' để giống mẫu 100%%")
    ap.add_argument("--with-questions", action="store_true", help="Tự sinh câu hỏi mẫu vào cột C")
    ap.add_argument("--with-tags", action="store_true", help="Điền Tags = Lĩnh vực; Cấp thực hiện")
    ap.add_argument("--csv", action="store_true", help="Xuất thêm file .csv cạnh file .xlsx")
    args = ap.parse_args()

    sys.path.insert(0, HERE)
    import province_config
    pc, prov, all_names = province_config.resolve(args.province, args.provinces)
    OTHER_PROVINCE_NAMES[:] = [n for n in all_names if n != prov["short"]]
    if args.out == "auto":
        args.out = os.path.join("out", f"{prov['file_prefix']}_Noi_dung_callbot_{pc}.xlsx")

    with gzip.open(args.raw, "rt", encoding="utf-8") if args.raw.endswith(".gz") else open(args.raw, encoding="utf-8") as f:
        raw = json.load(f)
    lst, det = raw.get("list", {}), raw.get("details", {})

    # thứ tự: theo Lĩnh vực rồi tên, ổn định giữa các lần chạy
    def sort_key(fid):
        d = det[fid]
        return ((d.get("category") or {}).get("name") or "", clean(d.get("name")))

    fields_order = []
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet0"
    ws.append(HEADER)
    n_rows = n_proc = 0
    skipped = 0
    for fid in sorted(det, key=sort_key):
        d, item = det[fid], lst.get(fid, {})
        promul = d.get("departmentPromulgateName") or ""
        if re.match(r"^(UBND|Ủy ban)", promul) and prov["short"] not in promul:
            skipped += 1  # TTHC do UBND tỉnh/thành khác công bố
            continue
        rows, N = build_rows(d, item, prov, {"with_conditions": not args.no_conditions})
        tags = ""
        if args.with_tags:
            lvl = [x for x, k in (("Cấp Bộ", "isMinistry"), ("Cấp Tỉnh", "isProvince"), ("Cấp Xã", "isWard")) if d.get(k)]
            tags = ";".join(uniq(names(d.get("categoriesDetails")) + lvl + [prov["short"]]))
        for title, content, ident in rows:
            q = ""
            if args.with_questions:
                field = title[: title.find(N)].strip() if N in title else ""
                q = gen_questions(field, N)
            ws.append([title, content, q or None, tags or None, ident])
            n_rows += 1
        n_proc += 1

    ws.column_dimensions["A"].width = 60
    ws.column_dimensions["B"].width = 100
    ws.column_dimensions["C"].width = 30
    ws.column_dimensions["D"].width = 20
    ws.column_dimensions["E"].width = 60
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    wb.save(args.out)
    print(f"Đã ghi {args.out}: {n_proc} TTHC, {n_rows} dòng dữ liệu (bỏ {skipped} TTHC của tỉnh khác)")

    if args.csv:
        import csv
        p = os.path.splitext(args.out)[0] + ".csv"
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            for r in ws.iter_rows(values_only=True):
                w.writerow(["" if v is None else v for v in r])
        print(f"Đã ghi {p}")


if __name__ == "__main__":
    main()
