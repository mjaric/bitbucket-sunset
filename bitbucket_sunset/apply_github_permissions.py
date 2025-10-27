from __future__ import annotations

import argparse
import logging
from typing import Dict, Iterable, List, Optional

from github import Github, GithubException

from .utils import BITBUCKET_TO_GITHUB, GithubTarget, read_csv

logger = logging.getLogger(__name__)


def load_email_to_login(mapping_csv: Optional[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not mapping_csv:
        return mapping
    for row in read_csv(mapping_csv):
        email = (row.get("email") or "").strip().lower()
        login = (row.get("github_login") or "").strip()
        if email and login:
            mapping[email] = login
    return mapping


def apply_permissions(
    github_token: str,
    org: str,
    effective_csv: str,
    mapping_csv: Optional[str] = None,
    default_missing: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """
    Apply repo permissions in GitHub based on effective per-user permissions CSV.

    Parameters:
    - github_token: GitHub token with admin:org and repo scopes (for org-owned repos)
    - org: target organization
    - effective_csv: CSV produced by expand_groups with columns project_key,repo_slug,email,permission
    - mapping_csv: optional CSV mapping email -> github_login
    - default_missing: optional default GitHub login to use when email is not in mapping (e.g., a fallback service account); if not provided, such rows are skipped with a warning.
    - dry_run: if True, no changes are made, only logs
    """
    gh = Github(github_token)
    email_to_login = load_email_to_login(mapping_csv)

    rows = list(read_csv(effective_csv))
    logger.info("Loaded %d effective permission rows", len(rows))

    # Group rows by target repo
    by_repo: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        project_key = r.get("project_key", "")
        repo_slug = r.get("repo_slug", "")
        tgt = GithubTarget.from_project_repo(org, project_key, repo_slug)
        full = f"{tgt.org}/{tgt.repo}"
        by_repo.setdefault(full, []).append(r)

    for full_name, entries in sorted(by_repo.items()):
        logger.info("Processing repo %s with %d entries", full_name, len(entries))
        try:
            repo = gh.get_repo(full_name)
        except GithubException as e:
            logger.error("Cannot access repo %s: %s", full_name, e)
            continue

        for e in entries:
            email = (e.get("email") or "").strip().lower()
            bb_perm = e.get("permission") or "REPO_READ"
            gh_perm = BITBUCKET_TO_GITHUB.get(bb_perm)
            if not gh_perm:
                logger.warning("Unknown Bitbucket permission %s for %s; skipping", bb_perm, email)
                continue

            login = email_to_login.get(email)
            if not login:
                if default_missing:
                    login = default_missing
                    logger.warning("No mapping for %s; using default login %s", email, login)
                else:
                    logger.warning("No mapping for %s; skipping", email)
                    continue

            # Check current permission to avoid redundant calls
            needs_update = True
            current_perm = None
            try:
                current_perm = repo.get_collaborator_permission(login)
                # get_collaborator_permission returns 'admin','write','read' or None
                if current_perm:
                    # Map to our three levels
                    norm = {
                        "admin": "admin",
                        "write": "push",
                        "triage": "triage",
                        "maintain": "maintain",
                        "read": "pull",
                    }.get(current_perm, current_perm)
                    if norm == gh_perm:
                        needs_update = False
            except GithubException:
                # User not a collaborator yet
                pass

            if not needs_update:
                logger.info("%s already has %s on %s", login, gh_perm, full_name)
                continue

            if dry_run:
                logger.info("Dry-run: would add/update %s on %s with %s (from %s)", login, full_name, gh_perm, email)
                continue

            try:
                repo.add_to_collaborators(login, permission=gh_perm)
                logger.info("Granted %s to %s on %s", gh_perm, login, full_name)
            except GithubException as ge:
                logger.error("Failed to add %s to %s with %s: %s", login, full_name, gh_perm, ge)
                continue


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Apply effective per-user permissions to GitHub repositories.\n\n"
            "What it does:\n"
            "- Reads effective_repo_user_permissions.csv produced by the expand step.\n"
            "- Resolves user emails to GitHub logins using a mapping CSV.\n"
            "- Grants 'pull', 'push', or 'admin' on repos named ORG/${PROJECT_KEY}-${REPO_SLUG}.\n"
            "- Skips users without a mapping unless --default-missing is provided.\n\n"
            "Example:\n"
            "  uv run python -m bitbucket_sunset apply \\\n"
            "    --token $GH_TOKEN --org your-org \\\n"
            "    --effective-csv out/effective_repo_user_permissions.csv \\\n"
            "    --mapping-csv email_github_login.csv --dry-run"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--token", dest="github_token", required=True, help="GitHub token with admin rights")
    p.add_argument("--org", required=True, help="Target GitHub organization")
    p.add_argument("--effective-csv", default="out/effective_repo_user_permissions.csv", help="Effective CSV path")
    p.add_argument("--mapping-csv", help="CSV mapping: email,github_login")
    p.add_argument("--default-missing", help="Default github login if email not found in mapping (optional)")
    p.add_argument("--dry-run", action="store_true", help="Do not make changes, only log")
    return p


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = build_arg_parser().parse_args(argv)
    apply_permissions(
        github_token=args.github_token,
        org=args.org,
        effective_csv=args.effective_csv,
        mapping_csv=args.mapping_csv,
        default_missing=args.default_missing,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
