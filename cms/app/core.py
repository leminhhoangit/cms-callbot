"""Lõi CMS dữ liệu Callbot TTHC – SQLite, dùng lại script sinh nội dung có sẵn (scripts/build_callbot_excel.py) để
nội dung trong CMS và file Excel nạp callbot TRÙNG KHỚP với bộ công cụ hiện tại.

Bảng
  provinces   cấu hình tỉnh (khởi tạo từ scripts/provinces.json; sửa trong CMS, không ghi đè file JSON)
  procedures  TTHC theo tỉnh: thông tin chính + detail JSON gốc của cổng (để dựng lại khi đổi cấu hình tỉnh)
              change = NEW / CHANGED / SAME / REMOVED (so với lần nhập trước), review = NEED_REVIEW / APPROVED
  rows        dòng nội dung callbot (Tiêu đề, Nội dung, IdentificationInfo) + Câu hỏi / Tags biên tập tay
  imports     mỗi lần nhập dữ liệu (file raw nào, bao nhiêu Mới / Thay đổi / Đã gỡ)
  exports     mỗi lần xuất Excel (loại, ai xuất, file)
  audit       nhật ký mọi thao tác ghi
Luật
  - Câu hỏi / Tags giữ nguyên qua các lần nhập (khớp theo TTHC + Tiêu đề), giống update_tthc.py.
  - TTHC Mới / Thay đổi -> Cần duyệt; sửa Câu hỏi / Tags của TTHC đã duyệt -> Cần duyệt lại.
  - Duyệt cần tên người thao tác. Không xoá TTHC: "Đã gỡ" khỏi cổng vẫn lưu, liệt kê để xoá khỏi tập train.
"""
import gzip
import json
import os
import re
import sqlite3
import sys
import threading
from contextlib import closing
from datetime import datetime

CMS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(CMS_DIR)
SCRIPTS = os.path.join(ROOT, "scripts")
RAW_DIR = os.path.join(ROOT, "data")
sys.path.insert(0, SCRIPTS)
import build_callbot_excel as B  # noqa: E402
import province_config  # noqa: E402

HEADER = B.HEADER
REVIEW_VI = {"NEED_REVIEW": "Cần duyệt", "APPROVED": "Đã duyệt"}
CHANGE_VI = {"NEW": "Mới", "CHANGED": "Thay đổi", "SAME": "Không đổi", "REMOVED": "Đã gỡ khỏi cổng"}
EXPORT_VI = {"FULL": "Bộ đầy đủ", "APPROVED": "Chỉ TTHC đã duyệt", "CHANGES": "Bản cập nhật (Mới + Thay đổi của lần nhập gần nhất)"}
PROV_FIELDS = ("display", "short", "ubnd", "in_phrase", "center_address", "file_prefix")
_GEN_LOCK = threading.Lock()   # B.generate dùng biến toàn cục OTHER_PROVINCE_NAMES


class CmsError(ValueError):
    """Thao tác không hợp lệ – hiện cho người dùng."""


def data_dir():
    d = os.environ.get("CMS_DATA_DIR") or os.path.join(CMS_DIR, "data")
    os.makedirs(d, exist_ok=True)
    return d


def now():
    return datetime.now().isoformat(timespec="seconds")


