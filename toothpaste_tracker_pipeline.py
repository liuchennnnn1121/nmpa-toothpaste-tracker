from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable or "python3"


def run_step(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="国产牙膏备案追踪统一入口：抓取月度结果、续跑包装信息、重建总面板。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_month = subparsers.add_parser(
        "run-month",
        help="使用当前 Chrome 会话抓取指定月份的品牌结果与包装信息，并重建面板。",
    )
    run_month.add_argument("--month", required=True, help="目标月份，格式 YYYY-MM。")
    run_month.add_argument("--brands", help="品牌 JSON 文件路径，默认使用仓库内置品牌。")
    run_month.add_argument("--settle-seconds", type=float, default=3.0, help="结果页跳转等待秒数。")
    run_month.add_argument("--skip-panel", action="store_true", help="完成抓取后不重建 HTML 面板。")
    run_month.add_argument("--build-site", action="store_true", help="完成后额外生成可部署静态站目录。")

    resume_month = subparsers.add_parser(
        "resume-month",
        help="基于现有月度 JSON 续跑详情和包装信息，并重建面板。",
    )
    resume_month.add_argument("--month", required=True, help="目标月份，格式 YYYY-MM。")
    resume_month.add_argument("--settle-seconds", type=float, default=3.0, help="页面跳转等待秒数。")
    resume_month.add_argument(
        "--only-brands",
        nargs="*",
        help="只续跑指定品牌；不传则续跑当前月文件中的全部品牌。",
    )
    resume_month.add_argument("--skip-panel", action="store_true", help="完成续跑后不重建 HTML 面板。")
    resume_month.add_argument("--build-site", action="store_true", help="完成后额外生成可部署静态站目录。")

    single_brand = subparsers.add_parser(
        "single-brand",
        help="仅抓取一个品牌并追加进度文件，再重建月度文件与总面板。",
    )
    single_brand.add_argument("--month", required=True, help="目标月份，格式 YYYY-MM。")
    single_brand.add_argument("--brand", required=True, help="品牌名。")
    single_brand.add_argument("--brands", help="品牌 JSON 文件路径，默认使用仓库内置品牌。")
    single_brand.add_argument("--settle-seconds", type=float, default=3.0, help="页面跳转等待秒数。")
    single_brand.add_argument("--skip-panel", action="store_true", help="完成后不重建 HTML 面板。")
    single_brand.add_argument("--build-site", action="store_true", help="完成后额外生成可部署静态站目录。")

    rebuild = subparsers.add_parser(
        "rebuild-panel",
        help="仅根据 output 目录中的月度 JSON 重建 HTML 总面板。",
    )
    rebuild.add_argument("--build-site", action="store_true", help="重建面板后额外生成可部署静态站目录。")
    return parser


def maybe_build_site(build_site: bool) -> None:
    if not build_site:
        return
    run_step([PYTHON, "prepare_site.py"])


def maybe_build_panel(skip_panel: bool, build_site: bool) -> None:
    if skip_panel:
        return
    run_step([PYTHON, "build_panel.py"])
    maybe_build_site(build_site)


def command_run_month(args: argparse.Namespace) -> None:
    cmd = [PYTHON, "chrome_session_tracker.py", "--month", args.month, "--settle-seconds", str(args.settle_seconds)]
    if args.brands:
        cmd.extend(["--brands", args.brands])
    run_step(cmd)
    maybe_build_panel(args.skip_panel, args.build_site)


def command_resume_month(args: argparse.Namespace) -> None:
    cmd = [
        PYTHON,
        "chrome_session_tracker.py",
        "--month",
        args.month,
        "--settle-seconds",
        str(args.settle_seconds),
        "--enrich-existing-month",
    ]
    if args.only_brands:
        cmd.append("--only-brands")
        cmd.extend(args.only_brands)
    run_step(cmd)
    maybe_build_panel(args.skip_panel, args.build_site)


def command_single_brand(args: argparse.Namespace) -> None:
    cmd = [
        PYTHON,
        "chrome_session_tracker.py",
        "--month",
        args.month,
        "--settle-seconds",
        str(args.settle_seconds),
        "--single-brand",
        args.brand,
    ]
    if args.brands:
        cmd.extend(["--brands", args.brands])
    run_step(cmd)
    rebuild_cmd = [PYTHON, "chrome_session_tracker.py", "--month", args.month, "--build-from-progress"]
    if args.brands:
        rebuild_cmd.extend(["--brands", args.brands])
    run_step(rebuild_cmd)
    maybe_build_panel(args.skip_panel, args.build_site)


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "run-month":
        command_run_month(args)
    elif args.command == "resume-month":
        command_resume_month(args)
    elif args.command == "single-brand":
        command_single_brand(args)
    elif args.command == "rebuild-panel":
        run_step([PYTHON, "build_panel.py"])
        maybe_build_site(args.build_site)
    else:
        raise ValueError(f"unsupported command: {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
