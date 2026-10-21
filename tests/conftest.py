"""Global test configuration and fixtures."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolate_home(tmp_path_factory):
    """Redirect the home directory for the whole test session.

    The CLI derives its credential file, its themes directory and its log
    directory from the home directory, so a test that touches the default
    configuration path reads and writes the developer's real
    ``~/.config/youtrack-cli/.env``.  Pointing the home directory at a
    throwaway one keeps every one of those paths inside the test run.

    Setting ``HOME`` is not enough on its own.  Some tests wipe
    ``os.environ`` wholesale to exercise the "no environment variables"
    path, and that takes ``HOME`` with it; ``Path.home()`` then falls back
    to the password database, which is the developer's real home.  The CLI
    writes its audit journal and its log file there, so a test that clears
    the environment can append to the developer's real audit journal.  The
    home directory is therefore pinned for the whole session, so that a
    cleared environment cannot reach it.

    This completes the isolation the other fixtures in this file already
    perform for the remaining credential carriers: the environment variables
    (``isolate_environment``), the keyring (``isolate_keyring``) and the
    dotenv loading (``mock_dotenv_loading``).
    """
    home = tmp_path_factory.mktemp("home")
    original = {key: os.environ.get(key) for key in ("HOME", "USERPROFILE")}
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)

    original_home = Path.home
    original_expanduser = os.path.expanduser

    def pinned_home(cls=None):
        return Path(home)

    def pinned_expanduser(path):
        if path.startswith("~"):
            return str(home) + path[1:]
        return original_expanduser(path)

    Path.home = classmethod(pinned_home)
    os.path.expanduser = pinned_expanduser
    try:
        yield home
    finally:
        Path.home = original_home
        os.path.expanduser = original_expanduser
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="function", autouse=True)
def isolate_environment():
    """Ensure test isolation by saving and restoring environment variables."""
    # YouTrack environment variables that could cause test contamination
    youtrack_env_vars = ["YOUTRACK_BASE_URL", "YOUTRACK_TOKEN", "YOUTRACK_USERNAME", "YOUTRACK_VERIFY_SSL"]

    # XDG_DATA_HOME redirects the audit journal and the log file. The CLI
    # prefers it over the home directory, so on a machine that sets it a
    # test's AuditLogger() would write to the developer's real journal
    # instead of the throwaway home. Clear it alongside the YouTrack
    # variables so the journal follows HOME like every other path.
    data_home_vars = ["XDG_DATA_HOME"]

    # Store original values
    original_env: dict[str, str | None] = {}
    for key in youtrack_env_vars + data_home_vars:
        original_env[key] = os.environ.get(key)

    # Clear YouTrack environment variables before each test
    for key in youtrack_env_vars + data_home_vars:
        if key in os.environ:
            del os.environ[key]

    yield

    # Restore original environment after test
    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]


@pytest.fixture(scope="function", autouse=True)
def isolate_keyring():
    """Give each test a fresh, empty in-memory keyring backend.

    The keyring backend is process-wide global state that pytest does not reset
    between tests, so credentials written (or leaked) by one test could be read
    by another under randomized ordering. This mirrors ``isolate_environment``
    for the keyring and removes any dependency on the developer's real keychain.
    """
    import keyring
    from keyring.backend import KeyringBackend

    class _MemKeyring(KeyringBackend):
        priority = 1

        def __init__(self):
            super().__init__()
            self._store: dict[tuple[str, str], str] = {}

        def get_password(self, service, username):
            return self._store.get((service, username))

        def set_password(self, service, username, password):
            self._store[(service, username)] = password

        def delete_password(self, service, username):
            self._store.pop((service, username), None)

    previous = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    try:
        yield
    finally:
        keyring.set_keyring(previous)


@pytest.fixture(scope="function", autouse=True)
def mock_dotenv_loading():
    """Mock dotenv loading to prevent real config files from loading."""
    with (
        patch("youtrack_cli.auth.load_dotenv") as mock_auth_load_dotenv,
        patch("youtrack_cli.config.load_dotenv") as mock_config_load_dotenv,
    ):
        yield mock_auth_load_dotenv, mock_config_load_dotenv