def connect():
    c = sqlite3.connect(os.path.join(data_dir(), "cms.db"), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


SCHEMA = """
CREATE TABLE IF NOT EXISTS provinces (code TEXT PRIMARY KEY, display TEXT, short TEXT, ubnd TEXT, in_phrase TEXT, center_address TEXT,
  file_prefix TEXT, auto INTEGER DEFAULT 0, with_conditions INTEGER DEFAULT 1, updated_by TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS procedures (province TEXT NOT NULL, fid TEXT NOT NULL, uri TEXT, code TEXT, name TEXT, category TEXT, type TEXT,
  levels TEXT, portal_updated_at INTEGER, detail TEXT, item TEXT, status TEXT NOT NULL DEFAULT 'ACTIVE', change TEXT, review TEXT NOT NULL,
  reviewed_by TEXT, reviewed_at TEXT, last_import INTEGER, PRIMARY KEY (province, fid));
CREATE TABLE IF NOT EXISTS rows (province TEXT NOT NULL, fid TEXT NOT NULL, seq INTEGER NOT NULL, title TEXT NOT NULL, content TEXT,
  ident TEXT, questions TEXT, tags TEXT, PRIMARY KEY (province, fid, seq));
CREATE INDEX IF NOT EXISTS rows_title ON rows(province, fid, title);
CREATE INDEX IF NOT EXISTS rows_hasq ON rows(province, fid, (COALESCE(questions,'')<>''));
CREATE TABLE IF NOT EXISTS imports (id INTEGER PRIMARY KEY AUTOINCREMENT, province TEXT, source TEXT, fetched_at TEXT, at TEXT, actor TEXT,
  procedures INTEGER, rows INTEGER, added INTEGER, changed INTEGER, removed INTEGER, note TEXT);
CREATE TABLE IF NOT EXISTS exports (id INTEGER PRIMARY KEY AUTOINCREMENT, province TEXT, kind TEXT, at TEXT, actor TEXT, file TEXT,
  procedures INTEGER, rows INTEGER);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, actor TEXT, action TEXT, province TEXT, fid TEXT, detail TEXT);
"""


def init(c):
    c.executescript(SCHEMA)
    if "cmp_hash" not in {r[1] for r in c.execute("PRAGMA table_info(procedures)")}:
        c.execute("ALTER TABLE procedures ADD COLUMN cmp_hash TEXT")
    if not c.execute("SELECT 1 FROM provinces LIMIT 1").fetchone():
        seed_provinces(c)


def audit(c, actor, action, province=None, fid=None, detail=""):
    c.execute("INSERT INTO audit(at, actor, action, province, fid, detail) VALUES (?,?,?,?,?,?)",
              (now(), actor, action, province, fid, (detail or "")[:2000]))


def _actor(actor):
    a = (actor or "").strip()
    if not a:
        raise CmsError("Nhập tên người thao tác (góc trên bên phải) trước khi ghi")
    return a[:80]


# ------------------------------------------------------------------ tỉnh / thành
def seed_provinces(c):
    provs = province_config.load()
    for code, ubnd in provs.get("_codes", {}).items():
        cfg = provs[code] if code in provs else province_config._auto(code, ubnd)
        c.execute("INSERT OR IGNORE INTO provinces(code, display, short, ubnd, in_phrase, center_address, file_prefix, auto) VALUES (?,?,?,?,?,?,?,?)",
                  (code, *(cfg.get(k, "") for k in PROV_FIELDS), 1 if code not in provs else 0))


def provinces(c):
    return [dict(r) for r in c.execute("SELECT * FROM provinces ORDER BY display")]


def province(c, code):
    r = c.execute("SELECT * FROM provinces WHERE code=?", ((code or "").upper(),)).fetchone()
    if not r:
        raise CmsError(f"Không có tỉnh/thành {code}")
    return dict(r)


def update_province(c, code, actor, **kw):
    actor = _actor(actor)
    p = province(c, code)
    changed = {k: (v or "").strip() for k, v in kw.items() if k in PROV_FIELDS and v is not None and (v or "").strip() != (p[k] or "")}
    if "file_prefix" in changed and not re.fullmatch(r"[A-Z0-9]{2,6}", changed["file_prefix"]):
        raise CmsError("Tiền tố file: 2–6 chữ in hoa / số")
    if "with_conditions" in kw and kw["with_conditions"] is not None and int(bool(kw["with_conditions"])) != p["with_conditions"]:
        changed["with_conditions"] = int(bool(kw["with_conditions"]))
    if not changed:
        return p
    sets = ", ".join(f"{k}=?" for k in changed)
    c.execute(f"UPDATE provinces SET {sets}, auto=0, updated_by=?, updated_at=? WHERE code=?", (*changed.values(), actor, now(), p["code"]))
    audit(c, actor, "province_update", p["code"], detail="Sửa cấu hình: " + ", ".join(changed))
    return province(c, code)


def _all_short_names(c):
    return [r[0] for r in c.execute("SELECT short FROM provinces")]


# ------------------------------------------------------------------ nhập dữ liệu
def cms_raw_dir():
    """File CMS tải về – TÁCH khỏi data/ của bộ công cụ: update_tthc.py lấy file raw mới nhất trong data/ làm mốc so sánh,
    file chạy thử (vài thủ tục) để ở đó sẽ làm lần cập nhật tháng sau báo sai hàng nghìn "Mới"."""
    d = os.path.join(data_dir(), "raw")
    os.makedirs(d, exist_ok=True)
    return d


def raw_files(code=None):
    out = []
    for src, folder in (("tool", RAW_DIR), ("cms", cms_raw_dir())):
        if not os.path.isdir(folder):
            continue
        for f in sorted(os.listdir(folder)):
            m = re.match(r"(H\d{2})_raw.*\.json(\.gz)?$", f)
            if m and (not code or m.group(1) == code.upper()):
                p = os.path.join(folder, f)
                out.append({"name": f, "province": m.group(1), "size": os.path.getsize(p), "source": src,
                            "mtime": datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="seconds")})
    return sorted(out, key=lambda x: x["mtime"])


