import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT_DIR = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT_DIR = path.join(ROOT_DIR, "output");
const HOME_INDEX_URL = "https://www.nmpa.gov.cn/datasearch/home-index.html#category=hzp";
const PACKAGE_LINK_ITEM_ID = "ff8080818e63c900018e7884a67f0623";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function safeName(value) {
  return String(value == null ? "" : value)
    .trim()
    .replace(/[^\p{L}\p{N}_\-.]+/gu, "_")
    .replace(/^[_\-.]+|[_\-.]+$/gu, "") || "item";
}

function appleEscape(value) {
  return String(value == null ? "" : value)
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"');
}

function jsEscape(value) {
  return String(value == null ? "" : value)
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\r/g, " ")
    .replace(/\n/g, " ");
}

function rowPackageDir(month, brand, filingNo) {
  return path.join(OUTPUT_DIR, "package_images", month, safeName(brand), safeName(filingNo));
}

function relOutputPath(absPath) {
  return path.relative(OUTPUT_DIR, absPath).replace(/\\/g, "/");
}

function homeDownloadsDir() {
  return path.join(os.homedir(), "Downloads");
}

function pngSize(buffer) {
  const signature = "IHDR";
  const markerIndex = buffer.indexOf(signature, 0, "ascii");
  if (markerIndex < 0 || markerIndex + 12 >= buffer.length) {
    return { width: 0, height: 0 };
  }
  return {
    width: buffer.readUInt32BE(markerIndex + 4),
    height: buffer.readUInt32BE(markerIndex + 8),
  };
}

function buildChildListUrl(mainId) {
  const raw = `linkItemId=${PACKAGE_LINK_ITEM_ID}&link_item_feild=f0&main_item_value={"f0":"${String(mainId).trim()}"}`;
  return `https://www.nmpa.gov.cn/datasearch/child-list.html?nmpa=${Buffer.from(raw, "utf8").toString("base64")}`;
}

function osa(lines) {
  return execFileSync(
    "osascript",
    lines.flatMap((line) => ["-e", line]),
    { encoding: "utf8" },
  ).trim();
}

function runText(command, args, options = {}) {
  return execFileSync(command, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  });
}

function targetTabLines(tabId) {
  const idText = String(tabId);
  return [
    'tell application "Google Chrome"',
    "set targetTab to missing value",
    "repeat with w in windows",
    "repeat with t in tabs of w",
    `if ((id of t) as string) is "${appleEscape(idText)}" then`,
    "set targetTab to t",
    "exit repeat",
    "end if",
    "end repeat",
    "if targetTab is not missing value then exit repeat",
    "end repeat",
    'if targetTab is missing value then error "target tab not found"',
  ];
}

function createNativeTab(url = HOME_INDEX_URL) {
  const out = osa([
    'tell application "Google Chrome"',
    "activate",
    "if (count of windows) = 0 then make new window",
    'tell front window',
    `set newTab to make new tab with properties {URL:"${appleEscape(url)}"}`,
    "set active tab index to (count of tabs)",
    "return (id of newTab) as string",
    "end tell",
    "end tell",
  ]);
  return String(out || "").trim();
}

function setTabUrl(tabId, url) {
  osa([
    ...targetTabLines(tabId),
    `set URL of targetTab to "${appleEscape(url)}"`,
    "end tell",
  ]);
}

function closeTab(tabId) {
  try {
    osa([
      ...targetTabLines(tabId),
      "close targetTab",
      "end tell",
    ]);
  } catch {
    // Ignore close failures so one bad tab does not stop the batch.
  }
}

function confirmDownloadPrompt() {
  try {
    const result = osa([
      'tell application "Google Chrome" to activate',
      'tell application "System Events"',
      'tell process "Google Chrome"',
      "if exists window 1 then",
      "if exists sheet 1 of window 1 then",
      'try',
      'click button "保存" of sheet 1 of window 1',
      'return "clicked-save-cn"',
      'end try',
      'try',
      'click button "Save" of sheet 1 of window 1',
      'return "clicked-save-en"',
      'end try',
      'try',
      'click button 2 of sheet 1 of window 1',
      'return "clicked-save-index"',
      'end try',
      'try',
      'perform action "AXPress" of button "保存" of sheet 1 of window 1',
      'return "pressed-save-cn"',
      'end try',
      'try',
      'perform action "AXPress" of button "Save" of sheet 1 of window 1',
      'return "pressed-save-en"',
      'end try',
      'try',
      'perform action "AXPress" of button 2 of sheet 1 of window 1',
      'return "pressed-save-index"',
      'end try',
      "end if",
      "end if",
      "end tell",
      "end tell",
    ]);
    return String(result || "").trim();
  } catch {
    return "";
  }
}

