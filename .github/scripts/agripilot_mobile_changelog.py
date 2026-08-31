#!/usr/bin/env python3
"""Generate grouped release notes for AgriPilot mobile APK releases."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import OrderedDict

MOBILE_PATH = "use-cases/agri-pilot/mobile"

FEATURE_KEYWORDS = ("add", "added", "create", "implement", "feat")
BUG_KEYWORDS = ("fix", "bug", "issue")
IMPROVEMENT_KEYWORDS = ("improve", "update", "extend")

SECTION_ORDER = ("Features", "Bug fixes", "Improvements", "Other")


def run_git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def latest_tag(tag_prefix: str) -> str | None:
    output = run_git("tag", "-l", f"{tag_prefix}*", "--sort=-version:refname")
    if not output:
        return None
    return output.splitlines()[0]


def commit_subjects(since_tag: str | None) -> list[str]:
    log_range = f"{since_tag}..HEAD" if since_tag else "HEAD"
    output = run_git(
        "log",
        log_range,
        "--pretty=format:%s",
        "--",
        MOBILE_PATH,
    )
    if not output:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def categorize(subject: str) -> str:
    lower = subject.lower()
    if any(keyword in lower for keyword in FEATURE_KEYWORDS):
        return "Features"
    if any(keyword in lower for keyword in BUG_KEYWORDS):
        return "Bug fixes"
    if any(keyword in lower for keyword in IMPROVEMENT_KEYWORDS):
        return "Improvements"
    return "Other"


def clean_subject(subject: str) -> str:
    text = subject.strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    if text.endswith("."):
        text = text[:-1]
    return text


def group_subjects(subjects: list[str]) -> OrderedDict[str, list[str]]:
    grouped: OrderedDict[str, list[str]] = OrderedDict((section, []) for section in SECTION_ORDER)
    seen: set[str] = set()

    for subject in subjects:
        cleaned = clean_subject(subject)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        grouped[categorize(subject)].append(cleaned)

    return grouped


def render_notes(
    version: str,
    api_base_url: str,
    apk_name: str,
    grouped: OrderedDict[str, list[str]],
    since_tag: str | None,
) -> str:
    lines = [
        f"## AgriPilot Mobile {version}",
        "",
        f"Release APK targeting `{api_base_url}`.",
        "",
    ]

    has_changes = any(grouped[section] for section in SECTION_ORDER)
    if has_changes:
        for section in SECTION_ORDER:
            items = grouped[section]
            if not items:
                continue
            lines.append(f"### {section}")
            lines.extend(f"- {item}" for item in items)
            lines.append("")
    else:
        lines.extend(
            [
                "### Changes",
                "",
                "_No mobile commits since the previous release tag._",
                "",
            ]
        )

    if since_tag:
        lines.extend([f"_Commits since `{since_tag}`._", ""])

    lines.extend(
        [
            "### Notes",
            "",
            "_Edit this draft before publishing._",
            "",
            "---",
            f"Install: download `{apk_name}` from Assets below (sideload; allow unknown sources).",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AgriPilot mobile release notes")
    parser.add_argument("--tag-prefix", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--apk-name", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    since_tag = latest_tag(args.tag_prefix)
    subjects = commit_subjects(since_tag)
    grouped = group_subjects(subjects)
    notes = render_notes(args.version, args.api_base_url, args.apk_name, grouped, since_tag)

    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(notes)

    return 0


if __name__ == "__main__":
    sys.exit(main())