def raw_path(name):
    name = os.path.basename(name)
    for folder in (cms_raw_dir(), RAW_DIR):
        if os.path.exists(os.path.join(folder, name)):
            return os.path.join(folder, name)
    raise CmsError(f"Không có file {name}")


def _load_raw(path):
    with gzip.open(path, "rt", encoding="utf-8") if path.endswith(".gz") else open(path, encoding="utf-8") as f:
        return json.load(f)


def _generate(c, prov, raw):
    cfg = {k: prov[k] for k in PROV_FIELDS}
    with _GEN_LOCK:
        return B.generate(raw, cfg, _all_short_names(c), bool(prov["with_conditions"]))


# Cổng DVC trả cùng một danh sách (cơ quan, căn cứ pháp lý, đối tượng…) với THỨ TỰ khác nhau giữa các lần gọi
# (đo 22/10/2026: 1.979/2.023 thủ tục "thay đổi" chỉ do đảo thứ tự). So sánh trên bản đã chuẩn hoá thứ tự;
# nội dung LƯU / XUẤT vẫn là nguyên văn (trùng file của bộ công cụ).
_ORDERED = ("executionSteps", "executionMethods")
_AGENCY_STR = ("executingAgencies", "delegatedAgencies", "coordinatingAgencies", "authorizedAgencies")


def _canon_detail(d):
    out = dict(d)
    for k, v in d.items():
        if k in _AGENCY_STR and isinstance(v, str):
            out[k] = ", ".join(sorted(x.strip() for x in v.split(",") if x.strip()))
        elif k in _ORDERED or not isinstance(v, list) or not v:
            continue
        elif all(isinstance(x, dict) for x in v):
            out[k] = sorted(v, key=lambda x: (str(x.get("code") or ""), str(x.get("name") or ""), str(x.get("id") or "")))
        elif all(isinstance(x, str) for x in v):
            out[k] = sorted(v)
    return out


def _cmp_hashes(c, prov, raw):
    """{fid: băm nội dung sinh từ dữ liệu đã chuẩn hoá thứ tự} – dùng để quyết định Thay đổi / Không đổi."""
    import hashlib
    canon = {**raw, "details": {f: _canon_detail(d) for f, d in raw.get("details", {}).items()}}
    return {fid: hashlib.sha256(json.dumps([(B.clean(t), B.clean(ct)) for t, ct, _ in rows], ensure_ascii=False).encode()).hexdigest()
            for fid, _d, rows, _n in _generate(c, prov, canon)}