async function settleDownloadPrompt() {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    await sleep(attempt === 0 ? 900 : 700);
    const outcome = confirmDownloadPrompt();
    if (outcome) {
      await sleep(1200);
      return outcome;
    }
  }
  return "";
}

function getTabMeta(tabId) {
  const raw = osa([
    ...targetTabLines(tabId),
    'return (title of targetTab) & " ||| " & (URL of targetTab)',
    "end tell",
  ]);
  const parts = String(raw || "").split(" ||| ");
  return {
    title: (parts[0] || "").trim(),
    url: (parts.slice(1).join(" ||| ") || "").trim(),
  };
}

function executeTabJs(tabId, script) {
  return osa([
    ...targetTabLines(tabId),
    `execute targetTab javascript "${jsEscape(script)}"`,
    "end tell",
  ]);
}

const CHILD_PAGE_SCRIPT = `
(function(){
  const clean = (s) => String(s || "").replace(/\\s+/g, " ").trim();
  const rows = [...document.querySelectorAll("tbody tr")].map((tr) => {
    const tds = [...tr.querySelectorAll("td")].map((td) => clean(td.innerText));
    const linkCell = tds[2] || "";
    const urlMatch = linkCell.match(/https?:\\S+/i);
    return {
      category: tds[1] || "",
      preview_link: urlMatch ? urlMatch[0] : "",
      row_text: clean(tr.innerText || "")
    };
  }).filter((row) => row.category || row.preview_link);
  const bodyText = clean(document.body && document.body.innerText ? document.body.innerText : "");
  return JSON.stringify({
    href: location.href,
    title: document.title || "",
    ready: document.readyState || "",
    scripts: document.scripts ? document.scripts.length : 0,
    rows,
    body_text: bodyText,
    row_count: rows.length
  });
})()
`;

async function waitForChildPageData(tabId, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  let last = {
    href: "",
    title: "",
    ready: "",
    scripts: 0,
    rows: [],
    body_text: "",
    row_count: 0,
  };
  while (Date.now() < deadline) {
    try {
      const raw = executeTabJs(tabId, CHILD_PAGE_SCRIPT);
      if (raw) {
        last = JSON.parse(raw);
      }
    } catch {
      // Keep polling while the page is transitioning.
    }

    const bodyText = String(last.body_text || "");
    if ((last.row_count || 0) > 0) {
      return last;
    }
    if (bodyText.includes("暂无关联信息")) {
      return last;
    }
    await sleep(1000);
  }
  return last;
}

function uniqueStrings(values) {
  const result = [];
  for (const value of values || []) {
    const text = String(value || "").trim();
    if (text && !result.includes(text)) {
      result.push(text);
    }
  }
  return result;
}

function normalizeSpuName(productName) {
  return String(productName || "")
    .replace(/[（(][^（）()]*?(香型|口味|味|款|版)[^（）()]*?[)）]\s*$/u, "")
    .replace(/\s+[^\s]+(?:香型|口味|味)$/u, "")
    .trim();
}

