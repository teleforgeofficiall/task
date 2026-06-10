"""
manager.py — MySQL backup and restore manager.

Uses mysqldump for backup and mysql client for restore.
Backups are stored as compressed .sql.gz files in the configured BACKUP_DIR.
"""
from __future__ import annotations

import asyncio
import gzip
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from bot.database.session import get_database_url
from config.settings import settings

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class BackupError(Exception):
    """Raised when a backup or restore operation fails."""


def _parse_db_url(url: str) -> dict:
    """Parse a MySQL connection string into components."""
    url = url.replace("mysql+aiomysql://", "mysql://", 1)
    url = url.replace("mysql://", "", 1)
    parts = url.split("@")
    user_pass = parts[0].split(":")
    host_port_db = parts[1].split("/")
    host_port = host_port_db[0].split(":")
    return {
        "username": user_pass[0],
        "password": user_pass[1] if len(user_pass) > 1 else "",
        "host": host_port[0],
        "port": host_port[1] if len(host_port) > 1 else "3306",
        "database": host_port_db[1] if len(host_port_db) > 1 else settings.DB_NAME,
    }


class BackupManager:
    """Handles MySQL backup creation, restoration, and listing."""

    def __init__(self) -> None:
        self.backup_dir = Path(settings.BACKUP_DIR)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _get_mysql_env(self) -> tuple[dict, dict]:
        """Build environment dict with MYSQL_PWD for mysqldump/mysql."""
        db_url = get_database_url()
        info = _parse_db_url(db_url)
        env = os.environ.copy()
        env["MYSQL_PWD"] = info["password"]
        return env, info

    async def create_backup(self, notes: str = "") -> dict:
        """
        Create a full MySQL backup using mysqldump.
        Returns dict with filename, size, and path.
        """
        env, info = self._get_mysql_env()
        timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
        filename = f"taskhub_backup_{timestamp}.sql.gz"
        filepath = self.backup_dir / filename

        logger.info("Creating backup: %s", filename)

        try:
            cmd = [
                "mysqldump",
                f"--host={info['host']}",
                f"--port={info['port']}",
                f"--user={info['username']}",
                "--single-transaction",
                "--routines",
                "--triggers",
                "--no-create-db",
                "--skip-extended-insert",
                info["database"],
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise BackupError(f"mysqldump failed: {stderr.decode(errors='replace')}")

            # Compress the output
            with gzip.open(filepath, "wb") as f:
                f.write(stdout)

            file_size = filepath.stat().st_size
            logger.info("Backup created: %s (%d bytes)", filename, file_size)

            return {
                "filename": filename,
                "filepath": str(filepath),
                "file_size_bytes": file_size,
                "notes": notes,
                "created_at": datetime.now(IST).isoformat(),
            }

        except FileNotFoundError:
            raise BackupError(
                "mysqldump not found. Install MySQL client tools on the server."
            )
        except Exception as exc:
            raise BackupError(f"Backup failed: {exc}")

    async def restore_backup(self, filepath: str) -> dict:
        """
        Restore a MySQL backup from a .sql.gz file.
        WARNING: This will DROP and recreate the database.
        """
        path = Path(filepath)
        if not path.exists():
            raise BackupError(f"Backup file not found: {filepath}")

        env, info = self._get_mysql_env()
        logger.warning("RESTORING DATABASE FROM: %s", filepath)

        try:
            # Decompress the backup
            with gzip.open(path, "rb") as f:
                sql_data = f.read()

            # Run mysql client to restore
            cmd = [
                "mysql",
                f"--host={info['host']}",
                f"--port={info['port']}",
                f"--user={info['username']}",
                info["database"],
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await process.communicate(input=sql_data)

            if process.returncode != 0:
                raise BackupError(f"Restore failed: {stderr.decode(errors='replace')}")

            logger.info("Database restored successfully from %s", filepath)
            return {
                "success": True,
                "message": f"Database restored from {path.name}",
            }

        except FileNotFoundError:
            raise BackupError(
                "mysql client not found. Install MySQL client tools on the server."
            )
        except Exception as exc:
            raise BackupError(f"Restore failed: {exc}")

    async def list_backups(self) -> list:
        """List all available backup files sorted by date (newest first)."""
        backups = []
        for f in sorted(self.backup_dir.glob("taskhub_backup_*.sql.gz"), reverse=True):
            stat = f.stat()
            backups.append({
                "filename": f.name,
                "filepath": str(f),
                "file_size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=IST).isoformat(),
            })
        return backups

    async def delete_backup(self, filename: str) -> bool:
        """Delete a specific backup file."""
        filepath = self.backup_dir / filename
        if filepath.exists():
            filepath.unlink()
            logger.info("Deleted backup: %s", filename)
            return True
        return False

    async def cleanup_old_backups(self) -> int:
        """Remove backups older than BACKUP_RETENTION_DAYS. Returns count deleted."""
        cutoff = datetime.now(IST).timestamp() - (settings.BACKUP_RETENTION_DAYS * 86400)
        deleted = 0
        for f in self.backup_dir.glob("taskhub_backup_*.sql.gz"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        if deleted:
            logger.info("Cleaned up %d old backup(s)", deleted)
        return deleted

    async def get_backup_size_total(self) -> int:
        """Total size of all backup files in bytes."""
        total = 0
        for f in self.backup_dir.glob("taskhub_backup_*.sql.gz"):
            total += f.stat().st_size
        return total