def _levels(d):
    return "; ".join(x for x, k in (("Cấp Bộ", "isMinistry"), ("Cấp Tỉnh", "isProvince"), ("Cấp Xã", "isWard")) if d.get(k))


def _apply(c, code, gen, items, import_id, actor, mark_removed=True, cmp=None):
    """Ghi bộ nội dung mới cho tỉnh, so với bộ đang có. Trả (added, changed, removed, rows).
    cmp = {fid: băm đã chuẩn hoá thứ tự} của bộ mới. Không đổi -> giữ nguyên dòng đã lưu (trạng thái duyệt + bản đã train ổn định)."""
    old = {r["fid"]: dict(r) for r in c.execute("SELECT fid, status, review, cmp_hash FROM procedures WHERE province=?", (code,))}
    missing = [f for f, o in old.items() if not o["cmp_hash"]]
    if missing:                                    # dữ liệu nhập trước khi có cmp_hash -> tính từ chi tiết đã lưu
        rs = [r for r in c.execute("SELECT fid, detail, item FROM procedures WHERE province=?", (code,)) if r["fid"] in set(missing)]
        prev_cmp = _cmp_hashes(c, province(c, code), {"details": {r["fid"]: json.loads(r["detail"]) for r in rs},
                                                       "list": {r["fid"]: json.loads(r["item"] or "{}") for r in rs}})
        for f, h in prev_cmp.items():
            old[f]["cmp_hash"] = h
            c.execute("UPDATE procedures SET cmp_hash=? WHERE province=? AND fid=?", (h, code, f))
    cmp = cmp or {}
    added = changed = n_rows = 0
    seen = set()
    for fid, d, rows, name in gen:
        seen.add(fid)
        new_rows = [(t, ct) for t, ct, _ in rows]          # lưu NGUYÊN VĂN như file Excel của bộ công cụ
        o = old.get(fid)
        if not o:
            change, added = "NEW", added + 1
        elif o["status"] == "REMOVED" or o["cmp_hash"] != cmp.get(fid):
            change, changed = "CHANGED", changed + 1
        else:
            change = "SAME"
        if change == "SAME":                       # chỉ đánh dấu, KHÔNG ghi đè nội dung / chi tiết đã lưu
            c.execute("UPDATE procedures SET change='SAME', last_import=? WHERE province=? AND fid=?", (import_id, code, fid))
            n_rows += len(new_rows)
            continue
        prev = c.execute("SELECT title, questions, tags FROM rows WHERE province=? AND fid=? ORDER BY seq", (code, fid)).fetchall()
        keep = {r["title"]: (r["questions"], r["tags"]) for r in prev if r["questions"] or r["tags"]}
        review = "NEED_REVIEW"
        uri = json.loads(rows[0][2])["uri"]
        cat = (d.get("category") or {}).get("name") or "; ".join(B.names(d.get("categoriesDetails")))
        c.execute("INSERT INTO procedures(province, fid, uri, code, name, category, type, levels, portal_updated_at, detail, item, status, change, review,"
                  " last_import, cmp_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,?,?,?) ON CONFLICT(province, fid) DO UPDATE SET uri=excluded.uri, code=excluded.code,"
                  " name=excluded.name, category=excluded.category, type=excluded.type, levels=excluded.levels, portal_updated_at=excluded.portal_updated_at,"
                  " detail=excluded.detail, item=excluded.item, status='ACTIVE', change=excluded.change, review=excluded.review,"
                  " reviewed_by=CASE WHEN excluded.review='APPROVED' THEN reviewed_by END, reviewed_at=CASE WHEN excluded.review='APPROVED' THEN reviewed_at END,"
                  " last_import=excluded.last_import, cmp_hash=excluded.cmp_hash",
                  (code, fid, uri, d.get("codeNotation") or d.get("code"), name, cat, d.get("type"), _levels(d), d.get("updatedAt"),
                   json.dumps(d, ensure_ascii=False), json.dumps(items.get(fid, {}), ensure_ascii=False), change, review, import_id, cmp.get(fid)))
        c.execute("DELETE FROM rows WHERE province=? AND fid=?", (code, fid))
        c.executemany("INSERT INTO rows(province, fid, seq, title, content, ident, questions, tags) VALUES (?,?,?,?,?,?,?,?)",
                      [(code, fid, i, t, ct, rows[i][2], *keep.get(t, (None, None))) for i, (t, ct) in enumerate(new_rows)])
        n_rows += len(new_rows)
    gone = [f for f, o in old.items() if f not in seen and o["status"] != "REMOVED"] if mark_removed else []
    for f in gone:
        c.execute("UPDATE procedures SET status='REMOVED', change='REMOVED', review='NEED_REVIEW', last_import=? WHERE province=? AND fid=?",
                  (import_id, code, f))
    for f in old:
        if f not in seen and f not in gone:
            c.execute("UPDATE procedures SET change='SAME' WHERE province=? AND fid=?", (code, f))
    return added, changed, len(gone), n_rows