function groupRowsToSpu(rows) {
  const buckets = new Map();
  for (const row of rows || []) {
    const copy = { ...row };
    const spuName = normalizeSpuName(copy.product_name || "") || String(copy.product_name || "").trim() || "未命名SPU";
    copy.spu_name = spuName;
    if (!buckets.has(spuName)) {
      buckets.set(spuName, []);
    }
    buckets.get(spuName).push(copy);
  }

  return [...buckets.entries()].map(([spuName, bucketRows]) => {
    const sorted = [...bucketRows].sort((a, b) => {
      const left = `${a.filing_date || ""}|${a.product_name || ""}`;
      const right = `${b.filing_date || ""}|${b.product_name || ""}`;
      return right.localeCompare(left, "zh-CN");
    });
    const latest = sorted[0] || {};
    const filers = [...new Set(sorted.map((row) => String(row.filer || "").trim()).filter(Boolean))];
    return {
      spu_name: spuName,
      sku_count: sorted.length,
      latest_filing_date: latest.filing_date || "",
      latest_product_name: latest.product_name || "",
      filers,
      rows: sorted,
    };
  }).sort((a, b) => {
    const left = `${a.latest_filing_date || ""}|${a.latest_product_name || ""}`;
    const right = `${b.latest_filing_date || ""}|${b.latest_product_name || ""}`;
    return right.localeCompare(left, "zh-CN");
  });
}

function refreshAggregates(data) {
  let detailCount = 0;
  for (const item of data.results || []) {
    const rows = Array.isArray(item.month_rows) ? item.month_rows : [];
    item.month_rows = rows;
    item.all_rows = rows;
    item.month_count = rows.length;
    detailCount += rows.length;
    item.spu_groups = groupRowsToSpu(rows);
    const latest = [...rows].sort((a, b) => {
      const left = `${a.filing_date || ""}|${a.product_name || ""}`;
      const right = `${b.filing_date || ""}|${b.product_name || ""}`;
      return right.localeCompare(left, "zh-CN");
    })[0] || {};
    item.latest_filing_date = latest.filing_date || "";
    item.product_name = latest.product_name || "";
    item.filing_no = latest.filing_no || "";
    item.filer = latest.filer || "";
  }
  data.detail_count = detailCount;
}

function choosePreviewLink(attachmentItems) {
  const items = Array.isArray(attachmentItems) ? attachmentItems : [];
  const scored = items
    .filter((item) => item && item.preview_link)
    .map((item) => {
      const category = String(item.category || "");
      let score = 0;
      if (category.includes("立体")) {
        score += 20;
      }
      if (category.includes("包装")) {
        score += 10;
      }
      if (category.includes("说明书")) {
        score -= 50;
      }
      return { ...item, score };
    })
    .sort((a, b) => b.score - a.score);
  return scored[0] || null;
}

async function waitForPreviewTabReady(tabId, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  let last = { title: "", url: "" };
  while (Date.now() < deadline) {
    try {
      last = getTabMeta(tabId);
    } catch {
      await sleep(800);
      continue;
    }
    const title = String(last.title || "");
    if (title && !title.startsWith("hzpba.nmpa.gov.cn/")) {
      return last;
    }
    await sleep(1000);
  }
  return last;
}

async function claimChromeTabById(browser, tabId, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const tabs = await browser.user.openTabs();
    const found = tabs.find((tab) => String(tab.id) === String(tabId));
    if (found) {
      return browser.user.claimTab(found);
    }
    await sleep(800);
  }
  return null;
}

async function listDownloadFiles(limit = 120) {
  let names = [];
  try {
    names = await fs.readdir(homeDownloadsDir());
  } catch {
    return [];
  }
  const rows = [];
  for (const name of names) {
    const absPath = path.join(homeDownloadsDir(), name);
    try {
      const stat = await fs.stat(absPath);
      if (!stat.isFile()) {
        continue;
      }
      rows.push({
        name,
        absPath,
        size: stat.size,
        mtimeMs: stat.mtimeMs,
      });
    } catch {
      // Ignore transient files while polling downloads.
    }
  }
  return rows.sort((a, b) => b.mtimeMs - a.mtimeMs).slice(0, limit);
}

function isPdfPath(filePath) {
  const name = path.basename(String(filePath || ""));
  if (/\.pdf$/i.test(name)) {
    return true;
  }
  try {
    return /PDF document/i.test(runText("file", [filePath]));
  } catch {
    return false;
  }
}

async function waitForDownloadedPdf(beforeFiles, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  const knownKeys = new Set((beforeFiles || []).map((item) => `${item.absPath}|${item.mtimeMs}|${item.size}`));
  while (Date.now() < deadline) {
    const current = await listDownloadFiles(160);
    for (const item of current) {
      const key = `${item.absPath}|${item.mtimeMs}|${item.size}`;
      if (knownKeys.has(key)) {
        continue;
      }
      if (isPdfPath(item.absPath)) {
        return item;
      }
    }
    await sleep(1000);
  }
  return null;
}

