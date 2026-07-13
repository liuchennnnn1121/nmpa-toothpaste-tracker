from __future__ import annotations

from collections import OrderedDict
from typing import Any


def clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def derive_spu_name(product_name: str) -> str:
    name = clean_text(product_name)
    if not name:
        return ""
    idx = name.rfind("牙膏")
    if idx != -1:
        return name[: idx + 2]
    for sep in ("（", "(", "-", " - ", "/", " / "):
        if sep in name:
            return clean_text(name.split(sep, 1)[0])
    return name


def group_rows_to_spu(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in rows:
        spu_name = derive_spu_name(str(row.get("product_name", "")))
        key = spu_name or clean_text(str(row.get("product_name", ""))) or "未命名SPU"
        entry = dict(row)
        entry["spu_name"] = spu_name or key
        group = groups.setdefault(
            key,
            {
                "spu_name": spu_name or key,
                "sku_count": 0,
                "latest_filing_date": "",
                "latest_product_name": "",
                "filers": [],
                "rows": [],
            },
        )
        group["rows"].append(entry)
        group["sku_count"] += 1
        filing_date = str(entry.get("filing_date", ""))
        latest_filing_date = str(group.get("latest_filing_date", ""))
        if filing_date >= latest_filing_date:
            group["latest_filing_date"] = filing_date
            group["latest_product_name"] = str(entry.get("product_name", ""))
        filer = clean_text(str(entry.get("filer", "")))
        if filer and filer not in group["filers"]:
            group["filers"].append(filer)

    values = list(groups.values())
    values.sort(
        key=lambda item: (
            str(item.get("latest_filing_date", "")),
            str(item.get("spu_name", "")),
        ),
        reverse=True,
    )
    return values