def import_raw(c, code, path, actor, note=""):
    """Nhập 1 file raw (.json.gz từ collect_tthc.py / browser_collector.js) cho tỉnh."""
    actor = _actor(actor)
    prov = province(c, code)
    code = prov["code"]
    if not os.path.exists(path):
        raise CmsError(f"Không có file {path}")
    raw = _load_raw(path)
    pc = (raw.get("provinceCode") or code).upper()
    if pc != code:
        raise CmsError(f"File là dữ liệu của {pc}, không phải {code}")
    if not raw.get("details"):
        raise CmsError("File không có chi tiết TTHC (details rỗng)")
    gen = _generate(c, prov, raw)
    active = c.execute("SELECT COUNT(*) FROM procedures WHERE province=? AND status='ACTIVE'", (code,)).fetchone()[0]
    # rào chắn: file tải dở (có lỗi) hoặc ít hơn hẳn bộ đang có -> KHÔNG đánh dấu "Đã gỡ" (tránh gỡ nhầm hàng loạt)
    partial = bool(raw.get("failures")) or (active and len(gen) < 0.9 * active)
    if partial:
        note = (note + " | " if note else "") + f"Bộ dữ liệu không đầy đủ ({len(gen)} TTHC so với {active} đang có"
        note += f", {len(raw.get('failures') or [])} lỗi tải) – không đánh dấu Đã gỡ"
    cur = c.execute("INSERT INTO imports(province, source, fetched_at, at, actor, note) VALUES (?,?,?,?,?,?)",
                    (code, os.path.basename(path), raw.get("fetchedAt"), now(), actor, note[:500]))
    iid = cur.lastrowid
    added, changed, removed, n_rows = _apply(c, code, gen, raw.get("list", {}), iid, actor, mark_removed=not partial,
                                             cmp=_cmp_hashes(c, prov, raw))
    c.execute("UPDATE imports SET procedures=?, rows=?, added=?, changed=?, removed=? WHERE id=?", (len(gen), n_rows, added, changed, removed, iid))
    audit(c, actor, "import", code, detail=f"{os.path.basename(path)}: {len(gen)} TTHC, {n_rows} dòng – Mới {added}, Thay đổi {changed}, Đã gỡ {removed}")
    return dict(c.execute("SELECT * FROM imports WHERE id=?", (iid,)).fetchone())


