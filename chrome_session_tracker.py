from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from spu_utils import group_rows_to_spu


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

OUTPUT_DIR = Path("output")
MONTHLY_DIR = OUTPUT_DIR / "monthly"
PROGRESS_DIR = OUTPUT_DIR / "progress"
PACKAGE_DIR = OUTPUT_DIR / "package_images"
PACKAGE_PDF_DIR = OUTPUT_DIR / "package_pdfs"
PACKAGE_RENDER_DIR = OUTPUT_DIR / "package_renders"
SEARCH_ITEM_ID = "ff8080818e63c900018e787bc48d0598"
SEARCH_RESULT_URL = "https://www.nmpa.gov.cn/datasearch/search-result.html"
HOME_INDEX_URL = "https://www.nmpa.gov.cn/datasearch/home-index.html#category=hzp"
PACKAGE_LINK_ITEM_ID = "ff8080818e63c900018e7884a67f0623"
NMPA_TAB_KEY = "codex-tab:nmpa-worker"
NMPA_WORKER_NAME = "nmpa-worker"
NMPA_URL_FILTER = "nmpa.gov.cn/datasearch"
DOWNLOADS_DIR = Path.home() / "Downloads"


@dataclass
class Row:
    seq: str
    product_name: str
    filing_no: str
    filing_date: str
    filer: str
    detail: str
    detail_url: str
    package_info_status: str
    package_images: list[str]


def row_package_bucket(month: str, brand: str, filing_no: str) -> Path:
    return Path(month) / safe_name(brand) / safe_name(filing_no)


def file_extension_from_name(name: str, fallback: str = ".bin") -> str:
    suffix = Path(str(name or "")).suffix.lower()
    if suffix:
        return suffix
    return fallback


def detail_url_from_row(row: dict[str, str]) -> str:
    detail_url = str(row.get("detail_url", "") or "").strip()
    if detail_url:
        return detail_url
    filing_no = str(row.get("filing_no", "") or "").strip()
    if not filing_no:
        return ""
    script = f"""
    (function(){{
      var rows=[...document.querySelectorAll("tbody tr")];
      var filing={json.dumps(filing_no)};
      var target=rows.find(function(tr){{
        var tds=[...tr.querySelectorAll("td")].map(function(td){{ return String(td.innerText||"").replace(/\\s+/g," ").trim(); }});
        return (tds[2]||"")===filing || (tds[2]||"").startsWith(filing.replace(/\\.\\.\\.$/, ""));
      }});
      if(!target) return "";
      var btn=target.querySelector("td:last-child button");
      if(!btn) return "";
      btn.click();
      return "clicked";
    }})()
    """
    result = execute_on_tab("nmpa.gov.cn/datasearch/search-result.html", script)
    if result != "clicked":
        return ""
    time.sleep(2)
    current_url = execute_on_tab("nmpa.gov.cn/datasearch/search-info.html", "location.href")
    return current_url.strip()


def locate_row_on_result_pages(target_row: dict[str, str], settle_seconds: float) -> dict[str, str] | None:
    target_identity = row_identity(target_row)
    seen_pages: set[str] = set()
    state = read_page_state()
    for _ in range(40):
        page = str(state.get("page", "") or "")
        if page in seen_pages:
            break
        seen_pages.add(page)
        rows = [row for row in state.get("rows", []) if isinstance(row, dict)]
        for index, page_row in enumerate(rows, start=1):
            if row_identity(page_row) == target_identity:
                matched = dict(page_row)
                matched["_page"] = page
                matched["_page_row_index"] = str(index)
                return matched
        if not state.get("has_next"):
            break
        click_next_page()
        time.sleep(settle_seconds)
        state = read_page_state()
    return None


def return_to_brand_result_page(brand: str, target_page: str, settle_seconds: float) -> dict[str, object]:
    try:
        execute_on_tab("nmpa.gov.cn/datasearch/search-info.html", 'history.back(); "ok";')
        state = wait_for_result_page(target_page, settle_seconds, retries=6)
        if str(state.get("page", "") or "") == str(target_page or ""):
            return state
    except Exception:
        pass
    navigate_brand_result(brand)
    state = wait_for_brand_rows(brand, settle_seconds)
    if str(target_page or "1") != "1":
        state = go_to_page_number(str(target_page), settle_seconds)
    return state


def enrich_rows_with_detail_and_package(
    brand: str,
    rows: list[dict[str, str]],
    month: str,
    settle_seconds: float,
) -> list[dict[str, str]]:
    if not rows:
        return []

    ordered_rows = [dict(row) for row in rows]
    ordered_rows.sort(
        key=lambda row: (
            int(str(row.get("_page", "9999") or "9999")),
            int(str(row.get("_page_row_index", "9999") or "9999")),
            str(row.get("filing_date", "") or ""),
        )
    )

    current_state = return_to_brand_result_page(brand, "1", settle_seconds)
    current_page = str(current_state.get("page", "") or "1")
    enriched: list[dict[str, str]] = []

    for item in ordered_rows:
        item.setdefault("package_images", [])
        item.setdefault("package_info_status", "")
        target_page = str(item.get("_page", "") or "")
        target_row_index = str(item.get("_page_row_index", "") or "")

        if not target_page or not target_row_index:
            current_state = return_to_brand_result_page(brand, "1", settle_seconds)
            located = locate_row_on_result_pages(item, settle_seconds)
            if not located:
                item["detail_url"] = ""
                item["package_info_status"] = "no_detail_url"
                item["package_images"] = []
                enriched.append(item)
                continue
            item.update({"_page": located["_page"], "_page_row_index": located["_page_row_index"]})
            target_page = str(item.get("_page", "") or "")
            target_row_index = str(item.get("_page_row_index", "") or "")
            current_page = "1"

        if current_page != target_page:
            current_state = return_to_brand_result_page(brand, target_page, settle_seconds)
            current_page = str(current_state.get("page", "") or target_page)

        clicked = click_detail_button_for_row_index(int(target_row_index))
        if clicked != "clicked":
            item["detail_url"] = ""
            item["package_info_status"] = "detail_button_not_found"
            item["package_images"] = []
            enriched.append(item)
            current_state = return_to_brand_result_page(brand, target_page, settle_seconds)
            current_page = str(current_state.get("page", "") or target_page)
            continue

        detail_url = wait_for_detail_page(settle_seconds)
        item["detail_url"] = detail_url
        if detail_url:
            item = enrich_row_detail_and_package(item, month, brand)
        else:
            item["package_info_status"] = "no_detail_url"
            item["package_images"] = []

        enriched.append(item)
        current_state = return_to_brand_result_page(brand, target_page, settle_seconds)
        current_page = str(current_state.get("page", "") or target_page)

    enriched.sort(key=lambda row: (str(row.get("filing_date", "")), str(row.get("product_name", ""))), reverse=True)
    return enriched


def safe_name(value: str) -> str:
    text = re.sub(r"[^\w\-.]+", "_", str(value or "").strip(), flags=re.UNICODE)
    text = text.strip("._")
    return text or "item"


def run_in_page_world(expression: str, storage_key: str | None = None, poll_seconds: float = 10.0) -> str:
    key = storage_key or f"codex_bridge_{int(time.time() * 1000)}"
    escaped_expr = expression.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    script = f"""
    (function(){{
      localStorage.removeItem("{key}");
      var s = document.createElement("script");
      s.text = `
        (async function(){{
          try {{
            const __codex_result = await (async function(){{ return {escaped_expr}; }})();
            localStorage.setItem("{key}", JSON.stringify({{ ok: true, value: __codex_result }}));
          }} catch (error) {{
            localStorage.setItem("{key}", JSON.stringify({{ ok: false, error: String(error && error.message ? error.message : error) }}));
          }}
        }})();`;
      document.documentElement.appendChild(s);
      s.remove();
      return "started";
    }})()
    """
    execute_on_tab(NMPA_TAB_KEY, script)
    deadline = time.time() + poll_seconds
    last_raw = ""
    while time.time() < deadline:
        time.sleep(0.4)
        raw = execute_on_tab(NMPA_TAB_KEY, f'(function(){{ return localStorage.getItem("{key}") || ""; }})()')
        if not raw:
            continue
        last_raw = raw
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        execute_on_tab(NMPA_TAB_KEY, f'(function(){{ localStorage.removeItem("{key}"); return "ok"; }})()')
        if not payload.get("ok"):
            raise RuntimeError(str(payload.get("error") or payload))
        value = payload.get("value", "")
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    execute_on_tab(NMPA_TAB_KEY, f'(function(){{ localStorage.removeItem("{key}"); return "ok"; }})()')
    raise RuntimeError(f"页面脚本执行超时: {last_raw[:200]}")


