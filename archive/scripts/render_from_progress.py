from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from spu_utils import group_rows_to_spu


OUTPUT_DIR = Path("output")
ORDERED_BRANDS = ["参半", "笑容加", "高露洁", "佳洁士", "BOP", "白惜", "俊小白", "冷酸灵", "舒适达", "好来"]


def build_paths(month: str) -> dict[str, Path]:
    return {
        "progress": OUTPUT_DIR / f"{month}_brand_progress.jsonl",
        "summary_csv": OUTPUT_DIR / f"{month}_brand_latest.csv",
        "summary_md": OUTPUT_DIR / f"{month}_brand_latest.md",
        "detail_csv": OUTPUT_DIR / f"{month}_brand_details.csv",
        "detail_md": OUTPUT_DIR / f"{month}_brand_details.md",
        "summary_json": OUTPUT_DIR / f"{month}_brand_latest.json",
    }


def filing_month(value: str) -> str:
    text = str(value or "").strip()
    return text[:7] if len(text) >= 7 else ""


def normalize_rows(rows: list[dict], month: str) -> list[dict]:
    deduped: dict[tuple[str, str, str, str], dict] = {}
    for row in rows:
        if filing_month(row.get("filing_date", "")) != month:
            continue
        key = (
            str(row.get("product_name", "")),
            str(row.get("filing_no", "")),
            str(row.get("filing_date", "")),
            str(row.get("filer", "")),
        )
        deduped[key] = dict(row)
    result = list(deduped.values())
    result.sort(key=lambda row: (str(row.get("filing_date", "")), str(row.get("product_name", ""))), reverse=True)
    return result


def empty_item(brand: str, month: str) -> dict:
    return {
        "brand": brand,
        "month": month,
        "latest_filing_date": "",
        "product_name": "",
        "filing_no": "",
        "filer": "",
        "month_count": 0,
        "note": f"{month}未检索到备案记录",
        "month_rows": [],
        "spu_groups": [],
        "all_rows": [],
    }


def normalize_item(item: dict, month: str, brand: str) -> dict:
    raw_rows = item.get("month_rows") or item.get("all_rows") or []
    month_rows = normalize_rows(raw_rows, month)
    latest = month_rows[0] if month_rows else {}
    normalized = empty_item(brand, month)
    normalized.update(
        {
            "latest_filing_date": latest.get("filing_date", ""),
            "product_name": latest.get("product_name", ""),
            "filing_no": latest.get("filing_no", ""),
            "filer": latest.get("filer", ""),
            "month_count": len(month_rows),
            "note": f"{month}存在备案记录" if month_rows else f"{month}未检索到备案记录",
            "month_rows": month_rows,
            "spu_groups": group_rows_to_spu(month_rows),
            "all_rows": month_rows,
        }
    )
    return normalized


def load_items(progress_path: Path, month: str) -> list[dict]:
    items = [
        json.loads(line)
        for line in progress_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    deduped: dict[str, dict] = {}
    for item in items:
        deduped[item["brand"]] = item
    extras = sorted(brand for brand in deduped if brand not in ORDERED_BRANDS)
    ordered_brands = [*ORDERED_BRANDS, *extras]
    result: list[dict] = []
    for brand in ordered_brands:
        if brand in deduped:
            result.append(normalize_item(deduped[brand], month, brand))
        else:
            result.append(empty_item(brand, month))
    return result


def write_summary_csv(items: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "brand",
                "month",
                "latest_filing_date",
                "product_name",
                "filing_no",
                "filer",
                "month_count",
                "note",
            ],
        )
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "brand": item["brand"],
                    "month": item["month"],
                    "latest_filing_date": item["latest_filing_date"],
                    "product_name": item["product_name"],
                    "filing_no": item["filing_no"],
                    "filer": item["filer"],
                    "month_count": item["month_count"],
                    "note": item["note"],
                }
            )


def write_detail_csv(items: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "brand",
                "month",
                "seq",
                "product_name",
                "filing_no",
                "filing_date",
                "filer",
                "detail",
            ],
        )
        writer.writeheader()
        for item in items:
            for row in item["month_rows"]:
                writer.writerow(
                    {
                        "brand": item["brand"],
                        "month": item["month"],
                        "seq": row.get("seq", ""),
                        "product_name": row.get("product_name", ""),
                        "filing_no": row.get("filing_no", ""),
                        "filing_date": row.get("filing_date", ""),
                        "filer": row.get("filer", ""),
                        "detail": row.get("detail", ""),
                    }
                )


def write_summary_md(items: list[dict], path: Path, month: str) -> None:
    lines = [
        f"# {month} 国产牙膏备案品牌汇总",
        "",
        "数据来源：当前 Chrome 页面真实搜索结果与翻页抓取。",
        "当前版本仅保留目标月份命中的记录，不再携带品牌历史深页结果。",
        "",
        "| 品牌 | 最新备案日期 | 产品名称 | 备案编号 | 备案人 | 当月命中数 | 说明 |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for item in items:
        lines.append(
            f"| {item['brand']} | {item['latest_filing_date']} | {item['product_name']} | {item['filing_no']} | {item['filer']} | {item['month_count']} | {item['note']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_detail_md(items: list[dict], path: Path, month: str) -> None:
    lines = [
        f"# {month} 国产牙膏备案明细",
        "",
        "以下为各品牌在当月命中的全部备案记录。",
        "",
    ]
    for item in items:
        lines.append(f"## {item['brand']}")
        lines.append("")
        if not item["month_rows"]:
            lines.append("当月无命中记录。")
            lines.append("")
            continue
        lines.append("| 序号 | 备案日期 | 产品名称 | 备案编号 | 备案人 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in item["month_rows"]:
            lines.append(
                f"| {row.get('seq', '')} | {row.get('filing_date', '')} | {row.get('product_name', '')} | {row.get('filing_no', '')} | {row.get('filer', '')} |"
            )
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_json(items: list[dict], path: Path, month: str) -> None:
    enriched = []
    for item in items:
        copy = dict(item)
        copy["spu_groups"] = copy.get("spu_groups") or group_rows_to_spu(copy.get("month_rows", []))
        enriched.append(copy)
    path.write_text(
        json.dumps(
            {
                "month": month,
                "source": "current_chrome_page_month_hits",
                "capture_scope": "month_hits_only",
                "summary_count": len(enriched),
                "detail_count": sum(len(item["month_rows"]) for item in enriched),
                "results": enriched,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="根据 progress 文件生成指定月份的汇总产物。")
    parser.add_argument("--month", default="2026-06", help="目标月份，格式 YYYY-MM。")
    args = parser.parse_args()

    paths = build_paths(args.month)
    items = load_items(paths["progress"], args.month)
    write_summary_csv(items, paths["summary_csv"])
    write_detail_csv(items, paths["detail_csv"])
    write_summary_md(items, paths["summary_md"], args.month)
    write_detail_md(items, paths["detail_md"], args.month)
    write_summary_json(items, paths["summary_json"], args.month)
    print(str(paths["summary_json"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
