#!/usr/bin/env python3
"""Chạy trọn gói: thu thập + xuất Excel cho 1 tỉnh/thành. Chỉ cần đổi tên tỉnh.

    python run_all.py "Khánh Hòa"
    python run_all.py "Nghệ An" --limit 20          # chạy thử
    python run_all.py H19 --no-conditions           # tham số thêm được chuyển cho bước xuất Excel
    python run_all.py "Khánh Hòa" --skip-collect    # đã có data/H32_raw.json.gz, chỉ xuất lại Excel
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import province_config  # noqa: E402

COLLECT_FLAGS = {"--limit", "--workers"}
COLLECT_SWITCHES = {"--include-internal", "--resume"}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    name, rest = sys.argv[1], sys.argv[2:]
    code, cfg, _ = province_config.resolve(name)
    raw = os.path.join("data", f"{code}_raw.json.gz")
    out = os.path.join("out", f"{cfg['file_prefix']}_Noi_dung_callbot_{code}.xlsx")

    collect_args, build_args, skip = [], [], False
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--skip-collect":
            skip = True
        elif a in COLLECT_FLAGS:
            collect_args += [a, rest[i + 1]]
            i += 1
        elif a in COLLECT_SWITCHES:
            collect_args.append(a)
        else:
            build_args.append(a)
        i += 1

    print(f"== {cfg['display']} ({code}) ==")
    if not skip:
        subprocess.run([sys.executable, os.path.join(HERE, "collect_tthc.py"),
                        "--province", code, "--out", raw, *collect_args], check=True)
    subprocess.run([sys.executable, os.path.join(HERE, "build_callbot_excel.py"),
                    "--raw", raw, "--province", code, "--out", out, *build_args], check=True)
    print(f"\nXong -> {os.path.abspath(out)}")


if __name__ == "__main__":
    main()