def current_nmpa_page_health() -> dict[str, object]:
    script = """
    (function(){
      var text = (document.body && document.body.innerText) ? document.body.innerText : "";
      var searchInput = document.querySelector('input.el-input__inner[placeholder*="请输入产品名称中文"]');
      var selectInput = document.querySelector('input.el-input__inner[readonly][placeholder*="请选择"]');
      return JSON.stringify({
        href: location.href,
        title: document.title || "",
        ready: document.readyState || "",
        scripts: document.scripts ? document.scripts.length : 0,
        text_len: String(text || "").trim().length,
        has_search_input: !!searchInput,
        has_select_input: !!selectInput
      });
    })()
    """
    raw = execute_on_tab(NMPA_TAB_KEY, script)
    return json.loads(raw) if raw else {}


def wait_for_nmpa_ready_page(timeout_seconds: float = 20.0) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_state: dict[str, object] = {}
    while time.time() < deadline:
        try:
            state = current_nmpa_page_health()
        except Exception:
            time.sleep(0.8)
            continue
        last_state = state
        title = str(state.get("title", "") or "").strip()
        scripts = int(state.get("scripts", 0) or 0)
        text_len = int(state.get("text_len", 0) or 0)
        ready = str(state.get("ready", "") or "")
        has_search_input = bool(state.get("has_search_input"))
        has_select_input = bool(state.get("has_select_input"))
        if ready == "complete" and title and scripts >= 10 and (text_len >= 50 or (has_search_input and has_select_input)):
            return state
        time.sleep(0.8)
    raise RuntimeError(f"NMPA 页面未就绪: {last_state}")


def ensure_nmpa_runtime_page() -> None:
    ensure_chrome_nmpa_tab()
    try:
        state = current_nmpa_page_health()
        title = str(state.get("title", "") or "").strip()
        scripts = int(state.get("scripts", 0) or 0)
        text_len = int(state.get("text_len", 0) or 0)
        ready = str(state.get("ready", "") or "")
        has_search_input = bool(state.get("has_search_input"))
        has_select_input = bool(state.get("has_select_input"))
        if ready == "complete" and title and scripts >= 10 and (text_len >= 50 or (has_search_input and has_select_input)):
            return
    except Exception:
        pass
    navigate_tab(NMPA_URL_FILTER, HOME_INDEX_URL)
    wait_for_nmpa_ready_page()
    try:
        execute_on_tab(NMPA_URL_FILTER, f'window.name = "{NMPA_WORKER_NAME}"; "ok";')
    except Exception:
        pass


def nmpa_api_bootstrap_js() -> str:
    return """
    (async function(){
      if (!window.__codex_api_ready) {
        const [apiText, ajaxText] = await Promise.all([
          fetch('js/api.js').then((r) => r.text()),
          fetch('js/ajax.js').then((r) => r.text()),
        ]);
        eval(apiText);
        eval(ajaxText);
        window.__codex_api_ready = true;
      }
      return true;
    })()
    """


def nmpa_query_list(brand: str, page_num: int, page_size: int = 10) -> dict[str, object]:
    ensure_nmpa_runtime_page()
    expression = f"""(async function(){{
      const [axiosText, md5Text, base64Text, utilText, apiText, ajaxText] = await Promise.all([
        fetch('js/axios.min.js').then((r) => r.text()),
        fetch('js/md5.js').then((r) => r.text()),
        fetch('js/base64.js').then((r) => r.text()),
        fetch('js/util.js').then((r) => r.text()),
        fetch('js/api.js').then((r) => r.text()),
        fetch('js/ajax.js').then((r) => r.text()),
      ]);
      eval(axiosText);
      eval(md5Text);
      eval(base64Text);
      eval(utilText);
      eval(apiText);
      eval(ajaxText);
      if (typeof pajax !== 'object' || typeof api !== 'object' || typeof api.queryList !== 'string') {{
        throw new Error('nmpa_runtime_not_ready:list');
      }}
      const resp = await pajax.hasTokenGet(api.queryList, {{
        itemId: {json.dumps(SEARCH_ITEM_ID)},
        isSenior: 'N',
        searchValue: {json.dumps(brand)},
        pageNum: {int(page_num)},
        pageSize: {int(page_size)}
      }});
      return JSON.stringify(resp.data || {{}});
    }})()"""
    try:
        raw = run_in_page_world(expression, storage_key=f"codex_list_{safe_name(brand)}_{page_num}")
    except RuntimeError:
        ensure_nmpa_runtime_page()
        raw = run_in_page_world(expression, storage_key=f"codex_list_{safe_name(brand)}_{page_num}_retry")
    return json.loads(raw) if raw else {}


def nmpa_query_detail(main_id: str) -> dict[str, object]:
    ensure_nmpa_runtime_page()
    expression = f"""(async function(){{
      const [axiosText, md5Text, base64Text, utilText, apiText, ajaxText] = await Promise.all([
        fetch('js/axios.min.js').then((r) => r.text()),
        fetch('js/md5.js').then((r) => r.text()),
        fetch('js/base64.js').then((r) => r.text()),
        fetch('js/util.js').then((r) => r.text()),
        fetch('js/api.js').then((r) => r.text()),
        fetch('js/ajax.js').then((r) => r.text()),
      ]);
      eval(axiosText);
      eval(md5Text);
      eval(base64Text);
      eval(utilText);
      eval(apiText);
      eval(ajaxText);
      if (typeof pajax !== 'object' || typeof api !== 'object' || typeof api.queryDetail !== 'string') {{
        throw new Error('nmpa_runtime_not_ready:detail');
      }}
      const resp = await pajax.hasTokenGet(api.queryDetail, {{
        itemId: {json.dumps(SEARCH_ITEM_ID)},
        id: {json.dumps(main_id)}
      }});
      return JSON.stringify(resp.data || {{}});
    }})()"""
    try:
        raw = run_in_page_world(expression, storage_key=f"codex_detail_{safe_name(main_id)}")
    except RuntimeError:
        ensure_nmpa_runtime_page()
        raw = run_in_page_world(expression, storage_key=f"codex_detail_{safe_name(main_id)}_retry")
    return json.loads(raw) if raw else {}


def bridge_fetch_url(url: str, storage_key: str | None = None, poll_seconds: float = 10.0) -> dict[str, object]:
    expression = f"""(async function(){{
      const response = await fetch({json.dumps(url)}, {{ credentials: 'include' }});
      const contentType = response.headers.get('content-type') || 'application/octet-stream';
      if (!response.ok) {{
        return JSON.stringify({{ ok: false, status: response.status, content_type: contentType }});
      }}
      const buffer = await response.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = "";
      const chunkSize = 0x8000;
      for (let i = 0; i < bytes.length; i += chunkSize) {{
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
      }}
      return JSON.stringify({{
        ok: true,
        status: response.status,
        content_type: contentType,
        size: bytes.length,
        base64: btoa(binary)
      }});
    }})()"""
    raw = run_in_page_world(expression, storage_key=storage_key, poll_seconds=poll_seconds)
    return json.loads(raw) if raw else {}


def navigate_tab(url_part: str, url: str) -> None:
    script = f'location.href = "{js(url)}"; "ok";'
    execute_on_tab(url_part, script)


def detail_tab_key(detail_url: str) -> str:
    return detail_url if detail_url else "nmpa.gov.cn/datasearch/search-info.html"


def extract_main_item_id(detail_url: str) -> str:
    try:
        query = urllib.parse.urlparse(detail_url).query
        nmpa = urllib.parse.parse_qs(query).get("nmpa", [""])[0]
        decoded = base64.b64decode(nmpa).decode("utf-8", errors="ignore")
        match = re.search(r"(?:^|&)id=([^&]+)", decoded)
        return match.group(1) if match else ""
    except Exception:
        return ""


def build_child_list_url(detail_url: str, link_item_id: str = PACKAGE_LINK_ITEM_ID) -> str:
    main_item_id = extract_main_item_id(detail_url)
    if not main_item_id:
        return ""
    raw = f'linkItemId={link_item_id}&link_item_feild=f0&main_item_value={{"f0":"{main_item_id}"}}'
    encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
    return f"https://www.nmpa.gov.cn/datasearch/child-list.html?nmpa={encoded}"


def build_child_list_url_from_main_id(main_id: str, link_item_id: str = PACKAGE_LINK_ITEM_ID) -> str:
    main_item_id = str(main_id or "").strip()
    if not main_item_id:
        return ""
    raw = f'linkItemId={link_item_id}&link_item_feild=f0&main_item_value={{"f0":"{main_item_id}"}}'
    encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
    return f"https://www.nmpa.gov.cn/datasearch/child-list.html?nmpa={encoded}"


