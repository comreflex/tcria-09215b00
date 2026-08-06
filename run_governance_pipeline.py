#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional

from tcria.adapters.quinta_ordem_adapter import QuintaOrdemAdapter
from tcria.engine import TCRIAEngine
from tcria.reporting.quinta_ordem_markdown import QuintaOrdemMarkdownReporter


def run_cmd(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
    )
    if cp.returncode != 0:
        print(cp.stdout, end="")
        print(cp.stderr, end="", file=sys.stderr)
        raise SystemExit(cp.returncode)
    return cp


def default_review_paths(audit_json: Path) -> tuple[Path, Path]:
    stem = audit_json.stem
    parent = audit_json.parent
    return (
        parent / f"{stem}_blocked_artifacts_review.json",
        parent / f"{stem}_blocked_artifacts_review.md",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run official audit and complementary blocked-artifact review as a two-layer governance pipeline."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root where scripts are located.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/audit",
        help="Output directory for official audit artifacts in modular engine mode.",
    )
    parser.add_argument(
        "--audit-script",
        default="audit_accusation_bundle_with_tcr_gateway.py",
        help="Path (relative to repo root) for official audit script (legacy mode).",
    )
    parser.add_argument(
        "--legacy-audit-script",
        action="store_true",
        help="Use the legacy audit script instead of the modular TCRIA engine.",
    )
    parser.add_argument(
        "--review-script",
        default="generate_blocked_artifacts_review.py",
        help="Path (relative to repo root) for complementary blocked review script.",
    )
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        help="Input file or directory for official audit (repeatable).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Run official audit in strict mode.",
    )
    parser.add_argument(
        "--output-stem",
        default=None,
        help="Output stem passed to official audit script.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Maximum number of supported files to scan.",
    )
    parser.add_argument(
        "--max-total-bytes",
        type=int,
        default=None,
        help="Maximum total bytes across scanned files.",
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Skip official audit and run only blocked review using --audit-json.",
    )
    parser.add_argument(
        "--audit-json",
        default=None,
        help="Existing audit JSON path (required when --skip-audit).",
    )
    parser.add_argument(
        "--review-json-out",
        default=None,
        help="Output path for blocked review JSON.",
    )
    parser.add_argument(
        "--review-md-out",
        default=None,
        help="Output path for blocked review Markdown.",
    )
    parser.add_argument(
        "--quinta-ordem-json-out",
        default=None,
        help="Output path for Quinta Ordem ExecutionContext JSON export.",
    )
    parser.add_argument(
        "--quinta-ordem-md-out",
        default=None,
        help="Output path for Quinta Ordem Markdown report (for Precision Gate).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()

    audit_script = (repo_root / args.audit_script).resolve()
    review_script = (repo_root / args.review_script).resolve()
    if not review_script.exists():
        raise SystemExit(f"Review script not found: {review_script}")

    audit_json: Optional[Path] = None
    audit_md: Optional[Path] = None

    if args.skip_audit:
        if not args.audit_json:
            raise SystemExit("--audit-json is required when --skip-audit is used.")
        audit_json = Path(args.audit_json).expanduser().resolve()
        if not audit_json.exists():
            raise SystemExit(f"Audit JSON not found: {audit_json}")
        print(f"[pipeline] Official audit skipped. Using: {audit_json}")
    else:
        if not args.paths:
            raise SystemExit("At least one --path is required unless --skip-audit is used.")
        print("[pipeline] Running official audit...")
        if args.legacy_audit_script:
            if not audit_script.exists():
                raise SystemExit(f"Audit script not found: {audit_script}")
            audit_cmd = [sys.executable, str(audit_script)]
            if args.strict:
                audit_cmd.append("--strict")
            if args.output_stem:
                audit_cmd.extend(["--output-stem", args.output_stem])
            for p in args.paths or []:
                audit_cmd.extend(["--path", p])

            audit_cp = run_cmd(audit_cmd, cwd=repo_root)
            print(audit_cp.stdout, end="")

            marker = "JSON report:"
            for line in (audit_cp.stdout or "").splitlines():
                if line.startswith(marker):
                    audit_json = Path(line.split(marker, 1)[1].strip()).expanduser().resolve()
                    break
            if not audit_json:
                raise SystemExit("Could not detect official audit JSON path from legacy command output.")
            audit_md = audit_json.with_suffix(".md")
        else:
            engine = TCRIAEngine(repo_root=repo_root)
            stem = args.output_stem or "tcr_gateway_accusation_bundle_audit"
            try:
                result = engine.run_audit(
                    input_paths=args.paths,
                    strict=args.strict,
                    out_dir=(repo_root / args.output_dir).resolve(),
                    output_stem=stem,
                    include_pdf=True,
                    max_files=args.max_files,
                    max_total_bytes=args.max_total_bytes,
                )
            except Exception as exc:
                raise SystemExit(f"Official modular audit failed: {exc}") from exc
            audit_json = Path(result["artifacts"]["json"]).expanduser().resolve()
            audit_md = Path(result["artifacts"]["markdown"]).expanduser().resolve()
            print(f"Mode: {'strict-explicit-decision-record' if args.strict else 'default-heuristic'}")
            print(f"JSON report: {audit_json}")
            print(f"Markdown report: {audit_md}")
            print(f"Total scanned: {result['bundle']['total_files_scanned']}")
            print(f"Accusation set: {result['bundle']['accusation_set_count']}")

        if not audit_json.exists():
            raise SystemExit(f"Official audit JSON was reported but not found: {audit_json}")

    review_json_out: Path
    review_md_out: Path
    if args.review_json_out or args.review_md_out:
        review_json_out = Path(args.review_json_out).expanduser().resolve() if args.review_json_out else default_review_paths(audit_json)[0]
        review_md_out = Path(args.review_md_out).expanduser().resolve() if args.review_md_out else default_review_paths(audit_json)[1]
    else:
        review_json_out, review_md_out = default_review_paths(audit_json)

    review_json_out.parent.mkdir(parents=True, exist_ok=True)
    review_md_out.parent.mkdir(parents=True, exist_ok=True)

    print("[pipeline] Running complementary blocked review...")
    review_cmd = [
        sys.executable,
        str(review_script),
        str(audit_json),
        "--json-out",
        str(review_json_out),
        "--md-out",
        str(review_md_out),
    ]
    review_cp = run_cmd(review_cmd, cwd=repo_root)
    print(review_cp.stdout, end="")

    print("[pipeline] Completed")
    print(f"[pipeline] Official audit JSON: {audit_json}")
    if audit_md:
        print(f"[pipeline] Official audit MD: {audit_md}")
    print(f"[pipeline] Blocked review JSON: {review_json_out}")
    print(f"[pipeline] Blocked review MD: {review_md_out}")
    print(
        "[pipeline] Guardrails: complementary-only diagnostics; official outcomes are preserved and not promoted by this layer."
    )

    # -- Quinta Ordem ExecutionContext export (optional) --
    quinta_json_out: Optional[Path] = None
    quinta_md_out: Optional[Path] = None
    if args.quinta_ordem_json_out or args.quinta_ordem_md_out:
        stem = audit_json.stem
        quinta_json_out = (
            Path(args.quinta_ordem_json_out).expanduser().resolve()
            if args.quinta_ordem_json_out
            else audit_json.parent / f"{stem}_quinta_ordem_context.json"
        )
        quinta_md_out = (
            Path(args.quinta_ordem_md_out).expanduser().resolve()
            if args.quinta_ordem_md_out
            else audit_json.parent / f"{stem}_quinta_ordem_report.md"
        )

        print("[pipeline] Generating Quinta Ordem ExecutionContext...")
        adapter = QuintaOrdemAdapter()
        ctx = adapter.from_bundle_json(audit_json)

        quinta_json_out.parent.mkdir(parents=True, exist_ok=True)
        quinta_json_out.write_text(ctx.to_json(), encoding="utf-8")
        print(f"[pipeline] Quinta Ordem JSON: {quinta_json_out}")

        quinta_md_out.parent.mkdir(parents=True, exist_ok=True)
        reporter = QuintaOrdemMarkdownReporter()
        quinta_md_out.write_text(reporter.generate(ctx), encoding="utf-8")
        print(f"[pipeline] Quinta Ordem MD: {quinta_md_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
