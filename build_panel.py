from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spu_utils import group_rows_to_spu


OUTPUT_DIR = Path("output")
MONTHLY_DIR = OUTPUT_DIR / "monthly"
SOURCE_GLOB = "*_brand_latest.json"
TARGET_HTML = OUTPUT_DIR / "brand_dashboard.html"
MONTH_PANEL_HTML = OUTPUT_DIR / "2026-06_brand_panel.html"
ORDERED_BRANDS = ["参半", "笑容加", "高露洁", "佳洁士", "BOP", "白惜", "俊小白", "冷酸灵", "舒适达", "好来"]


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>国产牙膏备案总面板</title>
  <style>
    :root {
      --bg: #f3ede3;
      --panel: #fffaf4;
      --panel-strong: #fff6e8;
      --ink: #1f2937;
      --muted: #6b7280;
      --line: #e7dccb;
      --accent: #b45309;
      --accent-deep: #7c2d12;
      --accent-soft: #f59e0b;
      --ok: #0f766e;
      --empty: #9a3412;
      --shadow: 0 18px 40px rgba(84, 54, 20, 0.10);
      --shadow-strong: 0 28px 64px rgba(84, 54, 20, 0.16);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(245, 158, 11, 0.16), transparent 28%),
        radial-gradient(circle at bottom right, rgba(180, 83, 9, 0.12), transparent 26%),
        linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
      font-family: "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
    }
    .wrap {
      max-width: 1480px;
      margin: 0 auto;
      padding: 28px 20px 40px;
    }
    .hero {
      background: linear-gradient(135deg, rgba(180, 83, 9, 0.96), rgba(124, 45, 18, 0.93));
      color: #fffdf8;
      border-radius: 24px;
      padding: 28px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .hero h1 {
      margin: 0 0 10px;
      font-size: clamp(26px, 4vw, 42px);
      line-height: 1.1;
    }
    .hero p {
      margin: 0;
      max-width: 860px;
      color: rgba(255, 250, 241, 0.88);
      line-height: 1.6;
      font-size: 15px;
    }
    .stats {
      margin-top: 20px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
    }
    .stat {
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 18px;
      padding: 14px 16px;
    }
    .stat b {
      display: block;
      font-size: 22px;
      margin-bottom: 4px;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      margin: 22px 0 14px;
    }
    .toolbar-left {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    .search,
    .select {
      background: var(--panel);
      border: 1px solid var(--line);
      color: var(--ink);
      box-shadow: 0 10px 24px rgba(84, 54, 20, 0.06);
    }
    .search {
      width: min(360px, 100%);
      border-radius: 999px;
      padding: 12px 16px;
    }
    .select {
      border-radius: 14px;
      padding: 11px 14px;
      min-width: 140px;
    }
    .chipbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .chip {
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      border-radius: 999px;
      padding: 8px 12px;
      cursor: pointer;
    }
    .chip.active {
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .panel-head {
      padding: 18px 20px 8px;
    }
    .panel-head h2 {
      margin: 0;
      font-size: 20px;
    }
    .panel-head p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 13px;
    }
    .table-wrap {
      overflow: auto;
      padding: 8px 14px 16px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 720px;
    }
    th, td {
      padding: 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
      line-height: 1.45;
    }
    th {
      position: sticky;
      top: 0;
      background: #fff7eb;
      z-index: 1;
      color: var(--accent-deep);
      font-weight: 700;
      white-space: nowrap;
    }
    tbody tr {
      cursor: pointer;
    }
    tbody tr:hover {
      background: rgba(245, 158, 11, 0.08);
    }
    tbody tr.selected {
      background: rgba(180, 83, 9, 0.10);
    }
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }
    .badge.ok {
      background: rgba(15, 118, 110, 0.10);
      color: var(--ok);
    }
    .badge.empty {
      background: rgba(154, 52, 18, 0.10);
      color: var(--empty);
    }
    .detail {
      padding: 16px 18px 20px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .detail-card {
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 14px 12px;
      background: rgba(255,255,255,0.64);
    }
    .detail-card.brand-meta {
      border: 1px solid rgba(124, 45, 18, 0.20);
      background:
        radial-gradient(circle at top right, rgba(245, 158, 11, 0.20), transparent 30%),
        linear-gradient(145deg, rgba(124, 45, 18, 0.96), rgba(180, 83, 9, 0.92));
      color: #fffaf4;
      box-shadow: 0 24px 44px rgba(124, 45, 18, 0.20);
      padding: 20px 20px 18px;
    }
    .detail-card.brand-meta .brand-lead,
    .detail-card.brand-meta .kv dt,
    .detail-card.brand-meta .kv dd,
    .detail-card.brand-meta .metric-box span,
    .detail-card.brand-meta .eyebrow {
      color: rgba(255, 248, 240, 0.84);
    }
    .detail-card.brand-meta .metric-box {
      border-color: rgba(255,255,255,0.18);
      background: rgba(255,255,255,0.10);
    }
    .detail-card.brand-meta .metric-box b,
    .detail-card.brand-meta .brand-hero-main h3 {
      color: #fffdf8;
    }
    .detail-card.spu-card {
      background:
        linear-gradient(180deg, rgba(255,255,255,0.96), rgba(255,250,243,0.92)),
        rgba(255,255,255,0.74);
      border-style: solid;
      border-color: rgba(180, 83, 9, 0.14);
      box-shadow: 0 14px 30px rgba(84, 54, 20, 0.08);
      padding-top: 16px;
    }
    .detail-card h3 {
      margin: 0 0 10px;
      font-size: 18px;
    }
    .brand-hero {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(220px, 0.8fr);
      gap: 16px;
      align-items: start;
      margin-bottom: 12px;
    }
    .brand-hero-main h3 {
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.1;
    }
    .brand-lead {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
      margin: 0;
    }
    .brand-metrics {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .metric-box {
      border: 1px solid rgba(180, 83, 9, 0.18);
      border-radius: 16px;
      background: rgba(255,255,255,0.72);
      padding: 12px 12px 10px;
    }
    .metric-box b {
      display: block;
      font-size: 22px;
      line-height: 1.1;
      margin-bottom: 4px;
      color: var(--accent-deep);
    }
    .metric-box span {
      color: var(--muted);
      font-size: 12px;
    }
    .eyebrow {
      margin-bottom: 10px;
      color: var(--accent-deep);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
    }
    .spu-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 10px;
      padding-bottom: 10px;
      border-bottom: 1px solid rgba(180, 83, 9, 0.10);
    }
    .spu-name {
      flex: 1;
    }
    .spu-chip {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 7px 12px;
      border-radius: 999px;
      background: rgba(180, 83, 9, 0.10);
      color: var(--accent-deep);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }
    .spu-subline {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 10px 0 14px;
    }
    .mini-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      background: rgba(180, 83, 9, 0.08);
      color: var(--accent-deep);
      border: 1px solid rgba(180, 83, 9, 0.12);
    }
    .kv {
      display: grid;
      grid-template-columns: 96px 1fr;
      gap: 8px 10px;
      font-size: 14px;
    }
    .kv dt { color: var(--muted); }
    .detail-table {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 16px;
    }
    .detail-table .col-seq {
      width: 72px;
      min-width: 72px;
      white-space: nowrap;
    }
    .detail-table .col-date {
      width: 112px;
      min-width: 112px;
      white-space: nowrap;
    }
    .detail-table .col-filing {
      width: 206px;
      min-width: 206px;
      white-space: nowrap;
    }
    .detail-table .col-filer {
      width: 180px;
      min-width: 180px;
    }
    .detail-table .col-link {
      width: 92px;
      min-width: 92px;
      text-align: center;
      white-space: nowrap;
    }
    .detail-table .col-package {
      width: 176px;
      min-width: 176px;
      white-space: nowrap;
    }
    .icon-link,
    .package-trigger {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      border-radius: 12px;
      border: 1px solid rgba(180, 83, 9, 0.18);
      background: rgba(255,255,255,0.88);
      color: var(--accent-deep);
      text-decoration: none;
      cursor: pointer;
      min-height: 34px;
      padding: 0 12px;
      font-size: 12px;
      font-weight: 700;
      box-shadow: 0 8px 18px rgba(84, 54, 20, 0.08);
    }
    .icon-link {
      width: 36px;
      min-width: 36px;
      height: 36px;
      padding: 0;
      font-size: 16px;
    }
    .package-trigger:hover,
    .icon-link:hover {
      transform: translateY(-1px);
      box-shadow: 0 12px 22px rgba(84, 54, 20, 0.12);
    }
    .package-trigger {
      background: linear-gradient(180deg, #fffdf9, #fff4df);
    }
    .package-cell {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .inline-status {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid transparent;
      white-space: nowrap;
    }
    .inline-status.ok {
      color: var(--ok);
      background: rgba(15, 118, 110, 0.10);
      border-color: rgba(15, 118, 110, 0.16);
    }
    .inline-status.empty {
      color: var(--empty);
      background: rgba(154, 52, 18, 0.08);
      border-color: rgba(154, 52, 18, 0.14);
    }
    .package-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 18px;
      margin-top: 18px;
      align-items: stretch;
    }
    .package-card {
      border: 1px solid var(--line);
      border-radius: 22px;
      overflow: hidden;
      background: #fffdf9;
      text-decoration: none;
      color: inherit;
      box-shadow: 0 18px 34px rgba(84, 54, 20, 0.10);
      transition: transform 120ms ease, box-shadow 120ms ease;
      display: grid;
      grid-template-rows: minmax(280px, 360px) auto;
    }
    .package-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 24px 42px rgba(84, 54, 20, 0.14);
    }
    .package-card img {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: contain;
      object-position: center center;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.72), rgba(247,240,230,0.9)),
        #f7f0e6;
      padding: 16px;
    }
    .package-card .package-caption {
      padding: 12px 14px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
      word-break: break-all;
      border-top: 1px solid rgba(180, 83, 9, 0.10);
      background: rgba(255,255,255,0.95);
    }
    .package-card .package-stage {
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100%;
      background:
        radial-gradient(circle at center, rgba(255,255,255,0.76), rgba(247,240,230,0.94)),
        #f7f0e6;
      padding: 18px;
    }
    .package-card .package-stage.pdf-stage {
      color: #7c2d12;
      font-weight: 800;
      font-size: 34px;
      letter-spacing: 0.04em;
    }
    .package-card .package-index {
      position: absolute;
      top: 14px;
      left: 14px;
      z-index: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 34px;
      height: 34px;
      padding: 0 10px;
      border-radius: 999px;
      background: rgba(124, 45, 18, 0.88);
      color: #fffdf8;
      font-size: 12px;
      font-weight: 700;
      box-shadow: 0 10px 18px rgba(84, 54, 20, 0.18);
    }
    .package-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    }
    .package-toolbar .meta {
      color: var(--muted);
      font-size: 13px;
    }
    .overlay.package-overlay {
      align-items: flex-start;
      padding-top: 26px;
      background: rgba(31, 41, 55, 0.52);
    }
    .floating-card.package-card-shell {
      width: min(1320px, 100%);
      max-height: min(92vh, 980px);
      box-shadow: var(--shadow-strong);
    }
    .package-empty {
      margin-top: 14px;
      padding: 12px 14px;
      border: 1px dashed var(--line);
      border-radius: 14px;
      color: var(--muted);
      background: rgba(255,255,255,0.8);
    }
    .detail-table table {
      min-width: 100%;
    }
    .brand-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      padding: 10px 18px 20px;
    }
    .brand-card {
      border: 1px solid var(--line);
      border-radius: 24px;
      background:
        radial-gradient(circle at top right, rgba(245, 158, 11, 0.16), transparent 28%),
        linear-gradient(180deg, rgba(255,255,255,0.96), rgba(255,247,235,0.92));
      padding: 18px;
      cursor: pointer;
      transition: transform 120ms ease, box-shadow 120ms ease, border-color 120ms ease;
      box-shadow: 0 14px 28px rgba(84, 54, 20, 0.08);
      position: relative;
      overflow: hidden;
    }
    .brand-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 20px 36px rgba(84, 54, 20, 0.12);
    }
    .brand-card.selected {
      border-color: var(--accent);
      background:
        radial-gradient(circle at top right, rgba(245, 158, 11, 0.20), transparent 32%),
        linear-gradient(180deg, rgba(255,251,245,1), rgba(255,241,219,0.98));
      box-shadow: 0 22px 40px rgba(180, 83, 9, 0.18);
    }
    .brand-card-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 16px;
    }
    .brand-name {
      font-size: 20px;
      font-weight: 700;
      color: var(--accent-deep);
    }
    .brand-card .count {
      display: flex;
      align-items: baseline;
      gap: 6px;
      margin-bottom: 8px;
    }
    .brand-card .count b {
      font-size: 40px;
      line-height: 1;
    }
    .brand-card .count span {
      color: var(--muted);
      font-size: 13px;
    }
    .brand-card .sub {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .brand-card .accent-bar {
      margin-top: 14px;
      height: 8px;
      border-radius: 999px;
      background: rgba(180, 83, 9, 0.10);
      overflow: hidden;
    }
    .brand-card .accent-bar span {
      display: block;
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent-soft), var(--accent));
    }
    .hint {
      color: var(--muted);
      font-size: 13px;
    }
    .overlay {
      position: fixed;
      inset: 0;
      background: rgba(31, 41, 55, 0.42);
      backdrop-filter: blur(6px);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      z-index: 999;
    }
    .overlay.open {
      display: flex;
    }
    .modal {
      width: min(1100px, 100%);
      max-height: min(88vh, 900px);
      overflow: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow-strong);
    }
    .modal-head {
      position: sticky;
      top: 0;
      z-index: 2;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 18px 20px 10px;
      background: rgba(255, 250, 243, 0.96);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--line);
    }
    .modal-head h2 {
      margin: 0;
      font-size: 22px;
    }
    .modal-head p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
    }
    .close-btn {
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.88);
      color: var(--accent-deep);
      border-radius: 999px;
      padding: 10px 14px;
      cursor: pointer;
      font-weight: 700;
    }
    .empty-box {
      padding: 28px 18px;
      text-align: center;
      color: var(--muted);
    }
    .floating-card {
      width: min(980px, 100%);
      max-height: min(84vh, 860px);
      overflow: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 26px;
      box-shadow: 0 28px 80px rgba(31, 41, 55, 0.24);
    }
    .floating-head {
      position: sticky;
      top: 0;
      z-index: 2;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 18px 20px 10px;
      background: rgba(255, 250, 243, 0.96);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--line);
    }
    .floating-head h3 {
      margin: 0;
      font-size: 20px;
    }
    .floating-head p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
    }
    .floating-body {
      padding: 18px 20px 22px;
    }
    .overlay-note {
      margin-top: 12px;
      font-size: 13px;
      color: var(--muted);
    }
    .mono-path {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 11px;
      line-height: 1.5;
    }
    code {
      background: rgba(124, 45, 18, 0.08);
      padding: 2px 6px;
      border-radius: 6px;
    }
    @media (max-width: 680px) {
      .wrap { padding: 18px 12px 28px; }
      .hero { padding: 22px 18px; border-radius: 20px; }
      .panel { border-radius: 20px; }
      .panel-head { padding: 16px 16px 6px; }
      .table-wrap { padding: 8px 8px 14px; }
      .brand-grid { padding: 8px 12px 16px; }
      .brand-hero { grid-template-columns: 1fr; }
      .brand-metrics { grid-template-columns: 1fr 1fr; }
      .toolbar-left { width: 100%; }
      .search, .select { width: 100%; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>国产牙膏备案总面板</h1>
      <p>自动累计 <code>output</code> 目录中的月度抓取结果。当前以 SPU 维度归整同品牌下的多个 SKU，并尽量提供可直接访问的备案详情页链接；月度明细仅收录各月份实际命中的记录，不再携带整段品牌历史深页结果。</p>
      <div class="stats" id="stats"></div>
    </section>

    <div class="toolbar">
      <div class="toolbar-left">
        <select id="yearSelect" class="select"></select>
        <select id="monthSelect" class="select"></select>
        <input id="searchInput" class="search" type="search" placeholder="搜索品牌、SPU、备案编号、备案人、产品名称" />
        <div class="chipbar">
          <button class="chip active" data-filter="all">全部品牌</button>
          <button class="chip" data-filter="hit">仅看有命中</button>
          <button class="chip" data-filter="empty">仅看无命中</button>
        </div>
      </div>
      <div class="hint" id="resultHint"></div>
    </div>

    <section class="panel">
      <div class="panel-head">
        <h2>品牌汇总</h2>
        <p>底层仅展示本周期各品牌命中数量。点击品牌卡片后，会在最上层弹出该品牌明细信息。</p>
      </div>
      <div class="brand-grid" id="summaryBody"></div>
    </section>
  </div>

  <div class="overlay" id="detailOverlay">
    <section class="modal">
      <div class="modal-head">
        <div>
          <h2>品牌明细</h2>
          <p>展示当前选中品牌在所选年月下按 SPU 归整后的备案信息。</p>
        </div>
        <button type="button" class="close-btn" id="closeDetail">关闭</button>
      </div>
      <div class="detail" id="detailPanel"></div>
    </section>
  </div>

  <div class="overlay package-overlay" id="packageOverlay">
    <section class="floating-card package-card-shell">
      <div class="floating-head">
        <div>
          <h3>包装信息</h3>
          <p id="packageOverlaySub">查看该 SKU / SPU 的包装截图与来源信息。</p>
        </div>
        <button type="button" class="close-btn" id="closePackage">关闭</button>
      </div>
      <div class="floating-body" id="packagePanel"></div>
    </section>
  </div>

  <script>
    const rawData = __JSON_DATA__;
    const allBrands = rawData.brands || [];
    const allPeriods = rawData.periods || [];
    const state = {
      year: rawData.default_year || "",
      month: rawData.default_month || "",
      filter: "all",
      query: "",
      selectedBrand: allBrands[0] || ""
    };

    const summaryBody = document.getElementById("summaryBody");
    const detailPanel = document.getElementById("detailPanel");
    const searchInput = document.getElementById("searchInput");
    const resultHint = document.getElementById("resultHint");
    const stats = document.getElementById("stats");
    const yearSelect = document.getElementById("yearSelect");
    const monthSelect = document.getElementById("monthSelect");
    const detailOverlay = document.getElementById("detailOverlay");
    const closeDetail = document.getElementById("closeDetail");
    const packageOverlay = document.getElementById("packageOverlay");
    const closePackage = document.getElementById("closePackage");
    const packagePanel = document.getElementById("packagePanel");
    const packageOverlaySub = document.getElementById("packageOverlaySub");

    function esc(value) {
      return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function assetHref(value) {
      const text = String(value == null ? "" : value).trim();
      if (!text) return "";
      if (/^(https?:|data:|file:)/i.test(text)) return text;
      return `./${text.replace(/^\\.\\//, "")}`;
    }

    function externalIcon() {
      return "⤴";
    }

    function imageIcon() {
      return "▣";
    }

    function periodKey(year, month) {
      return `${year}-${month}`;
    }

    function currentPeriodKey() {
      return periodKey(state.year, state.month);
    }

    function currentPeriodData() {
      return rawData.by_period[currentPeriodKey()] || {};
    }

    function availableYears() {
      return [...new Set(allPeriods.map(item => item.year))];
    }

    function availableMonthsForYear(year) {
      return allPeriods
        .filter(item => item.year === year)
        .map(item => item.month)
        .sort();
    }

    function fillYearOptions() {
      yearSelect.innerHTML = availableYears().map(year => (
        `<option value="${esc(year)}">${esc(year)}年</option>`
      )).join("");
      yearSelect.value = state.year;
    }

    function fillMonthOptions() {
      const months = availableMonthsForYear(state.year);
      if (!months.includes(state.month)) {
        state.month = months[months.length - 1] || "";
      }
      monthSelect.innerHTML = months.map(month => (
        `<option value="${esc(month)}">${esc(month)}月</option>`
      )).join("");
      monthSelect.value = state.month;
    }

    function itemsForCurrentPeriod() {
      const mapping = currentPeriodData();
      return allBrands.map(brand => mapping[brand] || {
        brand,
        month: currentPeriodKey(),
        latest_filing_date: "",
        filer: "",
        month_count: 0,
        note: `${currentPeriodKey()}未检索到备案记录`,
        month_rows: [],
        spu_groups: [],
        product_name: "",
        filing_no: ""
      });
    }

    function computeStats() {
      const items = itemsForCurrentPeriod();
      const hitBrands = items.filter(item => item.month_count > 0).length;
      const totalRows = items.reduce((sum, item) => sum + item.month_count, 0);
      const totalSpu = items.reduce((sum, item) => sum + ((item.spu_groups || []).length), 0);
      return [
        { label: "已收录月份", value: allPeriods.length },
        { label: "当前年份", value: state.year || "-" },
        { label: "当前月份", value: currentPeriodKey() || "-" },
        { label: "当月SPU数", value: totalSpu },
        { label: "当月明细条数", value: totalRows },
        { label: "有命中品牌", value: hitBrands }
      ];
    }

    function renderStats() {
      stats.innerHTML = computeStats().map(item => `
        <div class="stat">
          <b>${esc(item.value)}</b>
          <span>${esc(item.label)}</span>
        </div>
      `).join("");
    }

    function filteredItems() {
      const query = state.query.trim().toLowerCase();
      return itemsForCurrentPeriod().filter(item => {
        if (state.filter === "hit" && item.month_count <= 0) return false;
        if (state.filter === "empty" && item.month_count > 0) return false;
        if (!query) return true;
        const haystack = [
          item.brand,
          item.filer,
          item.filing_no,
          item.product_name,
          ...((item.spu_groups || []).flatMap(spu => [spu.spu_name, spu.latest_product_name, ...(spu.filers || [])])),
          ...(item.month_rows || []).flatMap(row => [row.product_name, row.filing_no, row.filer, row.filing_date])
        ].join(" ").toLowerCase();
        return haystack.includes(query);
      });
    }

    function ensureSelection(items) {
      if (!items.find(item => item.brand === state.selectedBrand)) {
        state.selectedBrand = items[0] ? items[0].brand : "";
      }
    }

    function renderSummary() {
      const items = filteredItems();
      ensureSelection(items);
      resultHint.textContent = `当前显示 ${items.length} / ${allBrands.length} 个品牌卡片`;
      const maxCount = Math.max(...items.map(item => item.month_count || 0), 1);
      summaryBody.innerHTML = items.map(item => {
        const selected = item.brand === state.selectedBrand ? "selected" : "";
        const badgeClass = item.month_count > 0 ? "ok" : "empty";
        const badgeLabel = item.month_count > 0 ? "本周期有命中" : "本周期无命中";
        const ratio = Math.max(8, Math.round(((item.month_count || 0) / maxCount) * 100));
        return `
          <article class="brand-card ${selected}" data-brand="${esc(item.brand)}">
            <div class="brand-card-head">
              <div class="brand-name">${esc(item.brand)}</div>
              <span class="badge ${badgeClass}">${badgeLabel}</span>
            </div>
            <div class="count">
              <b>${esc(item.month_count)}</b>
              <span>条SKU命中</span>
            </div>
            <div class="sub">SPU数：${esc((item.spu_groups || []).length)} · 周期：${esc(currentPeriodKey())}</div>
            <div class="accent-bar"><span style="width:${ratio}%"></span></div>
          </article>
        `;
      }).join("");

      summaryBody.querySelectorAll(".brand-card").forEach(card => {
        card.addEventListener("click", () => {
          state.selectedBrand = card.dataset.brand;
          renderSummary();
          renderDetail();
          detailOverlay.classList.add("open");
        });
      });
    }

    function renderDetail() {
      const item = itemsForCurrentPeriod().find(entry => entry.brand === state.selectedBrand);
      if (!item) {
        detailPanel.innerHTML = `<div class="empty-box">当前筛选下没有可展示的品牌。</div>`;
        return;
      }

      const monthRows = item.month_rows || [];
      const spuGroups = item.spu_groups || [];
      const meta = `
        <div class="detail-card brand-meta">
          <div class="eyebrow">品牌层</div>
          <div class="brand-hero">
            <div class="brand-hero-main">
              <h3>${esc(item.brand)}</h3>
              <p class="brand-lead">当前展示的是 ${esc(currentPeriodKey())} 下该品牌按 SPU 归整后的备案情况。上半部分是品牌概览，下方每个卡片代表一个 SPU，并继续展开对应 SKU 备案信息与产品包装。</p>
            </div>
            <div class="brand-metrics">
              <div class="metric-box">
                <b>${esc(spuGroups.length)}</b>
                <span>SPU 数量</span>
              </div>
              <div class="metric-box">
                <b>${esc(item.month_count)}</b>
                <span>SKU 命中</span>
              </div>
              <div class="metric-box">
                <b>${esc(item.latest_filing_date || "-")}</b>
                <span>最新备案日期</span>
              </div>
              <div class="metric-box">
                <b>${esc(item.filer || "-")}</b>
                <span>最新备案人</span>
              </div>
            </div>
          </div>
          <dl class="kv">
            <dt>查看年月</dt><dd>${esc(currentPeriodKey())}</dd>
            <dt>最新日期</dt><dd>${esc(item.latest_filing_date || "-")}</dd>
            <dt>最新产品</dt><dd>${esc(item.product_name || "-")}</dd>
            <dt>备案编号</dt><dd>${esc(item.filing_no || "-")}</dd>
            <dt>最新备案人</dt><dd>${esc(item.filer || "-")}</dd>
            <dt>SPU数量</dt><dd>${esc(spuGroups.length)}</dd>
            <dt>当月命中</dt><dd>${esc(item.month_count)}</dd>
            <dt>说明</dt><dd>${esc(item.note || "-")}</dd>
          </dl>
        </div>
      `;

      const renderPackageSection = (rows, contextTitle) => {
        const imgs = [...new Set((rows || []).flatMap(row => row.package_images || []).filter(Boolean))];
        const files = [...new Set((rows || []).flatMap(row => row.package_files || []).filter(Boolean))];
        if (!imgs.length && !files.length) return `<div class="package-empty">暂无产品包装信息</div>`;
        return `
          <div class="package-toolbar">
            <div class="meta">共 ${imgs.length} 张图片${files.length ? ` · ${files.length} 个原始PDF` : ""}</div>
            <div class="meta">${files.map(src => `<a class="icon-link" href="${esc(assetHref(src))}" target="_blank" rel="noopener noreferrer" title="打开原始PDF">PDF</a>`).join(" ")}</div>
          </div>
          <div class="package-grid">
            ${imgs.map((src, index) => `
              <a class="package-card" href="${esc(assetHref(src))}" target="_blank" rel="noopener noreferrer">
                <span class="package-index">图 ${index + 1}</span>
                <div class="package-stage">
                  <img src="${esc(assetHref(src))}" alt="产品立体图" loading="lazy" />
                </div>
                <div class="package-caption mono-path">${esc(src)}</div>
              </a>
            `).join("")}
            ${files.filter(src => !imgs.includes(src)).map((src, index) => `
              <a class="package-card" href="${esc(assetHref(src))}" target="_blank" rel="noopener noreferrer">
                <span class="package-index">PDF ${index + 1}</span>
                <div class="package-stage pdf-stage">PDF</div>
                <div class="package-caption mono-path">${esc(src)}</div>
              </a>
            `).join("")}
          </div>
          <div class="overlay-note">来源：${esc(contextTitle || "包装信息")}，图片可点击放大查看。</div>
        `;
      };

      const packageAssets = rows => {
        const sourceRows = rows || [];
        return {
          imgs: [...new Set(sourceRows.flatMap(row => row.package_images || []).filter(Boolean))],
          files: [...new Set(sourceRows.flatMap(row => row.package_files || []).filter(Boolean))],
        };
      };

      const packagePayload = rows => encodeURIComponent(JSON.stringify(rows || []));
      const packageTrigger = (rows, label) => `
        <button
          type="button"
          class="package-trigger"
          data-package-label="${esc(label || '包装信息')}"
          data-package-rows="${packagePayload(rows)}"
        >${imageIcon()} 包装信息</button>
      `;
      const packageInline = (rows, label) => {
        const assets = packageAssets(rows);
        if (!assets.imgs.length && !assets.files.length) {
          return `<span class="inline-status empty">暂无包装信息</span>`;
        }
        return `
          <div class="package-cell">
            <span class="inline-status ok">${assets.imgs.length} 张图${assets.files.length ? ` · ${assets.files.length} PDF` : ""}</span>
            ${packageTrigger(rows, label)}
          </div>
        `;
      };

      const table = spuGroups.length ? `
        ${spuGroups.map(spu => `
          <div class="detail-card spu-card">
            <div class="eyebrow">SPU层</div>
            <div class="spu-head">
              <div class="spu-name">
                <h3>${esc(spu.spu_name || "-")}</h3>
              </div>
              <div class="spu-chip">${esc(spu.sku_count || 0)} 个 SKU</div>
            </div>
            <div class="spu-subline">
              <span class="mini-pill">最新备案：${esc(spu.latest_filing_date || "-")}</span>
              <span class="mini-pill">备案人：${esc((spu.filers || []).join(" / ") || "-")}</span>
            </div>
            <dl class="kv">
              <dt>SPU最新日期</dt><dd>${esc(spu.latest_filing_date || "-")}</dd>
              <dt>代表产品</dt><dd>${esc(spu.latest_product_name || "-")}</dd>
              <dt>备案人</dt><dd>${esc((spu.filers || []).join(" / ") || "-")}</dd>
            </dl>
            <div>${packageInline(spu.rows || [], `${item.brand} / ${spu.spu_name || "-"}`)}</div>
            <div class="detail-table">
              <table>
                <thead>
                  <tr>
                    <th class="col-seq">序号</th>
                    <th class="col-date">备案日期</th>
                    <th>SKU产品名称</th>
                    <th class="col-filing">备案编号</th>
                    <th class="col-filer">备案人</th>
                    <th class="col-link">详情页</th>
                    <th class="col-package">包装信息</th>
                  </tr>
                </thead>
                <tbody>
                  ${(spu.rows || []).map(row => `
                    <tr>
                      <td class="col-seq">${esc(row.seq)}</td>
                      <td class="col-date">${esc(row.filing_date)}</td>
                      <td>${esc(row.product_name)}</td>
                      <td class="col-filing">${esc(row.filing_no)}</td>
                      <td class="col-filer">${esc(row.filer)}</td>
                      <td class="col-link">${row.detail_url ? `<a class="icon-link" href="${esc(row.detail_url)}" target="_blank" rel="noopener noreferrer" title="打开备案详情页">${externalIcon()}</a>` : '-'}</td>
                      <td class="col-package">${packageInline([row], `${item.brand} / ${row.product_name || row.filing_no || "SKU包装信息"}`)}</td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            </div>
          </div>
        `).join("")}
      ` : (monthRows.length ? `
        <div class="detail-table">
          <table>
            <thead>
              <tr>
                <th class="col-seq">序号</th>
                <th class="col-date">备案日期</th>
                <th>SKU产品名称</th>
                <th class="col-filing">备案编号</th>
                <th class="col-filer">备案人</th>
                <th class="col-link">详情页</th>
                <th class="col-package">包装信息</th>
              </tr>
            </thead>
            <tbody>
              ${monthRows.map(row => `
                <tr>
                  <td class="col-seq">${esc(row.seq)}</td>
                  <td class="col-date">${esc(row.filing_date)}</td>
                  <td>${esc(row.product_name)}</td>
                  <td class="col-filing">${esc(row.filing_no)}</td>
                  <td class="col-filer">${esc(row.filer)}</td>
                  <td class="col-link">${row.detail_url ? `<a class="icon-link" href="${esc(row.detail_url)}" target="_blank" rel="noopener noreferrer" title="打开备案详情页">${externalIcon()}</a>` : '-'}</td>
                  <td class="col-package">${packageInline([row], `${item.brand} / ${row.product_name || row.filing_no || "SKU包装信息"}`)}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      ` : `<div class="empty-box">这个品牌在 ${esc(currentPeriodKey())} 没有命中记录。</div>`);

      detailPanel.innerHTML = meta + table;
      detailPanel.querySelectorAll(".package-trigger").forEach(button => {
        button.addEventListener("click", () => {
          const label = button.dataset.packageLabel || "包装信息";
          const rows = JSON.parse(decodeURIComponent(button.dataset.packageRows || "%5B%5D"));
          const assets = packageAssets(rows);
          const content = (assets.imgs.length || assets.files.length)
            ? renderPackageSection(rows, label)
            : `<div class="package-empty">暂无产品包装信息</div>`;
          packageOverlaySub.textContent = label;
          packagePanel.innerHTML = content;
          packageOverlay.classList.add("open");
        });
      });
    }

    function refresh() {
      fillYearOptions();
      fillMonthOptions();
      renderStats();
      renderSummary();
      renderDetail();
    }

    yearSelect.addEventListener("change", (event) => {
      state.year = event.target.value || "";
      fillMonthOptions();
      refresh();
    });

    monthSelect.addEventListener("change", (event) => {
      state.month = event.target.value || "";
      refresh();
    });

    searchInput.addEventListener("input", (event) => {
      state.query = event.target.value || "";
      renderSummary();
      renderDetail();
    });

    document.querySelectorAll(".chip").forEach(chip => {
      chip.addEventListener("click", () => {
        state.filter = chip.dataset.filter;
        document.querySelectorAll(".chip").forEach(node => node.classList.remove("active"));
        chip.classList.add("active");
        renderSummary();
      });
    });

    closeDetail.addEventListener("click", () => {
      detailOverlay.classList.remove("open");
    });

    detailOverlay.addEventListener("click", (event) => {
      if (event.target === detailOverlay) {
        detailOverlay.classList.remove("open");
      }
    });

    closePackage.addEventListener("click", () => {
      packageOverlay.classList.remove("open");
    });

    packageOverlay.addEventListener("click", (event) => {
      if (event.target === packageOverlay) {
        packageOverlay.classList.remove("open");
      }
    });

    refresh();
  </script>
</body>
</html>
"""


def load_month_files() -> list[tuple[str, dict[str, Any]]]:
    records: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(MONTHLY_DIR.glob(SOURCE_GLOB)):
      if path.name == TARGET_HTML.name:
          continue
      data = json.loads(path.read_text(encoding="utf-8"))
      month = str(data.get("month", "")).strip()
      if not month:
          continue
      for item in data.get("results", []):
          item.setdefault("month_rows", [])
          if "spu_groups" not in item:
              item["spu_groups"] = group_rows_to_spu(item.get("month_rows", []))
      records.append((month, data))
    return records


def aggregate() -> dict[str, Any]:
    monthly_data = load_month_files()
    brand_set: set[str] = set()
    by_period: dict[str, dict[str, Any]] = {}
    periods: list[dict[str, str]] = []

    for month, data in monthly_data:
        year, mon = month.split("-", 1)
        periods.append({"key": month, "year": year, "month": mon})
        brand_map: dict[str, Any] = {}
        for item in data.get("results", []):
            brand = str(item.get("brand", "")).strip()
            if not brand:
                continue
            brand_set.add(brand)
            brand_map[brand] = item
        by_period[month] = brand_map

    periods.sort(key=lambda item: item["key"])
    extras = sorted(brand for brand in brand_set if brand not in ORDERED_BRANDS)
    brands = [*ORDERED_BRANDS, *extras]
    default_period = periods[-1]["key"] if periods else ""
    default_year, default_month = ("", "")
    if default_period:
        default_year, default_month = default_period.split("-", 1)

    return {
        "brands": brands,
        "periods": periods,
        "by_period": by_period,
        "default_year": default_year,
        "default_month": default_month,
    }


def build_html(data: dict[str, Any]) -> str:
    return HTML_TEMPLATE.replace("__JSON_DATA__", json.dumps(data, ensure_ascii=False))


def main() -> int:
    data = aggregate()
    html = build_html(data)
    TARGET_HTML.write_text(html, encoding="utf-8")
    if data.get("default_year") == "2026" and data.get("default_month") == "06":
        MONTH_PANEL_HTML.write_text(html, encoding="utf-8")
    print(TARGET_HTML)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