def inspect_child_list_assets(child_url: str, return_url: str, settle_seconds: float) -> dict[str, object]:
    restore_url = return_url or HOME_INDEX_URL
    navigate_tab(NMPA_TAB_KEY, child_url)
    time.sleep(settle_seconds)
    script = """
    (function(){
      const clean = (s) => String(s || "").replace(/\\s+/g, " ").trim();
      const absoluteUrl = (value) => {
        const text = clean(value);
        if (!text) return "";
        if (/^(https?:|data:|blob:)/i.test(text)) return text;
        if (text.startsWith("/")) return location.origin + text;
        try { return new URL(text, location.href).href; } catch (e) { return text; }
      };
      const isNoiseImage = (url) => /logo\\.png|sublogo|wuzhangailogo|red\\.png|jiucuo\\.png/i.test(url || "");
      const imageUrls = [];
      const previewLinks = [];
      const attachmentItems = [];
      const text = clean(document.body.innerText || "");
      const textMatches = text.match(/https?:[^\\s]+gsxxFilePreview\\?attachmentId=[^\\s]+/ig) || [];
      for (const url of textMatches) {
        if (!previewLinks.includes(url)) previewLinks.push(url);
      }
      const html = String(document.documentElement.outerHTML || "");
      const htmlMatches = html.match(/https?:[^"'<>\\s]+gsxxFilePreview\\?attachmentId=[^"'<>\\s]+/ig) || [];
      for (const url of htmlMatches) {
        if (!previewLinks.includes(url)) previewLinks.push(url);
      }
      for (const tr of document.querySelectorAll("tr")) {
        const cells = [...tr.querySelectorAll("td, th")].map((node) => clean(node.innerText || ""));
        const rowText = clean(tr.innerText || "");
        const category = cells.find((value) => /包装|立体|说明书|图片|附件/.test(value)) || "";
        const links = [];
        for (const el of tr.querySelectorAll("a[href], [onclick]")) {
          const href = absoluteUrl(el.getAttribute("href"));
          const onclick = clean(el.getAttribute("onclick"));
          const match = onclick.match(/https?:[^'")\\s]+|\\/[^'")\\s]+/ig) || [];
          if (href) links.push(href);
          for (const raw of match) links.push(absoluteUrl(raw));
        }
        for (const url of links) {
          if (!url || !/gsxxFilePreview/i.test(url)) continue;
          if (!previewLinks.includes(url)) previewLinks.push(url);
          attachmentItems.push({
            category: category || rowText.slice(0, 120),
            preview_link: url,
            row_text: rowText.slice(0, 300)
          });
        }
      }
      for (const el of document.querySelectorAll("img[src], a[href], [onclick], iframe[src], embed[src]")) {
        const candidates = [
          absoluteUrl(el.getAttribute("src")),
          absoluteUrl(el.getAttribute("href")),
        ];
        const onclick = clean(el.getAttribute("onclick"));
        const match = onclick.match(/https?:[^'")\\s]+|\\/[^'")\\s]+/ig) || [];
        for (const raw of match) candidates.push(absoluteUrl(raw));
        for (const url of candidates) {
          if (!url) continue;
          if (/gsxxFilePreview/i.test(url)) {
            if (!previewLinks.includes(url)) previewLinks.push(url);
          } else if ((!isNoiseImage(url)) && (/\\.(?:png|jpe?g|gif|webp|bmp)(?:\\?|$)/i.test(url) || /^data:image\\//i.test(url))) {
            if (!imageUrls.includes(url)) imageUrls.push(url);
          }
        }
      }
      return JSON.stringify({
        image_urls: imageUrls,
        preview_links: previewLinks,
        attachment_items: attachmentItems,
        no_package_info: /暂无关联信息/.test(text),
        text_excerpt: text.slice(0, 2000),
        html_excerpt: html.slice(0, 5000)
      });
    })()
    """
    try:
        raw = execute_on_tab(NMPA_TAB_KEY, script)
        return json.loads(raw) if raw else {}
    finally:
        navigate_tab(NMPA_TAB_KEY, restore_url)
        time.sleep(settle_seconds)


def read_detail_package_candidates(detail_url: str) -> dict[str, object]:
    script = """
    (function(){
      const clean = (s) => String(s || "").replace(/\\s+/g, " ").trim();
      const absoluteUrl = (value) => {
        const text = clean(value);
        if (!text) return "";
        if (text.startsWith("http://") || text.startsWith("https://")) return text;
        if (text.startsWith("/")) return location.origin + text;
        try { return new URL(text, location.href).href; } catch (e) { return text; }
      };
      const uniq = (items) => [...new Set(items.filter(Boolean))];
      const extractUrl = (value) => {
        const text = clean(value);
        if (!text) return "";
        const match = text.match(/https?:[^'")\\s]+|\\/[^'")\\s]+(?:search-info|child-list|gsxxFilePreview)[^'")\\s]*/i);
        return match ? absoluteUrl(match[0]) : "";
      };
      const isPackText = (text) => /包装|立体图|图片|附件|产品图/.test(text || "");
      const links = [];
      for (const el of [...document.querySelectorAll("a[href], button[onclick], [onclick], img[src]")]) {
        const text = clean(el.innerText || el.getAttribute("title") || el.getAttribute("alt") || "");
        const href = absoluteUrl(el.getAttribute("href"));
        const src = absoluteUrl(el.getAttribute("src"));
        const onclick = extractUrl(el.getAttribute("onclick"));
        const parentText = clean((el.closest("tr, li, div, section, td") || {}).innerText || "");
        const ctx = [text, parentText].filter(Boolean).join(" ");
        const candidates = [href, src, onclick].filter(Boolean);
        for (const url of candidates) {
          if (/child-list\\.html|gsxxFilePreview/i.test(url) || isPackText(ctx)) {
            links.push({ text, context: ctx, url });
          }
        }
      }
      const childLinks = uniq(links.map(item => /child-list\\.html/i.test(item.url) ? item.url : "").filter(Boolean));
      const previewLinks = uniq(links.map(item => /gsxxFilePreview/i.test(item.url) ? item.url : "").filter(Boolean));
      return JSON.stringify({
        url: location.href,
        title: document.title || "",
        child_links: childLinks,
        preview_links: previewLinks,
        matched_links: links.slice(0, 200)
      });
    })()
    """
    raw = execute_on_tab(detail_tab_key(detail_url), script)
    return json.loads(raw) if raw else {}


def read_child_preview_links(current_tab_key: str, child_url: str) -> list[str]:
    navigate_tab(current_tab_key, child_url)
    time.sleep(2)
    script = """
    (function(){
      const clean = (s) => String(s || "").replace(/\\s+/g, " ").trim();
      const absoluteUrl = (value) => {
        const text = clean(value);
        if (!text) return "";
        if (text.startsWith("http://") || text.startsWith("https://")) return text;
        if (text.startsWith("/")) return location.origin + text;
        try { return new URL(text, location.href).href; } catch (e) { return text; }
      };
      const items = [];
      for (const el of [...document.querySelectorAll("a[href], [onclick], img[src]")]) {
        const href = absoluteUrl(el.getAttribute("href"));
        const src = absoluteUrl(el.getAttribute("src"));
        const onclick = clean(el.getAttribute("onclick"));
        const match = onclick.match(/https?:[^'")\\s]+|\\/[^'")\\s]*gsxxFilePreview[^'")\\s]*/i);
        const onclickUrl = match ? absoluteUrl(match[0]) : "";
        for (const url of [href, src, onclickUrl]) {
          if (url && /gsxxFilePreview/i.test(url)) {
            items.push(url);
          }
        }
      }
      return JSON.stringify([...new Set(items)]);
    })()
    """
    raw = execute_on_tab(child_url, script)
    return json.loads(raw) if raw else []


def fetch_url_as_base64_via_browser(tab_key: str, url: str) -> tuple[str, bytes]:
    storage_key = f"codex_fetch_{int(time.time() * 1000)}"
    script = f"""
    (function(){{
      const storageKey = {json.dumps(storage_key)};
      const targetUrl = {json.dumps(url)};
      localStorage.removeItem(storageKey);
      (async function(){{
        try {{
          const response = await fetch(targetUrl, {{ credentials: "include" }});
          if (!response.ok) {{
            localStorage.setItem(storageKey, JSON.stringify({{
              ok: false,
              status: response.status,
              statusText: response.statusText || ""
            }}));
            return;
          }}
          const contentType = response.headers.get("content-type") || "application/octet-stream";
          const buffer = await response.arrayBuffer();
          const bytes = new Uint8Array(buffer);
          let binary = "";
          const chunkSize = 0x8000;
          for (let i = 0; i < bytes.length; i += chunkSize) {{
            binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
          }}
          localStorage.setItem(storageKey, JSON.stringify({{
            ok: true,
            content_type: contentType,
            base64: btoa(binary)
          }}));
        }} catch (error) {{
          localStorage.setItem(storageKey, JSON.stringify({{
            ok: false,
            error: String(error && error.message ? error.message : error)
          }}));
        }}
      }})();
      return storageKey;
    }})()
    """
    execute_on_tab(tab_key, script)
    payload: dict[str, object] = {}
    for _ in range(40):
        time.sleep(0.5)
        raw = execute_on_tab(tab_key, f'(function(){{ return localStorage.getItem({json.dumps(storage_key)}) || ""; }})()')
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        else:
            break
    execute_on_tab(tab_key, f'(function(){{ localStorage.removeItem({json.dumps(storage_key)}); return "ok"; }})()')
    if not payload.get("ok"):
        raise RuntimeError(f"浏览器内下载失败: {payload}")
    return str(payload.get("content_type", "application/octet-stream")), base64.b64decode(str(payload.get("base64", "")))