def rebuild(c, code, actor):
    """Dựng lại nội dung từ dữ liệu đã lưu (sau khi sửa cấu hình tỉnh) – thay đổi đi qua luật duyệt như một lần nhập."""
    actor = _actor(actor)
    prov = province(c, code)
    code = prov["code"]
    rs = c.execute("SELECT fid, detail, item FROM procedures WHERE province=? AND status='ACTIVE'", (code,)).fetchall()
    if not rs:
        raise CmsError("Chưa có dữ liệu để dựng lại – nhập dữ liệu trước")
    raw = {"details": {r["fid"]: json.loads(r["detail"]) for r in rs}, "list": {r["fid"]: json.loads(r["item"] or "{}") for r in rs}}
    gen = _generate(c, prov, raw)
    iid = c.execute("INSERT INTO imports(province, source, at, actor, note) VALUES (?,?,?,?,?)",
                    (code, "(dựng lại từ dữ liệu đã lưu)", now(), actor, "Đổi cấu hình tỉnh")).lastrowid
    added, changed, removed, n_rows = _apply(c, code, gen, raw["list"], iid, actor, cmp=_cmp_hashes(c, prov, raw))
    c.execute("UPDATE imports SET procedures=?, rows=?, added=?, changed=?, removed=? WHERE id=?", (len(gen), n_rows, added, changed, removed, iid))
    audit(c, actor, "rebuild", code, detail=f"Dựng lại: Thay đổi {changed}, Đã gỡ {removed}")
    return dict(c.execute("SELECT * FROM imports WHERE id=?", (iid,)).fetchone())


def imports(c, code):
    return [dict(r) for r in c.execute("SELECT * FROM imports WHERE province=? ORDER BY id DESC", (code,))]


# ------------------------------------------------------------------ xem / tìm / biên tập / duyệt
def stats(c, code):
    q = lambda sql, *a: c.execute(sql, (code, *a)).fetchone()[0]  # noqa: E731
    total = q("SELECT COUNT(*) FROM procedures WHERE province=? AND status='ACTIVE'")
    # 1 truy vấn, chỉ đọc chỉ mục rows_hasq (không đọc nội dung dài)
    rows_total, rows_q = c.execute("SELECT COUNT(*), COALESCE(SUM(COALESCE(r.questions,'')<>''), 0) FROM rows r JOIN procedures p"
                                   " ON p.province=r.province AND p.fid=r.fid WHERE r.province=? AND p.status='ACTIVE'", (code,)).fetchone()
    last = c.execute("SELECT * FROM imports WHERE province=? ORDER BY id DESC LIMIT 1", (code,)).fetchone()
    return {"procedures": total, "rows": rows_total, "rows_with_questions": rows_q,
            "questions_pct": round(100 * rows_q / rows_total) if rows_total else None,
            "need_review": q("SELECT COUNT(*) FROM procedures WHERE province=? AND review='NEED_REVIEW'"),
            "approved": q("SELECT COUNT(*) FROM procedures WHERE province=? AND status='ACTIVE' AND review='APPROVED'"),
            "removed": q("SELECT COUNT(*) FROM procedures WHERE province=? AND status='REMOVED'"),
            "last_import": dict(last) if last else None}


def categories(c, code):
    return [r[0] for r in c.execute("SELECT DISTINCT category FROM procedures WHERE province=? AND category<>'' ORDER BY category", (code,))]


def search(c, code, q="", review="", change="", category="", status="ACTIVE", page=1, size=50):
    where, args = ["province=?"], [code]
    if status:
        where.append("status=?")
        args.append(status)
    if q:
        for w in q.split():
            where.append("(name LIKE ? OR code LIKE ?)")
            args += [f"%{w}%", f"%{w}%"]
    for col, v in (("review", review), ("change", change), ("category", category)):
        if v:
            where.append(f"{col}=?")
            args.append(v)
    w = " AND ".join(where)
    total = c.execute(f"SELECT COUNT(*) FROM procedures WHERE {w}", args).fetchone()[0]
    rs = c.execute(f"SELECT province, fid, uri, code, name, category, type, levels, status, change, review, reviewed_by, reviewed_at,"
                   f" (SELECT COUNT(*) FROM rows r WHERE r.province=p.province AND r.fid=p.fid) AS n_rows,"
                   f" (SELECT COUNT(*) FROM rows r WHERE r.province=p.province AND r.fid=p.fid AND COALESCE(r.questions,'')<>'') AS n_q"
                   f" FROM procedures p WHERE {w} ORDER BY category, name LIMIT ? OFFSET ?", (*args, size, (max(page, 1) - 1) * size)).fetchall()
    return {"total": total, "page": page, "size": size, "items": [dict(r) for r in rs]}


