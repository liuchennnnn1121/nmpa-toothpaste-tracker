from __future__ import annotations

import json
import subprocess
import time


SEARCH_ITEM_ID = "ff8080818e63c900018e787bc48d0598"
SEARCH_RESULT_URL = "https://www.nmpa.gov.cn/datasearch/search-result.html"


def run_osascript(lines: list[str]) -> str:
    cmd = ["osascript"]
    for line in lines:
        cmd.extend(["-e", line])
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "osascript failed")
    return result.stdout.strip()


def js(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", " ")
        .replace("\n", " ")
    )


def chrome_lines(url_part: str) -> list[str]:
    return [
        'tell application "Google Chrome"',
        "set targetTab to missing value",
        "repeat with w in windows",
        "repeat with t in tabs of w",
        "set u to URL of t",
        f'if u contains "{url_part}" then',
        "set targetTab to t",
        "exit repeat",
        "end if",
        "end repeat",
        "if targetTab is not missing value then exit repeat",
        "end repeat",
        'if targetTab is missing value then error "target tab not found"',
    ]


def execute_on_tab(url_part: str, script: str) -> str:
    return run_osascript(chrome_lines(url_part) + [f'execute targetTab javascript "{js(script)}"', "end tell"])


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


def current_rows() -> dict:
    script = """
    (function(){
      const clean = (s) => String(s || "").replace(/\\s+/g, " ").trim();
      const rows = [...document.querySelectorAll("tbody tr")].map((tr, i) => {
        const tds = [...tr.querySelectorAll("td")].map((td) => clean(td.innerText));
        return {i: i + 1, seq: tds[0] || "", product: tds[1] || "", filing: tds[2] || "", date: tds[3] || ""};
      });
      const current = document.querySelector(".el-pager li.active");
      return JSON.stringify({page: current ? clean(current.innerText) : "", rows});
    })()
    """
    return json.loads(execute_on_tab("nmpa.gov.cn/datasearch/search-result.html", script))


def click_next() -> str:
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


def probe_detail_state() -> dict:
    script = """
    (async function(){
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const clean = (s) => String(s || "").replace(/\\s+/g, " ").trim();
      const target = [...document.querySelectorAll("a,button,span")]
        .find((el) => clean(el.innerText) === "产品包装");
      if (target) (target.closest("a,button") || target).click();
      await sleep(1200);
      const imgs = [...document.querySelectorAll("img[src]")].map((img) => img.getAttribute("src") || "");
      const text = clean(document.body.innerText).slice(0, 3000);
      const dialogs = [...document.querySelectorAll(".el-dialog, .el-drawer, .el-table")].map((el) => ({
        cls: el.className || "",
        text: clean(el.innerText).slice(0, 500),
        html: (el.outerHTML || "").slice(0, 800)
      }));
      localStorage.setItem("codex_usmile_probe", JSON.stringify({url: location.href, text, imgs, dialogs}));
      return "ok";
    })()
    """
    execute_on_tab("nmpa.gov.cn/datasearch/search-info.html", script)
    time.sleep(1)
    raw = execute_on_tab("nmpa.gov.cn/datasearch/search-info.html", 'localStorage.getItem("codex_usmile_probe")')
    return json.loads(raw) if raw else {}


def click_detail_button(row_index: int) -> None:
    script = f"""
    (function(){{
      const rows = [...document.querySelectorAll("tbody tr")];
      const tr = rows[{max(row_index - 1, 0)}];
      if (!tr) return "no-row";
      const btn = tr.querySelector("td:last-child button");
      if (!btn) return "no-button";
      btn.click();
      return "clicked";
    }})()
    """
    print(execute_on_tab("nmpa.gov.cn/datasearch/search-result.html", script))


def main() -> int:
    navigate_brand_result("笑容加")
    time.sleep(3)
    for _ in range(25):
      payload = current_rows()
      hits = [row for row in payload["rows"] if "色修美白牙膏" in row["product"]]
      print({"page": payload["page"], "hits": hits})
      if hits:
          click_detail_button(int(hits[0]["i"]))
          time.sleep(2)
          print(json.dumps(probe_detail_state(), ensure_ascii=False, indent=2))
          return 0
      if click_next() != "clicked":
          break
      time.sleep(2.5)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