def file_extension_from_content_type(content_type: str) -> str:
    content_type = str(content_type or "").lower()
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "gif" in content_type:
        return ".gif"
    return ".jpg"


def save_package_image(month: str, brand: str, filing_no: str, index: int, content_type: str, content: bytes) -> str:
    target_dir = PACKAGE_DIR / month / safe_name(brand) / safe_name(filing_no)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"package_{index:02d}{file_extension_from_content_type(content_type)}"
    path.write_bytes(content)
    return str(path.relative_to(OUTPUT_DIR)).replace("\\", "/")


def is_likely_noise_package_image(content: bytes) -> bool:
    tmp_dir = OUTPUT_DIR / "_tmp_probe"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    probe_path = tmp_dir / f"probe_{int(time.time() * 1000)}.bin"
    probe_path.write_bytes(content)
    try:
        result = subprocess.run(
            ["file", str(probe_path)],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.lower()
        match = re.search(r"(\d+)\s*x\s*(\d+)", result)
        if match:
            width = int(match.group(1))
            height = int(match.group(2))
            if width <= 160 and height <= 160:
                return True
    finally:
        try:
            probe_path.unlink(missing_ok=True)
        except OSError:
            pass
    return False


def save_package_pdf(month: str, brand: str, filing_no: str, source_name: str, content: bytes) -> str:
    target_dir = PACKAGE_PDF_DIR / row_package_bucket(month, brand, filing_no)
    target_dir.mkdir(parents=True, exist_ok=True)
    ext = file_extension_from_name(source_name, fallback=".pdf")
    path = target_dir / f"package_document{ext}"
    path.write_bytes(content)
    return str(path.relative_to(OUTPUT_DIR)).replace("\\", "/")


def render_pdf_first_page(relative_pdf_path: str) -> str:
    rel = str(relative_pdf_path or "").strip()
    if not rel:
        return ""
    pdf_path = OUTPUT_DIR / rel
    if not pdf_path.exists():
        return ""
    render_dir = PACKAGE_RENDER_DIR / pdf_path.parent.relative_to(OUTPUT_DIR)
    render_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = render_dir / pdf_path.stem
    try:
        subprocess.run(
            ["pdftoppm", "-f", "1", "-singlefile", "-png", str(pdf_path), str(output_prefix)],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ""
    png_path = output_prefix.with_suffix(".png")
    if not png_path.exists():
        return ""
    return str(png_path.relative_to(OUTPUT_DIR)).replace("\\", "/")


def list_recent_download_candidates(since_ts: float, min_size: int = 1024) -> list[Path]:
    candidates: list[Path] = []
    if not DOWNLOADS_DIR.exists():
        return candidates
    for path in DOWNLOADS_DIR.iterdir():
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime < since_ts:
            continue
        if stat.st_size < min_size:
            continue
        candidates.append(path)
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates


def copy_recent_download_as_package_pdf(
    month: str,
    brand: str,
    filing_no: str,
    since_ts: float,
) -> tuple[str, str]:
    for candidate in list_recent_download_candidates(since_ts):
        try:
            if candidate.suffix.lower() != ".pdf":
                file_type = subprocess.run(
                    ["file", str(candidate)],
                    check=False,
                    capture_output=True,
                    text=True,
                ).stdout.lower()
                if "pdf document" not in file_type:
                    continue
            content = candidate.read_bytes()
        except OSError:
            continue
        saved_pdf = save_package_pdf(month, brand, filing_no, candidate.name or "package.pdf", content)
        preview_png = render_pdf_first_page(saved_pdf)
        return saved_pdf, preview_png
    return "", ""


def row_identity(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        str(row.get("product_name", "") or ""),
        str(row.get("filing_no", "") or ""),
        str(row.get("filing_date", "") or ""),
        str(row.get("filer", "") or ""),
    )


def wait_for_detail_page(settle_seconds: float, retries: int = 8) -> str:
    for _ in range(retries):
        time.sleep(settle_seconds)
        try:
            current_url = execute_on_tab("nmpa.gov.cn/datasearch/search-info.html", "location.href")
        except Exception:
            continue
        if "search-info.html" in current_url:
            return current_url.strip()
    return ""


def click_detail_button_for_row_index(page_row_index: int) -> str:
    js_index = max(int(page_row_index) - 1, 0)
    script = f"""
    (function(){{
      const rows = [...document.querySelectorAll("tbody tr")];
      const tr = rows[{js_index}] || null;
      if (!tr) return "no-row";
      const btn = tr.querySelector("td:last-child button");
      if (!btn) return "no-button";
      btn.click();
      return "clicked";
    }})()
    """
    return execute_on_tab("nmpa.gov.cn/datasearch/search-result.html", script)


def wait_for_result_page(expected_page: str, settle_seconds: float, retries: int = 8) -> dict[str, object]:
    last_state: dict[str, object] = {}
    for _ in range(retries):
        time.sleep(settle_seconds)
        try:
            state = read_page_state()
        except Exception:
            continue
        last_state = state
        if str(state.get("page", "")) == str(expected_page):
            return state
    return last_state


def go_to_page_number(target_page: str, settle_seconds: float) -> dict[str, object]:
    target = str(target_page or "").strip()
    state = read_page_state()
    if not target:
        return state
    for _ in range(40):
        current = str(state.get("page", "")).strip()
        if current == target:
            return state
        current_num = int(current or "1")
        target_num = int(target or "1")
        if current_num > target_num:
            break
        click_next_page()
        time.sleep(settle_seconds)
        state = read_page_state()
    return state


def inspect_current_detail_package_assets(detail_url: str) -> dict[str, object]:
    storage_key = f"codex_detail_{int(time.time() * 1000)}"
    script = """
    (function(){
      const storageKey = __STORAGE_KEY__;
      localStorage.removeItem(storageKey);
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const clean = (s) => String(s || "").replace(/\\s+/g, " ").trim();
      const visible = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      };
      const absoluteUrl = (value) => {
        const text = clean(value);
        if (!text) return "";
        if (/^(https?:|data:|blob:)/i.test(text)) return text;
        if (text.startsWith("/")) return location.origin + text;
        try { return new URL(text, location.href).href; } catch (e) { return text; }
      };
      const extractUrls = (value) => {
        const text = clean(value);
        if (!text) return [];
        return [...text.matchAll(/https?:[^'")\\s]+|\\/[^'")\\s]+/ig)].map((match) => absoluteUrl(match[0]));
      };
      const isNoiseImage = (url) => /logo\\.png|sublogo|wuzhangailogo|red\\.png|jiucuo\\.png/i.test(url || "");
      const uniqPush = (items, value) => {
        if (value && !items.includes(value)) items.push(value);
      };
      const mergeInto = (target, extra) => {
        for (const key of ["image_urls", "preview_links", "child_links"]) {
          for (const value of extra[key] || []) uniqPush(target[key], value);
        }
        if (extra.no_package_info) target.no_package_info = true;
        if (extra.package_panel_opened) target.package_panel_opened = true;
        if (extra.text_excerpt) target.text_excerpt = extra.text_excerpt;
      };
      const scan = () => {
        const result = {
          image_urls: [],
          preview_links: [],
          child_links: [],
          no_package_info: false,
          package_panel_opened: false,
          text_excerpt: ""
        };
        const scopeCandidates = [...document.querySelectorAll(".el-dialog, .el-dialog__wrapper, .el-drawer, .el-drawer__body, .el-card")]
          .filter(visible);
        const scopes = scopeCandidates.length ? scopeCandidates : [document.body];
        result.package_panel_opened = scopeCandidates.length > 0;
        const texts = [];
        for (const root of scopes) {
          const text = clean(root.innerText || "");
          if (text) texts.push(text);
          for (const img of root.querySelectorAll("img[src]")) {
            const src = absoluteUrl(img.getAttribute("src"));
            if (src && !isNoiseImage(src)) uniqPush(result.image_urls, src);
          }
          for (const el of root.querySelectorAll("a[href], iframe[src], embed[src], source[src], [onclick]")) {
            const urls = [];
            const href = absoluteUrl(el.getAttribute("href"));
            const src = absoluteUrl(el.getAttribute("src"));
            if (href) urls.push(href);
            if (src) urls.push(src);
            for (const value of extractUrls(el.getAttribute("onclick"))) urls.push(value);
            for (const url of urls) {
              if (!url) continue;
              if (/child-list\\.html/i.test(url)) {
                uniqPush(result.child_links, url);
              } else if (/gsxxFilePreview/i.test(url)) {
                uniqPush(result.preview_links, url);
              } else if (/\\.(?:png|jpe?g|gif|webp|bmp)(?:\\?|$)/i.test(url) || /^data:image\\//i.test(url)) {
                if (!isNoiseImage(url)) uniqPush(result.image_urls, url);
              }
            }
          }
        }
        result.no_package_info = texts.some((text) => /暂无关联信息/.test(text));
        result.text_excerpt = texts.join(" ").slice(0, 1500);
        return result;
      };

      (async function(){
        try {
          const packageEntry = [...document.querySelectorAll("a, button, span")]
            .find((el) => clean(el.innerText) === "产品包装");
          if (packageEntry) {
            (packageEntry.closest("a,button") || packageEntry).click();
            await sleep(1200);
          }
          const result = scan();
          if (!result.no_package_info && !result.image_urls.length) {
            const previewButtons = [...document.querySelectorAll(".el-dialog button, .el-dialog a, .el-dialog span, .el-drawer button, .el-drawer a, .el-drawer span, .el-table button, .el-table a, .el-table span")]
              .filter(visible)
              .filter((el) => /内容查看|查看|预览/.test(clean(el.innerText)));
            for (const node of previewButtons.slice(0, 8)) {
              try { node.click(); } catch (e) {}
              await sleep(900);
              mergeInto(result, scan());
            }
          }
          localStorage.setItem(storageKey, JSON.stringify(result));
        } catch (error) {
          localStorage.setItem(storageKey, JSON.stringify({
            image_urls: [],
            preview_links: [],
            child_links: [],
            no_package_info: false,
            package_panel_opened: false,
            text_excerpt: "",
            error: String(error && error.message ? error.message : error)
          }));
        }
      })();
      return storageKey;
    })()
    """
    script = script.replace("__STORAGE_KEY__", json.dumps(storage_key))
    tab_key = detail_tab_key(detail_url)
    execute_on_tab(tab_key, script)
    payload: dict[str, object] = {}
    for _ in range(30):
        time.sleep(0.5)
        raw = execute_on_tab(
            tab_key,
            f'(function(){{ return localStorage.getItem({json.dumps(storage_key)}) || ""; }})()',
        )
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        else:
            break
    execute_on_tab(
        tab_key,
        f'(function(){{ localStorage.removeItem({json.dumps(storage_key)}); return "ok"; }})()',
    )
    return payload


def inspect_preview_page_image_urls(preview_url: str, return_url: str, settle_seconds: float) -> list[str]:
    navigate_tab("nmpa.gov.cn/datasearch/", preview_url)
    time.sleep(settle_seconds)
    script = """
    (function(){
      const clean = (s) => String(s || "").replace(/\\s+/g, " ").trim();
      const absoluteUrl = (value) => {
        const text = clean(value);
        if (!text) return "";
        if (/^(https?:|data:|blob:)/i.test(text)) return text;
        if (text.startsWith("/")) return location.origin + text;
        try { return new URL(text, location.href).href; } catch (e) { return text; }
      };
      const isNoiseImage = (url) => /logo\\.png|sublogo|wuzhangailogo|red\\.png|jiucuo\\.png/i.test(url || "");
      const urls = [];
      for (const el of document.querySelectorAll("img[src], iframe[src], embed[src], source[src], a[href]")) {
        const src = absoluteUrl(el.getAttribute("src") || el.getAttribute("href"));
        if (!src || isNoiseImage(src)) continue;
        if (/\\.(?:png|jpe?g|gif|webp|bmp)(?:\\?|$)/i.test(src) || /^data:image\\//i.test(src)) {
          if (!urls.includes(src)) urls.push(src);
        }
      }
      return JSON.stringify(urls);
    })()
    """
    try:
        raw = execute_on_tab("nmpa.gov.cn/datasearch/", script)
        image_urls = json.loads(raw) if raw else []
    finally:
        navigate_tab("nmpa.gov.cn/datasearch/", return_url)
        time.sleep(settle_seconds)
    return image_urls


def fetch_child_html(child_url: str) -> str:
    navigate_tab(NMPA_TAB_KEY, child_url)
    time.sleep(1.0)
    script = """
    (function(){
      return document.documentElement ? String(document.documentElement.outerHTML || "") : "";
    })()
    """
    try:
        return execute_on_tab(NMPA_TAB_KEY, script)
    finally:
        navigate_tab(NMPA_TAB_KEY, HOME_INDEX_URL)
        time.sleep(0.8)


def extract_preview_links_from_html(html: str) -> list[str]:
    text = str(html or "")
    links = re.findall(r'https?:[^"\'>\s]+gsxxFilePreview\?attachmentId=[^"\'>\s]+', text, flags=re.I)
    deduped: list[str] = []
    for link in links:
        if link not in deduped:
            deduped.append(link)
    return deduped


def resolve_preview_to_image_urls(preview_url: str) -> list[str]:
    navigate_tab(NMPA_TAB_KEY, preview_url)
    time.sleep(1.2)
    script = """
    (function(){
      const clean = (s) => String(s || "").replace(/\\s+/g, " ").trim();
      const absoluteUrl = (value) => {
        const text = clean(value);
        if (!text) return "";
        if (/^(https?:|data:|blob:)/i.test(text)) return text;
        if (text.startsWith("/")) return location.origin + text;
        try { return new URL(text, location.href).href; } catch (e) { return text; }
      };
      const urls = [];
      const push = (value) => {
        const url = absoluteUrl(value);
        if (!url) return;
        if (
          /^data:image\\//i.test(url) ||
          /\\.(?:png|jpe?g|gif|webp|bmp)(?:\\?|$)/i.test(url) ||
          /(?:image|img|picture|photo|preview)/i.test(url)
        ) {
          if (!urls.includes(url)) urls.push(url);
        }
      };
      for (const el of document.querySelectorAll("img[src], a[href], iframe[src], embed[src], source[src]")) {
        push(el.getAttribute("src"));
        push(el.getAttribute("href"));
      }
      const html = String(document.documentElement.outerHTML || "");
      const htmlMatches = html.match(/https?:[^"'<>\\s]+(?:png|jpe?g|gif|webp|bmp)[^"'<>\\s]*/ig) || [];
      for (const value of htmlMatches) push(value);
      return JSON.stringify(urls);
    })()
    """
    try:
        raw = execute_on_tab(NMPA_TAB_KEY, script)
        return json.loads(raw) if raw else []
    finally:
        navigate_tab(NMPA_TAB_KEY, HOME_INDEX_URL)
        time.sleep(0.8)


def build_detail_url_from_child_id(child_id: str, item_id: str = PACKAGE_LINK_ITEM_ID) -> str:
    encoded = base64.b64encode(f"id={child_id}&itemId={item_id}".encode("utf-8")).decode("utf-8")
    return f"https://www.nmpa.gov.cn/datasearch/search-info.html?nmpa={encoded}"


def extract_child_detail_ids(child_url: str, return_url: str, settle_seconds: float) -> list[str]:
    restore_url = return_url or HOME_INDEX_URL
    navigate_tab(NMPA_TAB_KEY, child_url)
    time.sleep(settle_seconds)
    script = """
    (function(){
      const ids = [];
      const pushId = (value) => {
        const text = String(value || "").trim();
        if (text && !ids.includes(text)) ids.push(text);
      };
      const bodyText = String(document.body.innerText || "");
      const html = String(document.documentElement.outerHTML || "");
      for (const text of [html, bodyText]) {
        const matches = text.match(/search-info\\.html\\?nmpa=[A-Za-z0-9+/=_-]+/ig) || [];
        for (const match of matches) {
          try {
            const query = match.split("?")[1] || "";
            const nmpa = new URLSearchParams(query).get("nmpa") || "";
            const decoded = atob(nmpa);
            const idMatch = decoded.match(/(?:^|&)id=([^&]+)/i);
            if (idMatch && idMatch[1]) pushId(idMatch[1]);
          } catch (e) {}
        }
      }
      return JSON.stringify(ids);
    })()
    """
    try:
        raw = execute_on_tab(NMPA_TAB_KEY, script)
        return json.loads(raw) if raw else []
    finally:
        navigate_tab(NMPA_TAB_KEY, restore_url)
        time.sleep(settle_seconds)


def collect_package_links_from_detail_page(detail_url: str, settle_seconds: float = 1.0) -> dict[str, object]:
    navigate_tab(NMPA_TAB_KEY, detail_url)
    time.sleep(settle_seconds)
    script = r"""
    (function(){
      const clean = (s) => String(s || "").replace(/\s+/g, " ").trim();
      const absoluteUrl = (value) => {
        const text = clean(value);
        if (!text) return "";
        if (/^(https?:|data:|blob:)/i.test(text)) return text;
        if (text.startsWith("/")) return location.origin + text;
        try { return new URL(text, location.href).href; } catch (e) { return text; }
      };
      const clickDetail = () => {
        const detail = [...document.querySelectorAll("a.el-link, a, span, button")]
          .find((el) => clean(el.innerText) === "详情");
        if (!detail) return false;
        try { detail.click(); return true; } catch (e) { return false; }
      };
      const read = () => {
        const links = [...document.querySelectorAll("a[href]")]
          .map((el) => ({
            text: clean(el.innerText),
            href: absoluteUrl(el.getAttribute("href")),
            target: clean(el.getAttribute("target"))
          }))
          .filter((item) => item.href);
        return {
          links,
          has_content_dialog: /内容查看/.test(clean(document.body.innerText || "")),
          body_text: clean(document.body.innerText || "").slice(0, 2000)
        };
      };
      return JSON.stringify({ clicked: clickDetail(), initial: read() });
    })()
    """
    initial_raw = execute_on_tab(NMPA_TAB_KEY, script)
    initial = json.loads(initial_raw) if initial_raw else {}
    time.sleep(max(settle_seconds, 1.2))
    follow_script = r"""
    (function(){
      const clean = (s) => String(s || "").replace(/\s+/g, " ").trim();
      const absoluteUrl = (value) => {
        const text = clean(value);
        if (!text) return "";
        if (/^(https?:|data:|blob:)/i.test(text)) return text;
        if (text.startsWith("/")) return location.origin + text;
        try { return new URL(text, location.href).href; } catch (e) { return text; }
      };
      const links = [...document.querySelectorAll("a[href]")]
        .map((el) => ({
          text: clean(el.innerText),
          href: absoluteUrl(el.getAttribute("href")),
          target: clean(el.getAttribute("target"))
        }))
        .filter((item) => item.href);
      return JSON.stringify({
        links,
        body_text: clean(document.body.innerText || "").slice(0, 2000),
        title: document.title || ""
      });
    })()
    """
    follow_raw = execute_on_tab(NMPA_TAB_KEY, follow_script)
    follow = json.loads(follow_raw) if follow_raw else {}
    return {"initial": initial, "follow": follow}


def trigger_browser_download_from_detail_page(detail_url: str, settle_seconds: float = 1.0) -> bool:
    navigate_tab(NMPA_TAB_KEY, detail_url)
    time.sleep(settle_seconds)
    script = r"""
    (function(){
      const clean = (s) => String(s || "").replace(/\s+/g, " ").trim();
      const link = [...document.querySelectorAll("a[href]")]
        .find((el) => clean(el.innerText) === "点击链接");
      if (!link) return "no-click-link";
      try { link.click(); return "clicked"; } catch (e) { return "click-error:" + String(e && e.message ? e.message : e); }
    })()
    """
    return execute_on_tab(NMPA_TAB_KEY, script) == "clicked"


def enrich_row_detail_and_package(row: dict[str, str], month: str, brand: str) -> dict[str, str]:
    item = dict(row)
    main_id = str(item.get("_main_id", "") or "").strip()
    detail_url = str(item.get("detail_url", "") or "").strip()
    item.setdefault("package_files", [])
    item.setdefault("package_preview_links", [])
    item.setdefault("package_detail_pages", [])
    item.setdefault("package_attachment_items", [])
    if not detail_url and main_id:
        encoded = base64.b64encode(f"id={main_id}&itemId={SEARCH_ITEM_ID}".encode("utf-8")).decode("utf-8")
        detail_url = f"https://www.nmpa.gov.cn/datasearch/search-info.html?nmpa={encoded}"
        item["detail_url"] = detail_url
    if not detail_url and not main_id:
        item["package_info_status"] = "no_detail_url"
        item["package_images"] = []
        return item

    try:
        if main_id:
            detail_payload = nmpa_query_detail(main_id)
            detail_data_payload = detail_payload.get("data", {}) if isinstance(detail_payload, dict) else {}
            detail_fields = detail_data_payload.get("detail", {}) if isinstance(detail_data_payload, dict) else {}
            if isinstance(detail_fields, dict):
                item["detail_url"] = detail_url
                item["product_name"] = str(detail_fields.get("f1", item.get("product_name", "")) or item.get("product_name", ""))
                item["filing_no"] = str(detail_fields.get("f2", item.get("filing_no", "")) or item.get("filing_no", ""))
                item["filing_date"] = str(detail_fields.get("f3", item.get("filing_date", "")) or item.get("filing_date", ""))
                item["filer"] = str(detail_fields.get("f4", item.get("filer", "")) or item.get("filer", ""))
                main_id = str(detail_fields.get("f0", main_id) or main_id)
                item["_main_id"] = main_id

        child_url = build_child_list_url(detail_url)
        if not child_url and main_id:
            child_url = build_child_list_url_from_main_id(main_id)
        attachment_items: list[dict[str, str]] = []
        preview_links: list[str] = []
        image_urls: list[str] = []
        detail_data = {}
        if child_url:
            try:
                child_data = inspect_child_list_assets(child_url, detail_url, 1.0)
            except Exception:
                child_data = {}
            attachment_items = list(child_data.get("attachment_items", []) or [])
            item["package_attachment_items"] = attachment_items
            preview_links = list(child_data.get("preview_links", []) or [])
            image_urls = list(child_data.get("image_urls", []) or [])
            if not preview_links:
                try:
                    child_html = fetch_child_html(child_url)
                except Exception:
                    child_html = ""
                preview_links = list(dict.fromkeys(preview_links + extract_preview_links_from_html(child_html)))
        else:
            child_data = {}

        preferred_preview_links: list[str] = []
        fallback_preview_links: list[str] = []
        for attachment in attachment_items:
            if not isinstance(attachment, dict):
                continue
            category = str(attachment.get("category", "") or "") + " " + str(attachment.get("row_text", "") or "")
            link = str(attachment.get("preview_link", "") or "").strip()
            if not link:
                continue
            if "说明书" in category:
                fallback_preview_links.append(link)
            elif ("立体" in category) or ("包装" in category):
                preferred_preview_links.append(link)
            else:
                fallback_preview_links.append(link)

        preview_links = list(
            dict.fromkeys(
                link
                for link in (preferred_preview_links + preview_links + fallback_preview_links)
                if link
            )
        )
        item["package_preview_links"] = preview_links
        image_urls = list(dict.fromkeys(url for url in image_urls if url))
        package_images: list[str] = []
        package_files: list[str] = []
        resolved_image_urls: list[str] = []
        for preview_url in preview_links:
            try:
                resolved_image_urls.extend(resolve_preview_to_image_urls(preview_url))
            except Exception:
                continue
        candidate_downloads = list(dict.fromkeys(image_urls + resolved_image_urls + preview_links))
        for idx, image_url in enumerate(candidate_downloads, start=1):
            try:
                payload = bridge_fetch_url(image_url, storage_key=f"codex_fetch_{safe_name(item.get('filing_no',''))}_{idx}", poll_seconds=12.0)
                if not payload.get("ok"):
                    continue
                content_type = str(payload.get("content_type", "application/octet-stream"))
                content = base64.b64decode(str(payload.get("base64", "")))
                if is_likely_noise_package_image(content):
                    continue
                package_images.append(save_package_image(month, brand, str(item.get("filing_no", "")), idx, content_type, content))
            except Exception:
                continue
        package_detail_pages: list[str] = []
        item["package_detail_pages"] = package_detail_pages
        item["package_images"] = package_images
        item["package_files"] = package_files
        if package_images:
            item["package_info_status"] = "fetched"
        elif package_files:
            item["package_info_status"] = "pdf_downloaded"
        elif child_data.get("no_package_info") or detail_data.get("no_package_info"):
            item["package_info_status"] = "no_package_info"
        elif attachment_items or preview_links or package_detail_pages:
            item["package_info_status"] = "package_preview_link_detected"
        elif detail_data.get("package_panel_opened"):
            text_excerpt = str(detail_data.get("text_excerpt", "") or "")
            item["package_info_status"] = "no_package_info" if "暂无关联信息" in text_excerpt else "package_panel_opened_no_image"
        else:
            item["package_info_status"] = "no_package_image_found"
    except Exception as exc:
        item["package_images"] = []
        item["package_info_status"] = f"package_fetch_error:{exc}"
    return item


def previous_month(today: date | None = None) -> str:
    today = today or date.today()
    first_of_this_month = today.replace(day=1)
    previous_month_last_day = first_of_this_month - timedelta(days=1)
    return previous_month_last_day.strftime("%Y-%m")


def load_brands(path: str | None) -> list[str]:
    if not path:
        return DEFAULT_BRANDS
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("品牌文件必须是字符串数组 JSON。")
    return data


def run_osascript(lines: list[str]) -> str:
    cmd = ["osascript"]
    for line in lines:
        cmd.extend(["-e", line])
    last_error = ""
    for attempt in range(3):
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        last_error = result.stderr.strip() or result.stdout.strip() or "osascript 执行失败"
        if "-609" in last_error or "连接无效" in last_error:
            time.sleep(1.0 + attempt * 0.5)
            continue
        break
    raise RuntimeError(last_error)


def js(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", " ")
        .replace("\n", " ")
    )


def chrome_target_lines(url_part: str) -> list[str]:
    probe_script = js(
        '(function(){'
        'var text=(document.body&&document.body.innerText)?String(document.body.innerText).trim():"";'
        'var title=document.title||"";'
        'var scripts=document.scripts?document.scripts.length:0;'
        'var name=window.name||"";'
        'return [scripts,text.length,title.length,name].join("|");'
        '})()'
    )
    lines = [
        'tell application "Google Chrome"',
        "set targetTab to missing value",
        "set workerTab to missing value",
        "set bestScore to -1",
        "repeat with w in windows",
        "repeat with t in tabs of w",
        "set u to URL of t",
        f'if u contains "{NMPA_URL_FILTER}" then',
        "set scriptsCount to 0",
        "set textLen to 0",
        "set titleLen to 0",
        'set tabName to ""',
        "try",
        f'set probe to execute t javascript "{probe_script}"',
        "set oldTIDs to AppleScript's text item delimiters",
        'set AppleScript\'s text item delimiters to "|"',
        "set probeItems to text items of probe",
        "set AppleScript's text item delimiters to oldTIDs",
        "if (count of probeItems) is greater than or equal to 4 then",
        "set scriptsCount to (item 1 of probeItems) as integer",
        "set textLen to (item 2 of probeItems) as integer",
        "set titleLen to (item 3 of probeItems) as integer",
        "set tabName to item 4 of probeItems",
        "end if",
        "on error",
        "set AppleScript's text item delimiters to oldTIDs",
        "end try",
        f'if tabName is "{NMPA_WORKER_NAME}" then set workerTab to t',
        f'if u contains "{url_part}" then',
        "set score to (scriptsCount * 1000000) + textLen + (titleLen * 10)",
        "if score > bestScore then",
        "set bestScore to score",
        "set targetTab to t",
        "end if",
        "end if",
        "end if",
        "end repeat",
        "end repeat",
    ]
    if url_part in {NMPA_TAB_KEY, NMPA_URL_FILTER}:
        lines.append("if workerTab is not missing value then set targetTab to workerTab")
    lines.append('if targetTab is missing value then error "NMPA tab not found"')
    return lines


def ensure_chrome_nmpa_tab() -> None:
    try:
        run_osascript([
            'tell application "Google Chrome"',
            "if not running then launch",
            "if (count of windows) = 0 then make new window",
            "set targetTab to missing value",
            "repeat with w in windows",
            "repeat with t in tabs of w",
            "set u to URL of t",
            f'if u contains "{NMPA_URL_FILTER}" then',
            "set targetTab to t",
            "exit repeat",
            "end if",
            "end repeat",
            "if targetTab is not missing value then exit repeat",
            "end repeat",
            "if targetTab is missing value then",
            'tell front window',
            f'set targetTab to make new tab with properties {{URL:"{js(HOME_INDEX_URL)}"}}',
            "end tell",
            "end if",
            f'try\nset URL of targetTab to URL of targetTab\nend try',
            "end tell",
        ])
    except RuntimeError:
        run_osascript([
            'tell application "Google Chrome"',
            "if not running then launch",
            "make new window",
            'tell front window',
            f'set targetTab to make new tab with properties {{URL:"{js(HOME_INDEX_URL)}"}}',
            "end tell",
            "end tell",
        ])


def execute_on_tab(url_part: str, script: str) -> str:
    lines = chrome_target_lines(url_part)
    lines.append(f'execute targetTab javascript "{js(script)}"')
    lines.append("end tell")
    return run_osascript(lines)


def navigate_brand_result(brand: str) -> None:
    script = (
        "(function(){"
        f'localStorage.setItem("searchkey", "{brand}");'
        f'localStorage.setItem("itemIdArray", JSON.stringify(["{SEARCH_ITEM_ID}"]));'
        f'localStorage.setItem("selectValue", JSON.stringify([["item_4","{SEARCH_ITEM_ID}"]]));'
        'localStorage.setItem("bannerIndex", "2");'
        'localStorage.setItem("isSenior", "N");'
        f'location.href = "{SEARCH_RESULT_URL}";'
        'return "ok";'
        "})()"
    )
    execute_on_tab("nmpa.gov.cn/datasearch/", script)


def read_page_state() -> dict[str, object]:
    script = """
    (function(){
      const clean = (s) => String(s || "").replace(/\\s+/g, " ").trim();
      const absoluteUrl = (value) => {
        const text = clean(value);
        if (!text) return "";
        if (text.startsWith("http://") || text.startsWith("https://")) return text;
        if (text.startsWith("/")) return location.origin + text;
        try { return new URL(text, location.href).href; } catch (e) { return text; }
      };
      const fullText = (td) => {
        const ref = td.querySelector(".el-popover__reference[aria-describedby], .name-wrapper[aria-describedby]");
        if (ref) {
          const popId = ref.getAttribute("aria-describedby");
          const pop = popId ? document.getElementById(popId) : null;
          const popText = clean(pop ? pop.innerText : "");
          if (popText) return popText;
        }
        return clean(td.innerText);
      };
      const rows = [...document.querySelectorAll("tbody tr")].map((tr) => {
        const tds = [...tr.querySelectorAll("td")].map((td) => fullText(td));
        const detailAnchor = tr.querySelector("td:last-child a[href], a[href*='detail'], a[href*='info']");
        const onclick = detailAnchor ? clean(detailAnchor.getAttribute("onclick")) : "";
        let detailUrl = detailAnchor ? absoluteUrl(detailAnchor.getAttribute("href")) : "";
        if (!detailUrl && onclick) {
          const match = onclick.match(/['"]([^'"]*(?:detail|info|product)[^'"]*)['"]/i);
          if (match && match[1]) detailUrl = absoluteUrl(match[1]);
        }
        return {
          seq: tds[0] || "",
          product_name: tds[1] || "",
          filing_no: tds[2] || "",
          filing_date: tds[3] || "",
          filer: tds[4] || "",
          detail: tds[5] || "",
          detail_url: detailUrl
        };
      }).filter((row) => row.product_name);
      const current = document.querySelector(".el-pager li.active");
      const next = document.querySelector(".btn-next");
      const totalText = clean((document.querySelector(".el-pagination") || document.body).innerText);
      return JSON.stringify({
        url: location.href,
        page: current ? clean(current.innerText) : "",
        rows: rows,
        has_next: !!(next && !next.disabled && !(next.className || "").includes("is-disabled")),
        total_text: totalText
      });
    })()
    """
    last_error: Exception | None = None
    for _ in range(4):
        raw = execute_on_tab("nmpa.gov.cn/datasearch/search-result.html", script)
        if raw and raw.strip():
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                last_error = exc
        time.sleep(1)
    if last_error:
        raise last_error
    raise RuntimeError("结果页读取为空，无法解析页面状态")


def click_next_page() -> str:
    script = """
    (function(){
      const next = document.querySelector(".btn-next");
      if (next && !next.disabled && !(next.className || "").includes("is-disabled")) {
        next.click();
        return "clicked";
      }
      return "no-next";
    })()
    """
    return execute_on_tab("nmpa.gov.cn/datasearch/search-result.html", script)


def wait_for_brand_rows(brand: str, settle_seconds: float, retries: int = 8) -> dict[str, object]:
    last_state: dict[str, object] = {}
    for _ in range(retries):
        time.sleep(settle_seconds)
        state = read_page_state()
        last_state = state
        rows = state.get("rows", [])
        if rows:
            first_name = str(rows[0].get("product_name", "")) if isinstance(rows[0], dict) else ""
            page = str(state.get("page", ""))
            if page == "1" and brand in first_name:
                return state
        total_text = str(state.get("total_text", ""))
        if "共 0 条" in total_text:
            return state
    return last_state


def collect_brand_rows(brand: str, settle_seconds: float, month: str | None = None) -> list[dict[str, str]]:
    all_rows: list[dict[str, str]] = []
    seen_pages: set[int] = set()
    page_num = 1
    page_size = 20
    while page_num not in seen_pages and page_num <= 60:
        seen_pages.add(page_num)
        payload = nmpa_query_list(brand, page_num, page_size=page_size)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            break
        page_rows_raw = data.get("list", []) or []
        total = int(data.get("total", 0) or 0)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page_rows: list[dict[str, str]] = []
        for index, raw_row in enumerate(page_rows_raw, start=1):
            if not isinstance(raw_row, dict):
                continue
            page_row = {
                "seq": str((page_num - 1) * page_size + index),
                "product_name": str(raw_row.get("f0", "") or ""),
                "filing_no": str(raw_row.get("f1", "") or ""),
                "filing_date": str(raw_row.get("f2", "") or ""),
                "filer": str(raw_row.get("f3", "") or ""),
                "detail": "详情",
                "detail_url": "",
                "_page": str(page_num),
                "_page_row_index": str(index),
                "_main_id": str(raw_row.get("f4", "") or ""),
            }
            if page_row["product_name"]:
                page_rows.append(page_row)
        if month:
            all_rows.extend([row for row in page_rows if filing_month(row.get("filing_date", "")) == month])
        else:
            all_rows.extend(page_rows)
        if page_num >= total_pages or not page_rows:
            break
        page_num += 1
    dedup: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in all_rows:
        key = (
            row.get("product_name", ""),
            row.get("filing_no", ""),
            row.get("filing_date", ""),
            row.get("filer", ""),
        )
        dedup[key] = row
    return list(dedup.values())


def enrich_rows_via_api(brand: str, rows: list[dict[str, str]], month: str) -> list[dict[str, str]]:
    enriched: list[dict[str, str]] = []
    ordered_rows = [dict(row) for row in rows]
    ordered_rows.sort(key=lambda row: (str(row.get("filing_date", "")), str(row.get("product_name", ""))), reverse=True)
    for row in ordered_rows:
        row.setdefault("package_images", [])
        row.setdefault("package_info_status", "")
        enriched.append(enrich_row_detail_and_package(row, month, brand))
    enriched.sort(key=lambda row: (str(row.get("filing_date", "")), str(row.get("product_name", ""))), reverse=True)
    return enriched


def filing_month(value: str) -> str:
    text = str(value or "").strip()
    return text[:7] if len(text) >= 7 else ""


def filter_month(rows: list[dict[str, str]], month: str) -> list[dict[str, str]]:
    dedup: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in rows:
        if filing_month(row.get("filing_date", "")) != month:
            continue
        key = (
            row.get("product_name", ""),
            row.get("filing_no", ""),
            row.get("filing_date", ""),
            row.get("filer", ""),
        )
        dedup[key] = dict(row)
    filtered = list(dedup.values())
    filtered.sort(key=lambda row: (row.get("filing_date", ""), row.get("product_name", "")), reverse=True)
    return filtered


def build_brand_item(brand: str, month: str, rows: list[dict[str, str]]) -> dict[str, object]:
    month_rows = filter_month(rows, month)
    latest = month_rows[0] if month_rows else {}
    note = f"{month}未检索到备案记录"
    if month_rows:
        note = f"{month}存在备案记录"
    return {
        "brand": brand,
        "month": month,
        "latest_filing_date": latest.get("filing_date", ""),
        "product_name": latest.get("product_name", ""),
        "filing_no": latest.get("filing_no", ""),
        "filer": latest.get("filer", ""),
        "month_count": len(month_rows),
        "note": note,
        "month_rows": month_rows,
        "spu_groups": group_rows_to_spu(month_rows),
        # 仅保留当月命中，避免再次携带整段历史深页结果。
        "all_rows": month_rows,
    }


def load_month_results(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_month_results(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def enrich_existing_month_file(month: str, settle_seconds: float, brands: list[str] | None = None) -> Path:
    path = MONTHLY_DIR / f"{month}_brand_latest.json"
    data = load_month_results(path)
    target_brands = set(brands or [])
    for item in data.get("results", []):
        brand = str(item.get("brand", "")).strip()
        if target_brands and brand not in target_brands:
            continue
        rows = enrich_rows_via_api(brand, list(item.get("month_rows", []) or []), month)
        item["month_rows"] = rows
        item["all_rows"] = rows
        item["spu_groups"] = group_rows_to_spu(rows)
    data["detail_count"] = sum(len(item.get("month_rows", [])) for item in data.get("results", []))
    save_month_results(path, data)
    return path


def write_outputs(month: str, brand_rows: dict[str, list[dict[str, str]]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MONTHLY_DIR.mkdir(parents=True, exist_ok=True)
    json_path = MONTHLY_DIR / f"{month}_brand_latest.json"
    csv_path = MONTHLY_DIR / f"{month}_brand_latest.csv"
    md_path = MONTHLY_DIR / f"{month}_brand_latest.md"

    summary = [build_brand_item(brand, month, rows) for brand, rows in brand_rows.items()]
    json_path.write_text(
        json.dumps(
            {
                "month": month,
                "source": "current_chrome_page_month_hits",
                "capture_scope": "month_hits_only",
                "summary_count": len(summary),
                "detail_count": sum(int(item["month_count"]) for item in summary),
                "results": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["brand", "month", "latest_filing_date", "product_name", "filing_no", "filer", "month_count", "note"],
        )
        writer.writeheader()
        for item in summary:
            writer.writerow({key: item[key] for key in writer.fieldnames})

    lines = [
        f"# {month} 国产牙膏备案品牌追踪",
        "",
        "数据来源：当前 Chrome 页面真实搜索结果与翻页抓取。",
        "当前版本仅保留目标月份命中的记录，不再携带品牌历史深页结果。",
        "",
        "| 品牌 | 最新备案日期 | 产品名称 | 备案编号 | 备案人 | 当月命中数 | 说明 |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for item in summary:
        lines.append(
            f"| {item['brand']} | {item['latest_filing_date']} | {item['product_name']} | {item['filing_no']} | {item['filer']} | {item['month_count']} | {item['note']} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_brand_json(month: str, brand: str, rows: list[dict[str, str]]) -> Path:
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    item = build_brand_item(brand, month, rows)
    path = PROGRESS_DIR / f"{month}_brand_progress.jsonl"
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(item, ensure_ascii=False) + "\n")
    return path


def build_outputs_from_progress(month: str, brands: list[str]) -> Path:
    progress_path = PROGRESS_DIR / f"{month}_brand_progress.jsonl"
    brand_map: dict[str, dict[str, object]] = {}
    if progress_path.exists():
        for line in progress_path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError:
                continue
            brand = str(item.get("brand", "") or "").strip()
            if brand:
                brand_map[brand] = item

    brand_rows: dict[str, list[dict[str, str]]] = {}
    for brand in brands:
        if brand in brand_map:
            brand_rows[brand] = list(brand_map[brand].get("month_rows", []) or [])
        else:
            brand_rows[brand] = []
    write_outputs(month, brand_rows)
    return MONTHLY_DIR / f"{month}_brand_latest.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="复用当前 Chrome 会话并按页面翻页抓取 NMPA 牙膏备案，仅保留目标月份命中。")
    parser.add_argument("--brands", help="品牌 JSON 文件路径，默认使用内置品牌列表。")
    parser.add_argument("--month", help="指定月份，格式 YYYY-MM，默认使用上个月。")
    parser.add_argument("--settle-seconds", type=float, default=3.0, help="翻页或跳转后的等待秒数。")
    parser.add_argument("--single-brand", help="只抓取一个品牌，并把该品牌结果追加保存到 progress 文件。")
    parser.add_argument("--enrich-existing-month", action="store_true", help="基于现有月度 JSON 补抓详情链接与产品立体图。")
    parser.add_argument("--only-brands", nargs="*", help="配合 --enrich-existing-month 使用，只补指定品牌。")
    parser.add_argument("--build-from-progress", action="store_true", help="根据 progress 文件重建月度 JSON/CSV/MD。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    month = args.month or previous_month()
    if args.enrich_existing_month:
        path = enrich_existing_month_file(month, args.settle_seconds, args.only_brands)
        print(str(path))
        return 0
    brands = load_brands(args.brands)
    if args.build_from_progress:
        path = build_outputs_from_progress(month, brands)
        print(str(path))
        return 0
    if args.single_brand:
        rows = enrich_rows_via_api(
            args.single_brand,
            collect_brand_rows(args.single_brand, args.settle_seconds, month),
            month,
        )
        path = append_brand_json(month, args.single_brand, rows)
        print(str(path))
        return 0
    brand_rows = {
        brand: enrich_rows_via_api(
            brand,
            collect_brand_rows(brand, args.settle_seconds, month),
            month,
        )
        for brand in brands
    }
    write_outputs(month, brand_rows)
    print(str(MONTHLY_DIR / f"{month}_brand_latest.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