def procedure(c, code, fid):
    p = c.execute("SELECT * FROM procedures WHERE province=? AND fid=?", (code, fid)).fetchone()
    if not p:
        raise CmsError(f"Không có TTHC {fid}")
    p = dict(p)
    p.pop("detail", None)
    p.pop("item", None)
    p["rows"] = [dict(r) for r in c.execute("SELECT seq, title, content, questions, tags FROM rows WHERE province=? AND fid=? ORDER BY seq", (code, fid))]
    p["history"] = [dict(r) for r in c.execute("SELECT at, actor, action, detail FROM audit WHERE province=? AND fid=? ORDER BY id DESC LIMIT 50",
                                               (code, fid))]
    return p


def _norm_q(s):
    parts = [" ".join(x.split()) for x in (s or "").replace("\n", ";").split(";")]
    return ";".join(x for x in parts if x)[:4000] or None


def edit_rows(c, code, fid, actor, edits):
    """edits = {seq: (questions, tags)}. Đã duyệt + có thay đổi -> Cần duyệt lại."""
    actor = _actor(actor)
    p = procedure(c, code, fid)
    cur = {r["seq"]: r for r in p["rows"]}
    n = 0
    for seq, (qs, tags) in edits.items():
        r = cur.get(int(seq))
        if not r:
            continue
        nq, nt = _norm_q(qs), _norm_q(tags)
        if (nq, nt) != (r["questions"] or None, r["tags"] or None):
            c.execute("UPDATE rows SET questions=?, tags=? WHERE province=? AND fid=? AND seq=?", (nq, nt, code, fid, int(seq)))
            n += 1
    if n:
        if p["review"] == "APPROVED":
            c.execute("UPDATE procedures SET review='NEED_REVIEW', reviewed_by=NULL, reviewed_at=NULL WHERE province=? AND fid=?", (code, fid))
        audit(c, actor, "edit", code, fid, f"Sửa câu hỏi / tags {n} dòng")
    return n


def suggest_questions(c, code, fid, actor):
    """Điền câu hỏi mẫu theo luật (như --with-questions) cho các dòng CHƯA có câu hỏi."""
    p = procedure(c, code, fid)
    edits = {}
    for r in p["rows"]:
        if not r["questions"]:
            field = r["title"][: r["title"].find(p["name"])].strip() if p["name"] in r["title"] else ""
            q = B.gen_questions(field, p["name"])
            if q:
                edits[r["seq"]] = (q, r["tags"])
    return edit_rows(c, code, fid, actor, edits) if edits else 0


def set_review(c, code, fid, actor, approve=True):
    actor = _actor(actor)
    p = procedure(c, code, fid)
    if approve and p["status"] == "REMOVED":
        raise CmsError("TTHC đã gỡ khỏi cổng – không duyệt nội dung; xoá khỏi tập train callbot")
    if approve:
        c.execute("UPDATE procedures SET review='APPROVED', reviewed_by=?, reviewed_at=? WHERE province=? AND fid=?", (actor, now(), code, fid))
    else:
        c.execute("UPDATE procedures SET review='NEED_REVIEW', reviewed_by=NULL, reviewed_at=NULL WHERE province=? AND fid=?", (code, fid))
    audit(c, actor, "approve" if approve else "unapprove", code, fid, "Duyệt nội dung" if approve else "Bỏ duyệt")


