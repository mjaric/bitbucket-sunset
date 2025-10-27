from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

logger = logging.getLogger(__name__)


PERM_ORDER = ["REPO_READ", "REPO_WRITE", "REPO_ADMIN"]
BITBUCKET_TO_GITHUB = {
    "REPO_READ": "pull",
    "REPO_WRITE": "push",
    "REPO_ADMIN": "admin",
}


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_csv(path: str, rows: Iterable[Dict[str, object]], fieldnames: Iterable[str]) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def read_csv(path: str) -> Iterable[Dict[str, str]]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {k: v for k, v in row.items()}


def max_perm(current: Optional[str], new_perm: str) -> str:
    if current is None:
        return new_perm
    try:
        return max((current, new_perm), key=lambda p: PERM_ORDER.index(p))
    except ValueError:
        # unknown permission, preserve current
        logger.warning("Unknown permission encountered: %s", new_perm)
        return current


@dataclass
class GithubTarget:
    org: str
    repo: str

    @classmethod
    def from_project_repo(cls, org: str, project_key: str, repo_slug: str) -> "GithubTarget":
        # Convention: ${PROJECT_KEY}-${REPOSITORY_SLUG}
        name = f"{project_key}-{repo_slug}"
        return cls(org=org, repo=name)
