from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Generator, Iterable, List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class BitbucketConfig:
    base_url: str
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None  # personal access token
    verify_ssl: bool = True
    rate_limit_sleep: float = 0.0  # seconds to sleep between requests


class BitbucketDC:
    """
    Minimal Bitbucket Data Center REST client for permissions extraction.
    Uses v1.0 REST endpoints. Assumes admin-level credentials for email access.
    """

    def __init__(self, cfg: BitbucketConfig):
        if not cfg.base_url:
            raise ValueError("Bitbucket base_url is required")
        self.cfg = cfg
        self.session = requests.Session()
        if cfg.token:
            self.session.headers.update({"Authorization": f"Bearer {cfg.token}"})
        elif cfg.username and cfg.password:
            self.session.auth = (cfg.username, cfg.password)
        self.session.verify = cfg.verify_ssl
        self.session.headers.setdefault("Accept", "application/json")

        # Normalize base URL without trailing slash
        self.base = cfg.base_url.rstrip("/")

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.cfg.rate_limit_sleep:
            time.sleep(self.cfg.rate_limit_sleep)
        url = f"{self.base}{path}"
        resp = self.session.get(url, params=params)
        if resp.status_code >= 400:
            logger.error("Bitbucket GET %s failed: %s - %s", url, resp.status_code, resp.text)
            resp.raise_for_status()
        return resp.json()

    def _paginate(self, path: str, params: Optional[Dict[str, Any]] = None) -> Generator[Dict[str, Any], None, None]:
        if params is None:
            params = {}
        limit = params.get("limit", 1000)
        start = params.get("start", 0)
        while True:
            page_params = dict(params)
            page_params.update({"limit": limit, "start": start})
            data = self._get(path, page_params)
            values = data.get("values", [])
            for v in values:
                yield v
            if data.get("isLastPage", False):
                break
            next_start = data.get("nextPageStart")
            if next_start is None:
                # Fallback in case API doesn't return nextPageStart
                start += len(values)
            else:
                start = next_start

    # Projects and repos
    def iter_projects(self, project_keys: Optional[Iterable[str]] = None) -> Generator[Dict[str, Any], None, None]:
        if project_keys:
            key_set = set(project_keys)
        else:
            key_set = None
        for p in self._paginate("/rest/api/1.0/projects", params={"limit": 100}):
            if key_set and p.get("key") not in key_set:
                continue
            yield p

    def iter_repos(self, project_key: str, repo_slugs: Optional[Iterable[str]] = None) -> Generator[Dict[str, Any], None, None]:
        slug_set = set(repo_slugs) if repo_slugs else None
        for r in self._paginate(f"/rest/api/1.0/projects/{project_key}/repos", params={"limit": 100}):
            if slug_set and r.get("slug") not in slug_set:
                continue
            yield r

    # Repo permissions: users and groups
    def iter_repo_user_perms(self, project_key: str, repo_slug: str) -> Generator[Dict[str, Any], None, None]:
        path = f"/rest/api/1.0/projects/{project_key}/repos/{repo_slug}/permissions/users"
        for u in self._paginate(path, params={"limit": 100}):
            yield u

    def iter_repo_group_perms(self, project_key: str, repo_slug: str) -> Generator[Dict[str, Any], None, None]:
        path = f"/rest/api/1.0/projects/{project_key}/repos/{repo_slug}/permissions/groups"
        for g in self._paginate(path, params={"limit": 100}):
            yield g

    # Group members (global)
    def iter_group_members(self, group: str) -> Generator[Dict[str, Any], None, None]:
        # This endpoint returns user objects for group members, requires admin
        path = "/rest/api/1.0/admin/groups/more-members"
        params = {"context": group, "limit": 100}
        for u in self._paginate(path, params=params):
            yield u

    # User details (for email)
    def get_user(self, user_slug_or_name: str) -> Optional[Dict[str, Any]]:
        # Try user by slug
        try:
            return self._get(f"/rest/api/1.0/users/{user_slug_or_name}")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                # Try search endpoint as fallback
                users = list(self._paginate("/rest/api/1.0/users", params={"filter": user_slug_or_name, "limit": 50}))
                for u in users:
                    if u.get("name") == user_slug_or_name or u.get("slug") == user_slug_or_name:
                        return u
            logger.warning("Unable to fetch user details for %s: %s", user_slug_or_name, e)
            return None

    @staticmethod
    def extract_email(user_obj: Dict[str, Any]) -> Optional[str]:
        if not user_obj:
            return None
        # Common fields in Bitbucket Server/DC
        email = user_obj.get("emailAddress") or user_obj.get("email")
        return email