async function persistDownloadedPdf(month, brand, filingNo, sourcePath) {
  const targetDir = rowPackageDir(month, brand, filingNo);
  await fs.mkdir(targetDir, { recursive: true });
  const targetPath = path.join(targetDir, "package_source.pdf");
  await fs.copyFile(sourcePath, targetPath);
  return targetPath;
}

async function renderPdfToPackageImages(pdfPath, targetDir) {
  await fs.mkdir(targetDir, { recursive: true });
  const renderPrefix = path.join(targetDir, "__package_render");
  runText("pdftoppm", ["-png", "-r", "180", pdfPath, renderPrefix]);
  const renderFiles = (await fs.readdir(targetDir))
    .filter((name) => /^__package_render-\d+\.png$/i.test(name))
    .sort((a, b) => a.localeCompare(b, "en"));
  const captures = [];
  let index = 1;
  for (const name of renderFiles) {
    const sourcePath = path.join(targetDir, name);
    const targetPath = path.join(targetDir, `package_capture_${String(index).padStart(2, "0")}.png`);
    await fs.rename(sourcePath, targetPath).catch(async () => {
      const bytes = await fs.readFile(sourcePath);
      await fs.writeFile(targetPath, bytes);
      await fs.unlink(sourcePath).catch(() => {});
    });
    captures.push(relOutputPath(targetPath));
    index += 1;
  }
  return captures;
}

async function normalizePreviewViewport(previewTab) {
  try {
    await previewTab.cua.keypress({ keys: ["Meta", "0"] });
    await previewTab.playwright.waitForTimeout(1200);
  } catch {
    // Ignore shortcut failures and continue with the current zoom level.
  }
  for (let i = 0; i < 4; i += 1) {
    try {
      await previewTab.cua.keypress({ keys: ["Meta", "-"] });
      await previewTab.playwright.waitForTimeout(700);
    } catch {
      break;
    }
  }
  try {
    await previewTab.cua.keypress({ keys: ["Home"] });
    await previewTab.playwright.waitForTimeout(1000);
  } catch {
    // Ignore Home failures and continue.
  }
}

async function captureScrollablePreview(previewTab, targetDir) {
  await fs.mkdir(targetDir, { recursive: true });
  const captures = [];
  const seen = new Set();
  const maxShots = 8;
  let shellOnly = true;

  await normalizePreviewViewport(previewTab);

  for (let index = 0; index < maxShots; index += 1) {
    await previewTab.playwright.waitForTimeout(index === 0 ? 1800 : 1200);
    const bytes = await previewTab.screenshot({});
    const buffer = Buffer.from(bytes);
    const signature = `${buffer.length}:${buffer.subarray(0, 48).toString("base64")}`;
    if (seen.has(signature)) {
      break;
    }
    seen.add(signature);
    const targetPath = path.join(targetDir, `package_capture_${String(index + 1).padStart(2, "0")}.png`);
    await fs.writeFile(targetPath, buffer);
    captures.push(relOutputPath(targetPath));

    if (!isLikelyBlankCapture(buffer) && !isLikelyPdfViewerShell(buffer)) {
      shellOnly = false;
    }

    if (index >= 1 && shellOnly && buffer.length <= 8000) {
      break;
    }

    const { height } = pngSize(buffer);
    const scrollStep = Math.max(520, Math.min(860, height - 110));
    try {
      await previewTab.cua.scroll({ x: 1100, y: 650, scrollX: 0, scrollY: scrollStep });
    } catch {
      break;
    }
  }

  return {
    shellOnly,
    package_images: captures,
  };
}

