from __future__ import annotations

import argparse
import asyncio
import csv
import json
from http.cookiejar import MozillaCookieJar
import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Error as PlaywrightError, Page, Request, Response, async_playwright


DEFAULT_BRANDS = [
    "参半",
    "笑容加",
    "高露洁",
    "佳洁士",
    "BOP",
    "白惜",
    "俊小白",
    "冷酸灵",
    "舒适达",
    "好来",
]

TARGET_URL = "https://www.nmpa.gov.cn/datasearch/home-index.html#category=hzp"
OUTPUT_DIR = Path("output")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)


@dataclass
class RegistrationRecord:
    brand: str
    product_name: str = ""
    filing_no: str = ""
    registrant: str = ""
    filer: str = ""
    filing_date: str = ""
    detail_url: str = ""
    source: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def previous_month_window(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    first_of_this_month = today.replace(day=1)
    last_of_previous_month = first_of_this_month - timedelta(days=1)
    first_of_previous_month = last_of_previous_month.replace(day=1)
    return first_of_previous_month, last_of_previous_month


def load_brands(path: str | None) -> list[str]:
    if not path:
        return DEFAULT_BRANDS
    brand_path = Path(path)
    data = json.loads(brand_path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("品牌文件必须是字符串数组 JSON。")
    return data


def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def load_cookie_file(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return []
    cookie_jar = MozillaCookieJar()
    cookie_jar.load(path, ignore_discard=True, ignore_expires=True)
    cookies: list[dict[str, Any]] = []
    for cookie in cookie_jar:
        cookies.append(
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "expires": cookie.expires or -1,
                "httpOnly": False,
                "secure": cookie.secure,
                "sameSite": "Lax",
            }
        )
    return cookies


def looks_like_date(value: str) -> bool:
    return bool(re.search(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}", value))


def parse_date(value: str) -> date | None:
    cleaned = value.strip()
    patterns = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y年%m月%d日",
    ]
    for fmt in patterns:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(\d{4})\D(\d{1,2})\D(\d{1,2})", cleaned)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_date_in_payload(payload: Any) -> str:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, str) and ("日期" in key or "时间" in key or "date" in key.lower()) and looks_like_date(value):
                return value
        for value in payload.values():
            found = find_date_in_payload(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_date_in_payload(item)
            if found:
                return found
    return ""


def collect_string(payload: dict[str, Any], candidates: list[str]) -> str:
    lowered = {str(k).lower(): v for k, v in payload.items()}
    for candidate in candidates:
        if candidate in payload and isinstance(payload[candidate], str):
            return payload[candidate].strip()
        if candidate.lower() in lowered and isinstance(lowered[candidate.lower()], str):
            return lowered[candidate.lower()].strip()
    return ""


def normalize_record(brand: str, payload: dict[str, Any], source: str) -> RegistrationRecord:
    return RegistrationRecord(
        brand=brand,
        product_name=collect_string(payload, ["productName", "产品名称", "name", "title", "toothpasteName"]),
        filing_no=collect_string(payload, ["filingNo", "备案编号", "recordNo", "number"]),
        registrant=collect_string(payload, ["registrant", "注册人", "备案人"]),
        filer=collect_string(payload, ["filer", "备案企业", "生产企业", "企业名称"]),
        filing_date=find_date_in_payload(payload),
        detail_url=collect_string(payload, ["detailUrl", "详情链接", "url"]),
        source=source,
        raw=payload,
    )


class NetworkRecorder:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.json_responses: list[dict[str, Any]] = []

    async def on_request(self, request: Request) -> None:
        if any(token in request.url.lower() for token in ["search", "query", "data", "record", "hzp"]):
            self.requests.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "headers": await request.all_headers(),
                    "post_data": request.post_data,
                    "resource_type": request.resource_type,
                }
            )

    async def on_response(self, response: Response) -> None:
        content_type = (response.headers or {}).get("content-type", "")
        if "application/json" not in content_type.lower():
            return
        try:
            payload = await response.json()
        except Exception:
            return
        self.json_responses.append(
            {
                "url": response.url,
                "status": response.status,
                "content_type": content_type,
                "payload": payload,
            }
        )


async def setup_context(
    headless: bool,
    cookie_file: str | None,
) -> tuple[BrowserContext, Page, NetworkRecorder]:
    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
    except PlaywrightError as exc:
        message = str(exc)
        if "Executable doesn't exist" in message:
            raise RuntimeError(
                "未检测到 Playwright 浏览器内核。请先运行 `playwright install chromium`，再执行脚本。"
            ) from exc
        raise
    context = await browser.new_context(
        locale="zh-CN",
        user_agent=DEFAULT_USER_AGENT,
        viewport={"width": 1366, "height": 900},
    )
    cookies = load_cookie_file(cookie_file)
    if cookies:
        await context.add_cookies(cookies)
    page = await context.new_page()
    recorder = NetworkRecorder()
    page.on("request", lambda request: asyncio.create_task(recorder.on_request(request)))
    page.on("response", lambda response: asyncio.create_task(recorder.on_response(response)))
    page.set_default_timeout(15000)
    await page.add_init_script(
        """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
Object.defineProperty(navigator, 'language', { get: () => 'zh-CN' });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
        """
    )
    return context, page, recorder


async def collect_page_debug(page: Page) -> dict[str, Any]:
    return await page.evaluate(
        """() => ({
            url: location.href,
            title: document.title,
            text: (document.body?.innerText || "").slice(0, 3000),
            htmlLength: document.documentElement.outerHTML.length,
            inputs: Array.from(document.querySelectorAll("input,button,select,textarea")).slice(0, 20).map((el) => ({
                tag: el.tagName,
                type: el.getAttribute("type"),
                text: (el.textContent || "").trim().slice(0, 50),
                placeholder: el.getAttribute("placeholder"),
                value: "value" in el ? el.value : null
            }))
        })"""
    )


def flatten_payload_to_records(brand: str, responses: list[dict[str, Any]]) -> list[RegistrationRecord]:
    records: list[RegistrationRecord] = []

    def walk(node: Any, source: str) -> None:
        if isinstance(node, dict):
            values = list(node.values())
            if any(isinstance(value, str) and brand.lower() in value.lower() for value in values if isinstance(value, str)):
                records.append(normalize_record(brand, node, source))
            for value in values:
                walk(value, source)
        elif isinstance(node, list):
            for item in node:
                walk(item, source)

    for response in responses:
        walk(response["payload"], response["url"])
    unique: list[RegistrationRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for item in records:
        key = (item.product_name, item.filing_no, item.filing_date)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def filter_last_month(records: list[RegistrationRecord], start: date, end: date) -> list[RegistrationRecord]:
    filtered: list[RegistrationRecord] = []
    for record in records:
        parsed = parse_date(record.filing_date) if record.filing_date else None
        if parsed and start <= parsed <= end:
            filtered.append(record)
    return filtered


async def run(
    brand_file: str | None,
    headless: bool,
    pause_seconds: int,
    cookie_file: str | None,
) -> int:
    brands = load_brands(brand_file)
    start, end = previous_month_window()
    ensure_output_dir()

    context, page, recorder = await setup_context(headless=headless, cookie_file=cookie_file)
    try:
        await page.goto(TARGET_URL, wait_until="domcontentloaded")
        if pause_seconds:
            await page.wait_for_timeout(pause_seconds * 1000)

        page_debug = await collect_page_debug(page)
        (OUTPUT_DIR / "page_debug.json").write_text(
            json.dumps(page_debug, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        results: dict[str, list[RegistrationRecord]] = {}
        for brand in brands:
            results[brand] = filter_last_month(
                flatten_payload_to_records(brand, recorder.json_responses),
                start,
                end,
            )

        serializable = {
            "target_url": TARGET_URL,
            "capture_time": datetime.now().isoformat(timespec="seconds"),
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "brands": brands,
            "request_count": len(recorder.requests),
            "json_response_count": len(recorder.json_responses),
            "cookie_file": cookie_file or "",
            "requests": recorder.requests,
            "results": {brand: [asdict(item) for item in items] for brand, items in results.items()},
        }
        (OUTPUT_DIR / "run_result.json").write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        with (OUTPUT_DIR / "summary.csv").open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "brand",
                    "product_name",
                    "filing_no",
                    "registrant",
                    "filer",
                    "filing_date",
                    "detail_url",
                    "source",
                ],
            )
            writer.writeheader()
            for brand, items in results.items():
                for item in items:
                    writer.writerow(
                        {
                            "brand": brand,
                            "product_name": item.product_name,
                            "filing_no": item.filing_no,
                            "registrant": item.registrant,
                            "filer": item.filer,
                            "filing_date": item.filing_date,
                            "detail_url": item.detail_url,
                            "source": item.source,
                        }
                    )

        return 0
    finally:
        await context.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="追踪国家药监局国产牙膏备案信息。")
    parser.add_argument("--brands", help="品牌 JSON 文件路径，默认使用内置品牌列表。")
    parser.add_argument("--show-browser", action="store_true", help="显示浏览器，便于观察或手动处理站点校验。")
    parser.add_argument("--pause-seconds", type=int, default=8, help="打开页面后等待秒数，默认 8 秒。")
    parser.add_argument(
        "--cookie-file",
        help="可选的 Netscape/Mozilla cookie 文件路径，用于复用人工浏览器会话。",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(
        run(
            brand_file=args.brands,
            headless=not args.show_browser,
            pause_seconds=args.pause_seconds,
            cookie_file=args.cookie_file,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
