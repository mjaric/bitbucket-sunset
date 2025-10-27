from __future__ import annotations

import argparse
import logging
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from .utils import read_csv, write_csv, max_perm

logger = logging.getLogger(__name__)


def expand(
    user_perm_csv: str,
    group_perm_csv: str,
    group_members_csv: str,
    output_csv: str,
    dry_run: bool = False,
) -> None:
    # Load direct user permissions
    direct: List[Dict[str, str]] = list(read_csv(user_perm_csv))

    # Load group permissions
    group_perms: List[Dict[str, str]] = list(read_csv(group_perm_csv))

    # Load group members: group -> list of {user,email}
    members_by_group: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in read_csv(group_members_csv):
        g = row.get("group", "")
        if g:
            members_by_group[g].append(row)

    # Build effective permissions per (project, repo, email)
    effective: Dict[Tuple[str, str, str], Dict[str, str]] = {}

    # Apply direct user permissions first
    for row in direct:
        email = (row.get("email") or "").strip()
        if not email:
            logger.warning("Skipping direct user row without email: %s", row)
            continue
        key = (row.get("project_key", ""), row.get("repo_slug", ""), email)
        current = effective.get(key)
        perm = row.get("permission") or ""
        prev = current.get("permission") if current else None
        new_perm = max_perm(prev, perm)
        effective[key] = {
            "project_key": key[0],
            "repo_slug": key[1],
            "email": email,
            "permission": new_perm,
            "source": "user",
            "source_principal": row.get("principal", ""),
        }

    # Apply group-derived permissions
    for row in group_perms:
        group = row.get("principal") or ""
        perm = row.get("permission") or ""
        if not group:
            continue
        members = members_by_group.get(group, [])
        if not members:
            logger.warning("Group %s has repo permissions but no members were found in group_members.csv", group)
        for m in members:
            email = (m.get("email") or "").strip()
            if not email:
                continue
            key = (row.get("project_key", ""), row.get("repo_slug", ""), email)
            current = effective.get(key)
            prev = current.get("permission") if current else None
            new_perm = max_perm(prev, perm)
            effective[key] = {
                "project_key": key[0],
                "repo_slug": key[1],
                "email": email,
                "permission": new_perm,
                "source": "group",
                "source_principal": group,
            }

    out_rows = list(effective.values())
    out_rows.sort(key=lambda r: (r["project_key"], r["repo_slug"], r["email"]))
    if dry_run:
        logger.info("Dry-run: would write %d effective permission rows", len(out_rows))
        return

    write_csv(
        output_csv,
        out_rows,
        ["project_key", "repo_slug", "email", "permission", "source", "source_principal"],
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Expand group-based Bitbucket permissions into effective per-user permissions.\n\n"
            "What it does:\n"
            "- Reads repo_user_permissions.csv (direct user permissions).\n"
            "- Reads repo_group_permissions.csv (group permissions per repo).\n"
            "- Reads group_members.csv (group → user,email).\n"
            "- Produces effective per-user repo permissions, merging sources; strongest wins.\n\n"
            "Output:\n"
            "- effective_repo_user_permissions.csv with columns: project_key,repo_slug,email,permission,source,source_principal\n\n"
            "Example:\n"
            "  uv run python -m bitbucket_sunset expand \\\n"
            "    --user-permissions out/repo_user_permissions.csv \\\n"
            "    --group-permissions out/repo_group_permissions.csv \\\n"
            "    --group-members out/group_members.csv \\\n"
            "    --output out/effective_repo_user_permissions.csv"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--user-permissions", required=True, help="Path to repo_user_permissions.csv")
    p.add_argument("--group-permissions", required=True, help="Path to repo_group_permissions.csv")
    p.add_argument("--group-members", required=True, help="Path to group_members.csv")
    p.add_argument("--output", default="out/effective_repo_user_permissions.csv", help="Output CSV path")
    p.add_argument("--dry-run", action="store_true", help="Do not write files, just log actions")
    return p


essential_fields = ["project_key", "repo_slug", "email", "permission", "source", "source_principal"]


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = build_arg_parser().parse_args(argv)
    expand(
        user_perm_csv=args.user_permissions,
        group_perm_csv=args.group_permissions,
        group_members_csv=args.group_members,
        output_csv=args.output,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
