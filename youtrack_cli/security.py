"""Security enhancements for YouTrack CLI."""

import json
import os
import re
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import keyring
from cryptography.fernet import Fernet
from keyring.errors import PasswordDeleteError
from pydantic import BaseModel, Field

from .logging import get_logger

try:  # pragma: no cover - exercised on POSIX, absent on Windows
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None  # type: ignore[assignment]

__all__ = [
    "AuditLogger",
    "CredentialManager",
    "TokenManager",
    "SecurityConfig",
    "mask_sensitive_output",
]


class SecurityConfig(BaseModel):
    """Configuration for security features."""

    enable_audit_logging: bool = Field(default=True)
    enable_credential_encryption: bool = Field(default=True)
    enable_token_expiration_warnings: bool = Field(default=True)
    enable_automatic_token_refresh: bool = Field(default=True)
    audit_log_max_entries: int = Field(default=1000)
    token_warning_days: int = Field(default=7)
    token_refresh_threshold_days: int = Field(default=3)
    max_token_refresh_attempts: int = Field(default=1)


class AuditEntry(BaseModel):
    """Represents a single audit log entry."""

    timestamp: datetime
    command: str
    arguments: list[str]
    user: str | None = None
    success: bool = True
    error_message: str | None = None


class AuditLogger:
    """Manages command audit logging."""

    def __init__(self, config: SecurityConfig | None = None, audit_file: Path | str | None = None):
        """Initialize audit logger.

        Args:
            config: Security configuration
            audit_file: Optional path of the audit journal. Defaults to the
                per-user journal under ``XDG_DATA_HOME``. Tests pass a scratch
                path here rather than reaching into the private
                ``_audit_file`` attribute.
        """
        self.config = config or SecurityConfig()
        self.logger = get_logger("youtrack_cli.security.audit")
        if audit_file is None:
            self._audit_file = self._get_audit_file_path()
        else:
            self._audit_file = Path(audit_file)
            self._audit_file.parent.mkdir(parents=True, exist_ok=True)

    def _get_audit_file_path(self) -> Path:
        """Get the audit log file path."""
        data_home = os.environ.get("XDG_DATA_HOME")
        if data_home:
            audit_dir = Path(data_home) / "youtrack-cli"
        else:
            audit_dir = Path.home() / ".local" / "share" / "youtrack-cli"

        audit_dir.mkdir(parents=True, exist_ok=True)
        return audit_dir / "audit.log"

    @property
    def _lock_file(self) -> Path:
        """Path of the writer lock file.

        The lock lives on its own inode on purpose. Publishing the journal
        with ``os.replace`` retires the journal's inode, so a lock held on
        the journal itself would end up held on a file that is no longer the
        journal, and a second writer would take a lock nobody else can see.
        """
        return self._audit_file.with_name(f"{self._audit_file.name}.lock")

    @contextmanager
    def _writer_lock(self) -> Iterator[None]:
        """Serialise writers with an exclusive lock on the lock file.

        The journal is written by a read-modify-write, which is a lost-update
        race that an atomic publish does not fix: two writers can both read
        the same snapshot and the last publish wins. This lock closes that
        window.

        A journal failure must never fail the command, so a lock that cannot
        be created or taken is reported and the write proceeds without it --
        degraded (concurrent writers may lose entries) but not broken. The
        tolerant read and the atomic publish still apply in that case; only
        the writer serialisation is lost.
        """
        if fcntl is None:
            self.logger.warning(
                "Audit journal writer lock unavailable on this platform; concurrent writers may lose entries"
            )
            yield
            return

        lock_path = self._lock_file
        fd: int | None = None
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
        except OSError as e:
            self.logger.warning(
                "Audit journal writer lock unavailable; concurrent writers may lose entries",
                error=str(e),
            )
            if fd is not None:
                os.close(fd)
                fd = None

        try:
            yield
        finally:
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(fd)

    def log_command(
        self,
        command: str,
        arguments: list[str],
        user: str | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """Log a command execution.

        Args:
            command: The command that was executed
            arguments: Command arguments (sensitive data will be masked)
            user: Username if available
            success: Whether the command succeeded
            error_message: Error message if command failed
        """
        if not self.config.enable_audit_logging:
            return

        # Mask sensitive arguments
        masked_args = self._mask_sensitive_args(arguments)

        entry = AuditEntry(
            timestamp=datetime.now(),
            command=command,
            arguments=masked_args,
            user=user,
            success=success,
            error_message=error_message,
        )

        self._write_audit_entry(entry)
        self.logger.info(
            "Command executed",
            command=command,
            user=user,
            success=success,
        )

    def _mask_sensitive_args(self, arguments: list[str]) -> list[str]:
        """Mask sensitive information in command arguments."""
        sensitive_patterns = [
            r"--token=\S+",
            r"--password=\S+",
            r"--api-key=\S+",
        ]

        masked_args = []
        for arg in arguments:
            masked_arg = arg
            for pattern in sensitive_patterns:
                masked_arg = re.sub(pattern, "--***MASKED***", masked_arg, flags=re.IGNORECASE)
            masked_args.append(masked_arg)

        return masked_args

    def _write_audit_entry(self, entry: AuditEntry) -> None:
        """Write an audit entry to the log file.

        The read-modify-write runs under the writer lock and publishes
        atomically, so a concurrent writer cannot lose this entry and a
        concurrent reader never sees a half-written journal.
        """
        try:
            with self._writer_lock():
                # Read existing entries
                entries = self._read_audit_entries()

                # Add new entry
                entries.append(entry.model_dump(mode="json", serialize_as_any=True))

                # Keep only the most recent entries
                if len(entries) > self.config.audit_log_max_entries:
                    entries = entries[-self.config.audit_log_max_entries :]

                # Publish the new journal
                self._publish(entries)

        except Exception as e:
            self.logger.error("Failed to write audit entry", error=str(e))

    def _publish(self, entries: list[dict[str, Any]]) -> None:
        """Publish the journal atomically.

        The new journal is written to a temporary file in the same directory,
        flushed and fsynced, and then moved onto the journal with
        ``os.replace``. A reader therefore sees either the complete old
        journal or the complete new one, never a partial one -- which is
        what lets the read path stay lock-free. A failed publish leaves the
        previous journal byte-identical, because the journal itself is only
        ever touched by the rename.
        """
        tmp_path = self._write_temp_file(entries)
        try:
            os.replace(tmp_path, self._audit_file)
        finally:
            # The rename consumed the temporary file; anything left is the
            # debris of a failed publish and must not accumulate.
            try:
                tmp_path.unlink()
            except OSError:
                pass

    def _write_temp_file(self, entries: list[dict[str, Any]]) -> Path:
        """Write the new journal to a temporary file beside the journal.

        The temporary file has to live in the same directory as the journal
        so that the rename that publishes it is atomic.
        """
        tmp_path = self._audit_file.with_name(f".{self._audit_file.name}.{uuid.uuid4().hex}.tmp")
        with open(tmp_path, "w") as f:
            for entry_dict in entries:
                json.dump(entry_dict, f, default=str)
                f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        self._preserve_mode(tmp_path)
        return tmp_path

    def _preserve_mode(self, tmp_path: Path) -> None:
        """Give the published journal the permissions the journal already had.

        The temporary file is created with the process umask, which is not
        necessarily the mode the journal was given by its owner.
        """
        try:
            mode = stat.S_IMODE(self._audit_file.stat().st_mode)
        except OSError:
            return
        try:
            os.chmod(tmp_path, mode)
        except OSError:
            pass

    def _read_audit_entries(self) -> list[dict[str, Any]]:
        """Read existing audit entries from file."""
        entries, _ = self._read_journal()
        return entries

    def _read_journal(self) -> tuple[list[dict[str, Any]], int]:
        """Read the journal, returning its entries and the number of skipped lines.

        A malformed line is skipped and counted rather than aborting the
        read: the journal exists to keep history, so one torn line must not
        cost the entries around it. The count is reported once per read at
        WARNING -- nothing failed, the command succeeded and the journal
        recovered. An unreadable file is a different thing and stays a
        failure.
        """
        if not self._audit_file.exists():
            return [], 0

        entries: list[dict[str, Any]] = []
        skipped = 0
        try:
            # Read in binary so that a line which is not valid UTF-8 -- a
            # write torn in the middle of a multi-byte character -- is
            # skipped like any other malformed line instead of aborting the
            # whole read.
            with open(self._audit_file, "rb") as f:
                for raw_line in f:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        entries.append(json.loads(raw_line.decode("utf-8")))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        skipped += 1
        except OSError as e:
            self.logger.error("Failed to read audit entries", error=str(e))
            return entries, skipped

        if skipped:
            self.logger.warning("Skipped malformed lines in audit journal", skipped=skipped)

        return entries, skipped

    def get_audit_log(self, limit: int | None = None) -> list[AuditEntry]:
        """Get audit log entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of audit entries
        """
        entries, _ = self.get_audit_log_with_skipped(limit)
        return entries

    def get_audit_log_with_skipped(self, limit: int | None = None) -> tuple[list[AuditEntry], int]:
        """Get audit log entries and the number of malformed lines skipped.

        The count is what tells a reader that the journal is damaged: the
        entries are the history that survived, the count is the history that
        did not.

        Args:
            limit: Maximum number of entries to return

        Returns:
            Tuple of the audit entries and the number of skipped lines
        """
        entries_data, skipped = self._read_journal()
        entries = []

        for entry_data in entries_data:
            try:
                # Convert timestamp string back to datetime
                if isinstance(entry_data.get("timestamp"), str):
                    entry_data["timestamp"] = datetime.fromisoformat(entry_data["timestamp"].replace("Z", "+00:00"))
                # Validate required fields exist before creating AuditEntry
                required_fields = ["timestamp", "command", "arguments"]
                if all(key in entry_data for key in required_fields):
                    entries.append(AuditEntry(**entry_data))  # type: ignore[misc]
            except Exception as e:
                self.logger.warning("Failed to parse audit entry", error=str(e))

        if limit:
            entries = entries[-limit:]

        return entries, skipped

    def clear_audit_log(self) -> None:
        """Clear the audit journal.

        Clearing takes the same writer lock and publishes atomically: an
        in-place truncate would reintroduce exactly the tear that clearing
        is meant to remove.
        """
        with self._writer_lock():
            self._publish([])


class CredentialManager:
    """Manages encrypted credential storage."""

    KEYRING_SERVICE = "youtrack-cli"
    KEYRING_USERNAME = "default"
    ENCRYPTION_KEY_NAME = "encryption-key"

    def __init__(self, config: SecurityConfig | None = None):
        """Initialize credential manager.

        Args:
            config: Security configuration
        """
        self.config = config or SecurityConfig()
        self.logger = get_logger("youtrack_cli.security.credentials")

    def _get_encryption_key(self) -> bytes:
        """Get or create encryption key."""
        try:
            # Try to get existing key from keyring
            key_str = keyring.get_password(self.KEYRING_SERVICE, self.ENCRYPTION_KEY_NAME)
            if key_str:
                return key_str.encode()
        except Exception as e:
            self.logger.debug("Could not retrieve encryption key from keyring", error=str(e))

        # Generate new key
        key = Fernet.generate_key()

        try:
            # Store in keyring
            keyring.set_password(self.KEYRING_SERVICE, self.ENCRYPTION_KEY_NAME, key.decode())
        except Exception as e:
            self.logger.warning("Could not store encryption key in keyring", error=str(e))

        return key

    def encrypt_credential(self, value: str) -> str:
        """Encrypt a credential value.

        Args:
            value: The credential value to encrypt

        Returns:
            Encrypted credential as base64 string
        """
        if not self.config.enable_credential_encryption:
            return value

        try:
            key = self._get_encryption_key()
            fernet = Fernet(key)
            encrypted = fernet.encrypt(value.encode())
            return encrypted.decode()
        except Exception as e:
            self.logger.error("Failed to encrypt credential", error=str(e))
            return value

    def decrypt_credential(self, encrypted_value: str) -> str:
        """Decrypt a credential value.

        Args:
            encrypted_value: The encrypted credential value

        Returns:
            Decrypted credential value
        """
        if not self.config.enable_credential_encryption:
            return encrypted_value

        try:
            key = self._get_encryption_key()
            fernet = Fernet(key)
            decrypted = fernet.decrypt(encrypted_value.encode())
            return decrypted.decode()
        except Exception as e:
            self.logger.error("Failed to decrypt credential", error=str(e))
            return encrypted_value

    def store_credential(self, key: str, value: str) -> bool:
        """Store an encrypted credential in the keyring.

        Args:
            key: Credential key/identifier
            value: Credential value

        Returns:
            True if stored successfully
        """
        try:
            encrypted_value = self.encrypt_credential(value)
            keyring.set_password(self.KEYRING_SERVICE, key, encrypted_value)
            self.logger.info("Credential stored securely", key=key)
            return True
        except Exception as e:
            self.logger.error("Failed to store credential", key=key, error=str(e))
            return False

    def retrieve_credential(self, key: str) -> str | None:
        """Retrieve and decrypt a credential from the keyring.

        Args:
            key: Credential key/identifier

        Returns:
            Decrypted credential value or None if not found
        """
        try:
            encrypted_value = keyring.get_password(self.KEYRING_SERVICE, key)
            if encrypted_value:
                return self.decrypt_credential(encrypted_value)
        except Exception as e:
            self.logger.error("Failed to retrieve credential", key=key, error=str(e))

        return None

    def delete_credential(self, key: str) -> bool:
        """Delete a credential from the keyring.

        Args:
            key: Credential key/identifier

        Returns:
            True if deleted successfully
        """
        try:
            keyring.delete_password(self.KEYRING_SERVICE, key)
            self.logger.info("Credential deleted", key=key)
            return True
        except PasswordDeleteError:
            # Expected error when item doesn't exist - log as debug, not error
            self.logger.debug("Credential not found in keyring", key=key)
            return False
        except Exception as e:
            # Unexpected errors should still be logged as errors
            self.logger.error("Failed to delete credential", key=key, error=str(e))
            return False


class TokenManager:
    """Manages token expiration checking and warnings."""

    def __init__(self, config: SecurityConfig | None = None):
        """Initialize token manager.

        Args:
            config: Security configuration
        """
        self.config = config or SecurityConfig()
        self.logger = get_logger("youtrack_cli.security.tokens")

    def check_token_expiration(self, token_expiry: datetime | None) -> dict[str, Any]:
        """Check if a token is expired or expiring soon.

        Args:
            token_expiry: Token expiration datetime

        Returns:
            Dictionary with expiration status and warning message
        """
        if not self.config.enable_token_expiration_warnings or not token_expiry:
            return {"status": "unknown", "message": None}

        now = datetime.now()
        days_until_expiry = (token_expiry - now).days

        if days_until_expiry < 0:
            message = "Token has expired and needs to be renewed"
            self.logger.error("Token expired", expiry_date=token_expiry)
            return {"status": "expired", "message": message, "days": days_until_expiry}

        if days_until_expiry <= self.config.token_warning_days:
            message = f"Token expires in {days_until_expiry} days"
            self.logger.warning("Token expiring soon", days_until_expiry=days_until_expiry)
            return {"status": "expiring", "message": message, "days": days_until_expiry}

        return {"status": "valid", "message": None, "days": days_until_expiry}

    def should_refresh_token(self, token_expiry: datetime | None) -> bool:
        """Check if a token should be proactively refreshed.

        Args:
            token_expiry: Token expiration datetime

        Returns:
            True if token should be refreshed
        """
        if not self.config.enable_automatic_token_refresh or not token_expiry:
            return False

        now = datetime.now()
        days_until_expiry = (token_expiry - now).days

        return days_until_expiry <= self.config.token_refresh_threshold_days

    def is_token_renewable(self, token: str) -> bool:
        """Check if a token supports renewal based on format/type.

        Args:
            token: The API token

        Returns:
            True if token supports renewal
        """
        # YouTrack permanent tokens (format: perm-base64.base64.hash) typically don't refresh
        # Temporary tokens and JWT tokens may support refresh
        if token.startswith("perm-"):
            self.logger.debug("Permanent token detected - refresh not supported")
            return False

        # For other token formats, assume they might be refreshable
        # This would need to be enhanced based on actual YouTrack token types
        return True

    async def request_new_token(self, base_url: str, old_token: str, verify_ssl: bool = True) -> str | None:
        """Request a new token from YouTrack API.

        Args:
            base_url: YouTrack instance URL
            old_token: Current token to refresh
            verify_ssl: Whether to verify SSL certificates

        Returns:
            New token if successful, None otherwise
        """
        try:
            import httpx

            headers = {"Authorization": f"Bearer {old_token}", "Accept": "application/json"}

            client_kwargs = {"timeout": 10.0}
            if not verify_ssl:
                client_kwargs["verify"] = False

            async with httpx.AsyncClient(**client_kwargs) as client:
                # Try YouTrack's token refresh endpoint
                # Note: This endpoint may not exist in all YouTrack versions
                response = await client.post(f"{base_url.rstrip('/')}/api/auth/token/refresh", headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    new_token = data.get("token")
                    if new_token:
                        self.logger.info("Token refreshed successfully")
                        return new_token
                    else:
                        self.logger.warning("Token refresh response missing token field")
                        return None
                elif response.status_code == 404:
                    self.logger.debug("Token refresh endpoint not available")
                    return None
                else:
                    self.logger.warning(
                        "Token refresh failed", status_code=response.status_code, response_text=response.text
                    )
                    return None

        except Exception as e:
            self.logger.error("Token refresh request failed", error=str(e))
            return None

    def estimate_token_expiry(self, token: str) -> datetime | None:
        """Estimate token expiry from token format (if possible).

        Args:
            token: The API token

        Returns:
            Estimated expiry datetime or None if cannot determine
        """
        # This is a placeholder implementation
        # In practice, you'd need to decode JWT tokens or use API calls
        # to determine actual expiration dates
        self.logger.debug("Token expiry estimation not implemented for this token format")
        return None


def mask_sensitive_output(text: str) -> str:
    """Mask sensitive information in output text.

    Args:
        text: Text that may contain sensitive information

    Returns:
        Text with sensitive information masked
    """
    patterns = [
        (r"(token[\"'\s]*[=:][\"'\s]*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(password[\"'\s]*[=:][\"'\s]*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(api[_-]?key[\"'\s]*[=:][\"'\s]*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(authorization[\"'\s]*[=:][\"'\s]*)([^\s\"']+)", r"\1***MASKED***"),
        (r"(bearer\s+)([^\s]+)", r"\1***MASKED***"),
    ]

    masked_text = text
    for pattern, replacement in patterns:
        masked_text = re.sub(pattern, replacement, masked_text, flags=re.IGNORECASE)

    return masked_text