async function capturePreviewScreenshot(browser, rowContext, previewUrl, extraWaitMs = 0) {
  const previewNativeTabId = createNativeTab(previewUrl);
  const previewMeta = await waitForPreviewTabReady(previewNativeTabId, 36000);
  const previewTab = await claimChromeTabById(browser, previewNativeTabId, 12000);
  if (!previewTab) {
    closeTab(previewNativeTabId);
    return {
      ok: false,
      status: "preview_tab_not_found",
      title: previewMeta.title || "",
      tab_id: previewNativeTabId,
    };
  }

  try {
    const targetDir = rowPackageDir(rowContext.month, rowContext.brand, rowContext.filingNo);
    await fs.mkdir(targetDir, { recursive: true });
    const beforeDownloads = await listDownloadFiles(160);
    const attempts = [
      { waitMs: previewMeta.title ? 9000 : 14000, reload: false },
      { waitMs: 12000 + extraWaitMs, reload: false },
      { waitMs: 12000 + extraWaitMs, reload: true },
      { waitMs: 10000 + extraWaitMs, reload: false },
    ];
    let finalTitle = previewMeta.title || "";
    let shellOnly = true;
    let packageImages = [];
    let packageFiles = [];

    for (const attempt of attempts) {
      if (attempt.reload) {
        await previewTab.reload();
      }
      if (attempt.waitMs > 0) {
        await previewTab.playwright.waitForTimeout(attempt.waitMs);
      }
      finalTitle = (await previewTab.title()) || finalTitle;
      try {
        await previewTab.cua.click({ x: 1303, y: 27 });
        await settleDownloadPrompt();
      } catch {
        // Ignore download button click failures and continue to screenshot fallback.
      }
      const downloadedPdf = await waitForDownloadedPdf(beforeDownloads, 15000);
      if (downloadedPdf) {
        const persistedPdf = await persistDownloadedPdf(
          rowContext.month,
          rowContext.brand,
          rowContext.filingNo,
          downloadedPdf.absPath,
        );
        packageFiles = [relOutputPath(persistedPdf)];
        packageImages = await renderPdfToPackageImages(persistedPdf, targetDir);
        shellOnly = packageImages.length === 0;
        if (packageImages.length) {
          break;
        }
      }
      const captured = await captureScrollablePreview(previewTab, targetDir);
      packageImages = captured.package_images;
      shellOnly = captured.shellOnly;
      if (!shellOnly && packageImages.length) {
        break;
      }
    }
    return {
      ok: packageImages.length > 0,
      status: shellOnly ? "captured_preview_screenshot_but_viewer_shell" : "captured_preview_screenshot",
      title: finalTitle || previewMeta.title || "",
      tab_id: previewNativeTabId,
      package_images: packageImages,
      package_files: packageFiles,
    };
  } finally {
    try {
      await previewTab.close();
    } catch {
      closeTab(previewNativeTabId);
    }
  }
}

function isLikelyBlankCapture(buffer) {
  const signature = "IHDR";
  const markerIndex = buffer.indexOf(signature, 0, "ascii");
  if (markerIndex < 0 || markerIndex + 12 >= buffer.length) {
    return false;
  }
  const width = buffer.readUInt32BE(markerIndex + 4);
  const height = buffer.readUInt32BE(markerIndex + 8);
  const expectedArea = width * height;
  if (!expectedArea) {
    return false;
  }
  const fileSize = buffer.length;
  return fileSize <= 8000;
}

function isLikelyPdfViewerShell(buffer) {
  const signature = "IHDR";
  const markerIndex = buffer.indexOf(signature, 0, "ascii");
  if (markerIndex < 0 || markerIndex + 12 >= buffer.length) {
    return false;
  }
  const width = buffer.readUInt32BE(markerIndex + 4);
  const height = buffer.readUInt32BE(markerIndex + 8);
  const fileSize = buffer.length;
  if (width === 1407 && height === 770 && fileSize <= 15000) {
    return true;
  }
  return false;
}

