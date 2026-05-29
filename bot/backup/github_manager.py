"""
github_manager.py — GitHub API client for backup push/pull.
Uses httpx (dependency of python-telegram-bot), no git binary needed.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


class GitHubBackupError(Exception):
    """Raised when a GitHub backup operation fails."""


class GitHubManager:
    """Manage GitHub backup files via API."""

    BACKUP_PATH_IMAGES = "backups/images.json"
    BACKUP_PATH_DATABASE = "backups/database.json"

    def __init__(self) -> None:
        self.repo = settings.GIT_BACKUP_REPO.strip()
        self.token = settings.GIT_BACKUP_TOKEN.strip()
        if not self.repo or not self.token:
            raise GitHubBackupError("GIT_BACKUP_REPO and GIT_BACKUP_TOKEN must be set")

        # Normalise various URL formats to owner/repo
        repo = self.repo
        repo = repo.replace("https://github.com/", "").replace("http://github.com/", "")
        repo = repo.replace("git@github.com:", "")
        repo = repo.removesuffix(".git").removesuffix("/")
        self.repo = repo

        if "/" not in self.repo or self.repo.count("/") != 1:
            raise GitHubBackupError(
                "GIT_BACKUP_REPO must be in 'owner/repo' format (e.g. 'username/my-repo'). "
                f"Got: '{settings.GIT_BACKUP_REPO}' → '{self.repo}'"
            )
        self.owner, self.repo_name = self.repo.split("/", 1)
        self.repo_api_url = f"https://api.github.com/repos/{self.owner}/{self.repo_name}"
        self.api_url = f"{self.repo_api_url}/contents"

    async def validate_connection(self) -> dict:
        """Check that the repo exists and the token has access.

        Returns repo info on success. Raises GitHubBackupError with a
        specific message for each failure mode.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.repo_api_url,
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github.v3+json"},
            )

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 401:
            raise GitHubBackupError(
                "GitHub token is invalid or expired. "
                "Generate a new Personal Access Token with 'repo' scope and update GIT_BACKUP_TOKEN."
            )

        if resp.status_code == 403:
            body = resp.text.lower()
            if "rate limit" in body or "rate_limit" in body:
                raise GitHubBackupError(
                    "GitHub API rate limit exceeded. Try again in a few minutes."
                )
            raise GitHubBackupError(
                "GitHub token does not have access to this repository. "
                "Make sure the token has 'repo' scope (private repos) or 'public_repo' scope (public repos)."
            )

        if resp.status_code == 404:
            raise GitHubBackupError(
                f"Repository '{self.owner}/{self.repo_name}' not found "
                f"(404). Check:\n"
                f"1. GIT_BACKUP_REPO is set to the correct 'owner/repo' name\n"
                f"2. The GitHub token has access to this repository\n"
                f"3. The repository exists and is not deleted"
            )

        raise GitHubBackupError(
            f"GitHub API error (GET repo): {resp.status_code} - {resp.text}"
        )

    async def _put_file(self, path: str, content_bytes: bytes, message: str) -> dict:
        """Create or update a file in the repo."""
        content_b64 = base64.b64encode(content_bytes).decode()
        payload = {"message": message, "content": content_b64}

        async with httpx.AsyncClient() as client:
            head_resp = await client.get(
                f"{self.api_url}/{path}",
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github.v3+json"},
            )
            if head_resp.status_code == 200:
                existing = head_resp.json()
                payload["sha"] = existing["sha"]

            resp = await client.put(
                f"{self.api_url}/{path}",
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github.v3+json"},
                json=payload,
            )

        if resp.status_code not in (200, 201):
            raise GitHubBackupError(
                f"GitHub API error (PUT {path}): {resp.status_code} - {resp.text}"
            )
        data = resp.json()
        logger.info("GitHub file updated: %s (sha: %s)", path, data["content"]["sha"])
        return data

    async def _get_file(self, path: str) -> Optional[bytes]:
        """Download a file from the repo. Returns None if not found."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_url}/{path}",
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github.v3+json"},
            )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise GitHubBackupError(
                f"GitHub API error (GET {path}): {resp.status_code} - {resp.text}"
            )
        data = resp.json()
        return base64.b64decode(data["content"])

    async def push_backup(self, images_json_bytes: bytes, db_json_bytes: bytes) -> dict:
        """Push both backup files to GitHub. Returns commit info."""
        await self.validate_connection()
        timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        msg = f"backup: auto backup {timestamp}"

        images_result = await self._put_file(
            self.BACKUP_PATH_IMAGES, images_json_bytes, msg
        )
        db_result = await self._put_file(
            self.BACKUP_PATH_DATABASE, db_json_bytes, msg
        )

        return {
            "success": True,
            "timestamp": timestamp,
            "images_sha": images_result["content"]["sha"],
            "database_sha": db_result["content"]["sha"],
            "images_url": images_result["content"]["html_url"],
            "database_url": db_result["content"]["html_url"],
        }

    async def pull_backup(self) -> Tuple[Optional[bytes], Optional[bytes]]:
        """Download both backup files from GitHub."""
        await self.validate_connection()
        images_bytes = await self._get_file(self.BACKUP_PATH_IMAGES)
        db_bytes = await self._get_file(self.BACKUP_PATH_DATABASE)
        return images_bytes, db_bytes
