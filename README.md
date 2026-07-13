# 国产牙膏备案追踪

这个目录用于追踪国家药监局化妆品数据查询站里的“国产牙膏备案信息”，默认关注以下品牌：

- 参半
- 笑容加
- 高露洁
- 佳洁士
- BOP
- 白惜
- 俊小白
- 冷酸灵
- 舒适达
- 好来

## 当前实现

当前稳定入口是 `toothpaste_tracker_pipeline.py`。它把月度抓取、包装续跑和总面板重建固定为同一条流程。

底层抓取仍由 `chrome_session_tracker.py` 完成，它会：

1. 连接你当前已经打开的 Chrome 标签页。
2. 复用该页已通过校验的真实浏览器会话。
3. 跳到官方 `search-result` 结果页。
4. 直接读取页面已渲染的表格结果，并驱动分页按钮翻页。
5. 只保留“上个月”日期窗口内的记录。
6. 输出 JSON、CSV 和 Markdown 汇总。

历史实验脚本已经归档到 `archive/`，日常使用只需要关注统一入口和自动化目录。

## 运行

脚本会自动拉起并定位 NMPA 工作标签页。为了避免站点校验异常，建议 Chrome 保持登录态并尽量不要在运行中关闭浏览器。

如果需要手动确认页面状态，可打开：

`https://www.nmpa.gov.cn/datasearch/home-index.html#category=hzp`

并进入 `国产牙膏备案信息` 页面。

然后运行整月抓取：

```bash
python3 toothpaste_tracker_pipeline.py run-month --month 2026-05
```

如果需要替换关注品牌，创建一个 JSON 数组文件，例如：

```json
["参半", "高露洁"]
```

然后运行：

```bash
python3 toothpaste_tracker_pipeline.py run-month --month 2026-05 --brands brands.json
```

如果整月结果已经生成，只需要补跑详情页和包装信息：

```bash
python3 toothpaste_tracker_pipeline.py resume-month --month 2026-05
```

如果只想补某几个品牌：

```bash
python3 toothpaste_tracker_pipeline.py resume-month --month 2026-05 --only-brands 冷酸灵 俊小白
```

如果只抓单个品牌，并把结果并入当月文件：

```bash
python3 toothpaste_tracker_pipeline.py single-brand --month 2026-05 --brand 参半
```

如果只想重建 HTML 面板：

```bash
python3 toothpaste_tracker_pipeline.py rebuild-panel
```

如果想顺手生成一个可直接部署到公网的静态站目录：

```bash
python3 toothpaste_tracker_pipeline.py rebuild-panel --build-site
```

## 输出

运行后会生成：

- `output/monthly/YYYY-MM_brand_latest.json`
- `output/monthly/YYYY-MM_brand_latest.csv`
- `output/monthly/YYYY-MM_brand_latest.md`
- `output/progress/YYYY-MM_brand_progress.jsonl`
- `output/brand_dashboard.html`
- `output/package_images/YYYY-MM/...`
- `site/`（执行 `--build-site` 后生成，可直接部署到 GitHub Pages / Netlify / Vercel）

## 上线到公网

当前面板是纯静态 HTML，最省事的方式就是静态托管，不需要额外后端。

### 方案 A：GitHub Pages 自动发布

仓库已预留 GitHub Pages 工作流：

- `.github/workflows/deploy-pages.yml`
- `python3 toothpaste_tracker_pipeline.py rebuild-panel --build-site`

使用方式：

1. 把当前目录初始化并推送到 GitHub 仓库。
2. 确保 `output/brand_dashboard.html` 和 `output/package_images/` 一并提交。
3. 在 GitHub 仓库里打开 `Settings -> Pages`，Source 选择 `GitHub Actions`。
4. 之后每次推送到 `main`，都会自动发布 `site/` 目录。

发布后访问地址通常是：

```text
https://<你的 GitHub 用户名>.github.io/<仓库名>/
```

### 方案 B：手动上传到其他静态托管

如果你们更习惯国内可访问性更好的平台，也可以直接上传 `site/` 目录到：

- Cloudflare Pages
- Netlify
- Vercel
- 阿里云 OSS 静态网站
- 腾讯云 COS 静态网站

核心原则只有一个：发布目录选择 `site/`。

### 推荐发布流程

每次月度数据更新后执行：

```bash
python3 toothpaste_tracker_pipeline.py rebuild-panel --build-site
```

然后：

- 如果用 GitHub Pages：直接 `git push`
- 如果用 Netlify / Vercel / OSS：上传 `site/` 目录
- `output/package_pdfs/YYYY-MM/...`
- `output/package_renders/YYYY-MM/...`

## 自动化

项目支持 macOS `launchd` 月度自动运行。

每月 1 号会自动抓取“上个月”的所有备案信息，并重建总面板。

自动化入口脚本：

```bash
./automation/run_monthly_tracker.sh
```

安装月度任务：

```bash
sh ./automation/install_launchd.sh
```

默认计划时间：

- 每月第一个工作日 12:00
- 自动抓取“上个月”的全部备案信息
- 自动重建 `output/brand_dashboard.html`

## 说明

国家药监局查询站存在较强的前端校验和反爬机制。当前稳定方案是直接复用人工已打开的 Chrome 会话，并以页面真实渲染结果为准，而不是依赖单独猜测接口返回。

当前已验证：

- 自动化新会话会被站点拦截。
- 当前 Chrome 会话里的真实页面可以被脚本接管并执行分页查询。
- 当前链路已支持详情页补全、包装 PDF/图片保存和总面板重建。