async function captureRow(browser, month, brand, row) {
  const mainId = String(row._main_id || row.main_id || "").trim();
  const filingNo = String(row.filing_no || "").trim();
  if (!mainId) {
    return {
      status: "no_main_id",
      package_images: [],
      package_files: [],
      package_preview_links: [],
      package_attachment_items: [],
    };
  }

  const childUrl = buildChildListUrl(mainId);
  const childNativeTabId = createNativeTab(childUrl);
  let childData;
  try {
    childData = await waitForChildPageData(childNativeTabId, 22000);
  } finally {
    closeTab(childNativeTabId);
  }
  const attachmentItems = uniqueStrings(
    (childData.rows || []).map((item) => JSON.stringify(item)),
  ).map((text) => JSON.parse(text));
  const previewLinks = uniqueStrings(attachmentItems.map((item) => item.preview_link));

  if (!previewLinks.length) {
    const bodyText = String(childData.body_text || "");
    return {
      status: bodyText.includes("暂无关联信息") ? "no_package_info" : "no_package_link_found",
      package_images: [],
      package_files: [],
      package_preview_links: [],
      package_attachment_items: attachmentItems,
    };
  }

  const chosen = choosePreviewLink(attachmentItems) || { preview_link: previewLinks[0] };
  let captured = await capturePreviewScreenshot(browser, {
    month,
    brand,
    filingNo,
  }, chosen.preview_link);
  if (captured.package_images && captured.package_images[0]) {
    const absPath = path.join(OUTPUT_DIR, captured.package_images[0]);
    try {
      const bytes = await fs.readFile(absPath);
      if (isLikelyBlankCapture(bytes) || isLikelyPdfViewerShell(bytes)) {
        captured = await capturePreviewScreenshot(browser, {
          month,
          brand,
          filingNo,
        }, chosen.preview_link, 6000);
        if (captured.package_images && captured.package_images[0]) {
          const retriedAbsPath = path.join(OUTPUT_DIR, captured.package_images[0]);
          const retriedBytes = await fs.readFile(retriedAbsPath);
          if (isLikelyBlankCapture(retriedBytes) || isLikelyPdfViewerShell(retriedBytes)) {
            captured.status = "captured_preview_screenshot_but_viewer_shell";
          }
        }
      }
    } catch {
      // Ignore validation failures and keep the original capture result.
    }
  }

  return {
    status: captured.status,
    package_images: captured.package_images || [],
    package_files: captured.package_files || [],
    package_preview_links: previewLinks,
    package_attachment_items: attachmentItems,
    package_capture_title: captured.title || "",
  };
}

function loadMonthRows(data, onlyBrands) {
  const brandFilter = onlyBrands && onlyBrands.length ? new Set(onlyBrands) : null;
  const targets = [];
  for (const item of data.results || []) {
    const brand = String(item.brand || "").trim();
    if (!brand) {
      continue;
    }
    if (brandFilter && !brandFilter.has(brand)) {
      continue;
    }
    const rows = Array.isArray(item.month_rows) ? item.month_rows : [];
    for (const row of rows) {
      targets.push({ brand, row });
    }
  }
  return targets;
}

function normalizeFilingNo(value) {
  return String(value || "").replace(/\s+/g, "").trim();
}

function filterTargets(targets, options = {}) {
  const filings = Array.isArray(options.filingNos) ? options.filingNos.map(normalizeFilingNo).filter(Boolean) : [];
  if (!filings.length) {
    return targets;
  }
  const filingSet = new Set(filings);
  return targets.filter(({ row }) => filingSet.has(normalizeFilingNo(row.filing_no)));
}

