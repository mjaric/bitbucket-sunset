from __future__ import annotations

import argparse
import logging
from typing import Dict, Iterable, List, Optional

from .bitbucket import BitbucketConfig, BitbucketDC
from .utils import write_csv


logger = logging.getLogger(__name__)


def extract(
    base_url: str,
    username: Optional[str],
    password: Optional[str],
    token: Optional[str],
    verify_ssl: bool,
    output_dir: str,
    project_keys: Optional[List[str]] = None,
    repo_slugs: Optional[List[str]] = None,
    rate_limit_sleep: float = 0.0,
    dry_run: bool = False,
) -> None:
    cfg = BitbucketConfig(
        base_url=base_url,
        username=username,
        password=password,
        token=token,
        verify_ssl=verify_ssl,
        rate_limit_sleep=rate_limit_sleep,
    )
    bb = BitbucketDC(cfg)

    projects = list(bb.iter_projects(project_keys))
    logger.info("Found %d projects", len(projects))

    user_rows: List[Dict[str, object]] = []
    group_rows: List[Dict[str, object]] = []
    member_rows: List[Dict[str, object]] = []

    for p in projects:
        pkey = p.get("key")
        repos = list(bb.iter_repos(pkey, repo_slugs))
        logger.info("Project %s: %d repos", pkey, len(repos))
        for r in repos:
            rslug = r.get("slug")
            # Users
            for u in bb.iter_repo_user_perms(pkey, rslug):
                # u example: { "user": {"name":"jsmith","emailAddress":"..."}, "permission": "REPO_WRITE" }
                user = u.get("user", {})
                email = BitbucketDC.extract_email(user)
                if not email:
                    # Try fetch user details if missing email
                    name_or_slug = user.get("slug") or user.get("name")
                    details = bb.get_user(name_or_slug) if name_or_slug else None
                    email = BitbucketDC.extract_email(details or {})
                row = {
                    "project_key": pkey,
                    "repo_slug": rslug,
                    "principal_type": "user",
                    "principal": user.get("name") or user.get("slug") or "",
                    "email": email or "",
                    "permission": u.get("permission"),
                }
                user_rows.append(row)
            # Groups
            for g in bb.iter_repo_group_perms(pkey, rslug):
                group = g.get("group", {})
                row = {
                    "project_key": pkey,
                    "repo_slug": rslug,
                    "principal_type": "group",
                    "principal": group.get("name") or group.get("slug") or "",
                    "permission": g.get("permission"),
                }
                group_rows.append(row)

        # Also export group members at project scope for referenced groups
    # Get unique groups from group_rows
    unique_groups = sorted({row["principal"] for row in group_rows if row.get("principal")})
    logger.info("Exporting members for %d groups", len(unique_groups))
    for gname in unique_groups:
        for m in bb.iter_group_members(gname):
            email = BitbucketDC.extract_email(m)
            if not email:
                details = bb.get_user(m.get("slug") or m.get("name")) if m else None
                email = BitbucketDC.extract_email(details or {})
            member_rows.append(
                {
                    "group": gname,
                    "user": m.get("name") or m.get("slug") or "",
                    "email": email or "",
                }
            )

    if dry_run:
        logger.info("Dry-run: would write %d user permission rows, %d group permission rows, %d group members",
                    len(user_rows), len(group_rows), len(member_rows))
        return

    write_csv(
        f"{output_dir}/repo_user_permissions.csv",
        user_rows,
        ["project_key", "repo_slug", "principal_type", "principal", "email", "permission"],
    )
    write_csv(
        f"{output_dir}/repo_group_permissions.csv",
        group_rows,
        ["project_key", "repo_slug", "principal_type", "principal", "permission"],
    )
    write_csv(
        f"{output_dir}/group_members.csv",
        member_rows,
        ["group", "user", "email"],
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Extract Bitbucket DC repo permissions to CSV files")
    p.add_argument("--base-url", required=True, help="Bitbucket DC base URL, e.g. https://bitbucket.example.com")
    auth = p.add_mutually_exclusive_group(required=True)
    auth.add_argument("--token", help="Bitbucket personal access token")
    auth.add_argument("--username", help="Bitbucket username")
    p.add_argument("--password", help="Bitbucket password (used with --username)")
    p.add_argument("--no-verify-ssl", action="store_true", help="Disable SSL verification")
    p.add_argument("--rate-limit-sleep", type=float, default=0.0, help="Sleep seconds between requests")
    p.add_argument("--output-dir", default="out", help="Directory to write CSV files")
    p.add_argument("--project", action="append", dest="projects", help="Limit to specific project keys (repeatable)")
    p.add_argument("--repo", action="append", dest="repos", help="Limit to specific repo slugs (repeatable)")
    p.add_argument("--dry-run", action="store_true", help="Do not write files, just log actions")
    return p


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = build_arg_parser().parse_args(argv)
    extract(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        token=args.token,
        verify_ssl=not args.no_verify_ssl,
        output_dir=args.output_dir,
        project_keys=args.projects,
        repo_slugs=args.repos,
        rate_limit_sleep=args.rate_limit_sleep,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