# ------------------------------------------------------------------ xuất Excel nạp callbot
def export(c, code, kind, actor, only_approved=False):
    """FULL / APPROVED / CHANGES. Định dạng Sheet0 = 5 cột như bộ công cụ; CHANGES kèm sheet TongHop (Mới / Thay đổi / Đã gỡ)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    actor = _actor(actor)
    prov = province(c, code)
    if kind not in EXPORT_VI:
        raise CmsError("Loại xuất không hợp lệ")
    where = "p.province=? AND p.status='ACTIVE'"
    if kind == "APPROVED" or only_approved:
        where += " AND p.review='APPROVED'"
    if kind == "CHANGES":
        last = c.execute("SELECT MAX(id) FROM imports WHERE province=?", (code,)).fetchone()[0]
        where += f" AND p.change IN ('NEW','CHANGED') AND p.last_import={int(last or 0)}"
    procs = c.execute(f"SELECT p.fid, p.name, p.category, p.code, p.change, p.portal_updated_at, p.uri FROM procedures p WHERE {where}"
                      " ORDER BY p.category, p.name", (code,)).fetchall()
    if not procs and kind != "CHANGES":
        raise CmsError("Không có TTHC nào thoả điều kiện xuất")
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet0"
    ws.append(HEADER)
    n = 0
    for p in procs:
        for r in c.execute("SELECT title, content, questions, tags, ident FROM rows WHERE province=? AND fid=? ORDER BY seq", (code, p["fid"])):
            ws.append([r["title"], r["content"], r["questions"], r["tags"], r["ident"]])
            n += 1
    for col, w in zip("ABCDE", (60, 100, 30, 20, 60)):
        ws.column_dimensions[col].width = w
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"
    if kind == "CHANGES":
        sm = wb.create_sheet("TongHop")
        sm.append(["Trạng thái", "Mã TTHC", "Tên thủ tục", "Lĩnh vực", "Ngày cập nhật trên cổng", "URI"])
        for p in procs:
            sm.append([CHANGE_VI[p["change"]], p["code"], p["name"], p["category"], _ts(p["portal_updated_at"]), p["uri"]])
        last = c.execute("SELECT MAX(id) FROM imports WHERE province=?", (code,)).fetchone()[0]
        for p in c.execute("SELECT code, name, category, uri FROM procedures WHERE province=? AND status='REMOVED' AND last_import=?", (code, last)):
            sm.append(["Đã gỡ / không còn trên cổng", p["code"], p["name"], p["category"], "", p["uri"]])
        for cell in sm[1]:
            cell.font = Font(bold=True)
    out_dir = os.path.join(data_dir(), "exports")
    os.makedirs(out_dir, exist_ok=True)
    tag = {"FULL": "Noi_dung_callbot", "APPROVED": "Noi_dung_callbot_DaDuyet", "CHANGES": "CapNhat"}[kind]
    name = f"{prov['file_prefix']}_{tag}_{code}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    wb.save(os.path.join(out_dir, name))
    eid = c.execute("INSERT INTO exports(province, kind, at, actor, file, procedures, rows) VALUES (?,?,?,?,?,?,?)",
                    (code, kind, now(), actor, name, len(procs), n)).lastrowid
    audit(c, actor, "export", code, detail=f"{EXPORT_VI[kind]}{' (chỉ đã duyệt)' if only_approved else ''}: {len(procs)} TTHC, {n} dòng -> {name}")
    return dict(c.execute("SELECT * FROM exports WHERE id=?", (eid,)).fetchone())


def _ts(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return ""


def exports(c, code):
    return [dict(r) for r in c.execute("SELECT * FROM exports WHERE province=? ORDER BY id DESC", (code,))]


def export_path(name):
    p = os.path.join(data_dir(), "exports", os.path.basename(name))
    if not os.path.exists(p):
        raise CmsError("Không có file")
    return p


def audit_log(c, limit=300):
    return [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]