async function saveMonthJson(jsonPath, data) {
  refreshAggregates(data);
  await fs.writeFile(jsonPath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

export async function captureMonthPackageScreenshots(options = {}) {
  if (!globalThis.browser) {
    throw new Error("browser runtime not initialized");
  }
  const month = String(options.month || "").trim();
  if (!month) {
    throw new Error("month is required");
  }

  const onlyBrands = Array.isArray(options.onlyBrands) ? options.onlyBrands.map(String) : [];
  const limit = Number(options.limit || 0);
  const force = Boolean(options.force);
  const jsonPath = path.join(OUTPUT_DIR, `${month}_brand_latest.json`);
  const data = JSON.parse(await fs.readFile(jsonPath, "utf8"));
  const targets = filterTargets(loadMonthRows(data, onlyBrands), options);

  let processed = 0;
  let captured = 0;
  let skipped = 0;
  const summary = [];

  for (const target of targets) {
    if (limit > 0 && processed >= limit) {
      break;
    }

    const { brand, row } = target;
    row.package_images = Array.isArray(row.package_images) ? row.package_images : [];
    row.package_files = Array.isArray(row.package_files) ? row.package_files : [];
    row.package_preview_links = Array.isArray(row.package_preview_links) ? row.package_preview_links : [];
    row.package_attachment_items = Array.isArray(row.package_attachment_items) ? row.package_attachment_items : [];

    if (!force && row.package_images.length) {
      skipped += 1;
      summary.push({
        brand,
        filing_no: row.filing_no || "",
        product_name: row.product_name || "",
        status: "skipped_existing_images",
      });
      continue;
    }

    processed += 1;
    let result;
    try {
      result = await captureRow(globalThis.browser, month, brand, row);
    } catch (error) {
      const message = String(error && error.message ? error.message : error);
      result = {
        status: `capture_error:${message}`,
        package_images: [],
        package_files: [],
        package_preview_links: [],
        package_attachment_items: [],
      };
    }

    row.package_images = result.package_images || [];
    row.package_files = result.package_files || [];
    row.package_preview_links = result.package_preview_links || [];
    row.package_attachment_items = result.package_attachment_items || [];
    row.package_info_status = result.status || row.package_info_status || "";
    if (result.package_capture_title) {
      row.package_capture_title = result.package_capture_title;
    }

    if (row.package_images.length) {
      captured += 1;
    }

    summary.push({
      brand,
      filing_no: row.filing_no || "",
      product_name: row.product_name || "",
      status: row.package_info_status || "",
      package_images: row.package_images || [],
      package_files: row.package_files || [],
      package_preview_links: row.package_preview_links || [],
    });

    await saveMonthJson(jsonPath, data);
  }

  await saveMonthJson(jsonPath, data);
  return {
    json_path: jsonPath,
    processed,
    captured,
    skipped,
    summary,
  };
}

export async function captureSpecificRows(options = {}) {
  const filingNos = Array.isArray(options.filingNos) ? options.filingNos : [];
  if (!filingNos.length) {
    throw new Error("filingNos is required");
  }
  return captureMonthPackageScreenshots({
    ...options,
    filingNos,
  });
}

export async function captureSingleRow(options = {}) {
  if (!globalThis.browser) {
    throw new Error("browser runtime not initialized");
  }
  const month = String(options.month || "").trim();
  const filingNo = normalizeFilingNo(options.filingNo);
  if (!month) {
    throw new Error("month is required");
  }
  if (!filingNo) {
    throw new Error("filingNo is required");
  }

  const jsonPath = path.join(OUTPUT_DIR, `${month}_brand_latest.json`);
  const data = JSON.parse(await fs.readFile(jsonPath, "utf8"));
  const targets = filterTargets(loadMonthRows(data, []), { filingNos: [filingNo] });
  const target = targets[0];
  if (!target) {
    throw new Error(`filing not found: ${filingNo}`);
  }

  const { brand, row } = target;
  row.package_images = Array.isArray(row.package_images) ? row.package_images : [];
  row.package_files = Array.isArray(row.package_files) ? row.package_files : [];
  row.package_preview_links = Array.isArray(row.package_preview_links) ? row.package_preview_links : [];
  row.package_attachment_items = Array.isArray(row.package_attachment_items) ? row.package_attachment_items : [];

  let result;
  try {
    result = await captureRow(globalThis.browser, month, brand, row);
  } catch (error) {
    const message = String(error && error.message ? error.message : error);
    result = {
      status: `capture_error:${message}`,
      package_images: [],
      package_files: [],
      package_preview_links: [],
      package_attachment_items: [],
    };
  }

  row.package_images = result.package_images || [];
  row.package_files = result.package_files || [];
  row.package_preview_links = result.package_preview_links || [];
  row.package_attachment_items = result.package_attachment_items || [];
  row.package_info_status = result.status || row.package_info_status || "";
  if (result.package_capture_title) {
    row.package_capture_title = result.package_capture_title;
  }

  await saveMonthJson(jsonPath, data);

  return {
    json_path: jsonPath,
    brand,
    filing_no: row.filing_no || "",
    product_name: row.product_name || "",
    status: row.package_info_status || "",
    package_images: row.package_images || [],
    package_files: row.package_files || [],
    package_preview_links: row.package_preview_links || [],
  };
}
