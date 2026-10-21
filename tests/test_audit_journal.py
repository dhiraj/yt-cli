"""Tests for the audit journal.

The journal's whole value is its history: what the CLI ran, when, as whom.
These tests cover the four properties that keep that history intact when
more than one ``yt`` process is running at the same time.

* a malformed line is skipped, not fatal -- the entries around it survive;
* a repair rewrites the journal from the entries that survived, so history
  is not lost the moment a tear is noticed;
* a publish is atomic, so a reader never sees a half-written journal and a
  failed publish leaves the previous journal byte-identical;
* writers are serialised by a lock on a file of their own, so two writers
  cannot lose each other's entries.

Every test here fails against the implementation that had none of this: one
``try`` around one read loop, and one ``open(path, "w")`` to write it back.
"""

import fcntl
import json
import os
import threading
from pathlib import Path

import pytest
from click.testing import CliRunner
from structlog.testing import capture_logs

from youtrack_cli.main import main
from youtrack_cli.security import AuditLogger, SecurityConfig


def _entry(index: int) -> dict:
    """Build one well-formed journal entry."""
    return {
        "timestamp": f"2026-10-20T00:00:{index % 60:02d}.000000",
        "command": f"command{index}",
        "arguments": [f"arg{index}"],
        "user": "tester",
        "success": True,
        "error_message": None,
    }


def _write_journal(path: Path, entries: list[dict], torn_at: int | None = None) -> None:
    """Write a journal, optionally with a torn line at ``torn_at``.

    A torn line is what a half-finished write leaves behind: the beginning
    of a JSON object with no end.
    """
    lines: list[str] = []
    for index, entry in enumerate(entries):
        if index == torn_at:
            lines.append('{"timestamp": "2026-10-20T00:00:00.000000", "command": "tor')
        lines.append(json.dumps(entry))
    path.write_text("\n".join(lines) + "\n")


def _read_raw(path: Path) -> list[dict]:
    """Read a journal, insisting that every line parses."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _lock_is_held(lock_path: Path) -> bool:
    """Report whether some writer currently holds the journal's writer lock.

    ``flock`` is held per open file description, so a second description
    for the same file is refused even inside the same process. That is what
    makes this a usable probe: it answers "is a writer in the critical
    section right now?" without perturbing the writer.
    """
    if not lock_path.exists():
        return False
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


@pytest.mark.unit
class TestTolerantRead:
    """A malformed line must not cost the journal its history."""

    def test_t1_valid_entries_survive_a_corrupt_neighbour(self, tmp_path):
        """T1: three good entries around a torn line all come back.

        Kills: wrapping the read loop in one ``try`` again -- the entry
        after the torn line would then be absent, and so would the count.

        Might survive: a mutation that skips the torn line but then drops
        every entry after it. The count is asserted, not just the absence
        of an exception, so that mutation does not pass.
        """
        journal = tmp_path / "audit.log"
        _write_journal(journal, [_entry(i) for i in range(3)], torn_at=1)
        logger = AuditLogger(audit_file=journal)

        entries = logger.get_audit_log()

        assert len(entries) == 3
        assert [entry.command for entry in entries] == ["command0", "command1", "command2"]

    def test_t1b_a_line_that_is_not_utf8_is_skipped_not_fatal(self, tmp_path):
        """T1b: a line torn in the middle of a multi-byte character is skipped.

        The journal is read as bytes and decoded per line, so a write torn
        inside a multi-byte character costs that one line and not the read.

        Kills: reading the journal as text, where one undecodable byte
        aborts the whole read.
        """
        journal = tmp_path / "audit.log"
        good = json.dumps(_entry(0))
        journal.write_bytes(
            good.encode() + b"\n" + b'{"command": "\xff\xfe torn"}\n' + json.dumps(_entry(1)).encode() + b"\n"
        )
        logger = AuditLogger(audit_file=journal)

        entries = logger.get_audit_log()

        assert len(entries) == 2
        assert [entry.command for entry in entries] == ["command0", "command1"]


@pytest.mark.unit
class TestHistorySurvivesRepair:
    """The repair must not be the thing that destroys the history."""

    def test_t2_history_survives_a_repair(self, tmp_path):
        """T2: ten good entries and a torn line become eleven intact entries.

        Kills: the collapse -- reading the journal from a truncated parse
        and writing it back leaves one entry where there were ten.

        Might survive: a mutation that preserves the count but reorders the
        entries. The order is asserted as well as the count.
        """
        journal = tmp_path / "audit.log"
        _write_journal(journal, [_entry(i) for i in range(10)], torn_at=0)
        logger = AuditLogger(audit_file=journal)

        logger.log_command("newcmd", ["arg"])

        lines = journal.read_text().splitlines()
        assert len(lines) == 11
        parsed = _read_raw(journal)
        assert [entry["command"] for entry in parsed] == [f"command{i}" for i in range(10)] + ["newcmd"]


@pytest.mark.unit
class TestAtomicPublish:
    """A publish is all-or-nothing."""

    def test_t3_failed_publish_leaves_the_old_journal_intact(self, tmp_path, monkeypatch):
        """T3: a publish that cannot complete leaves the journal untouched.

        The journal is only ever touched by the rename, so a publish that
        fails before it leaves the previous journal byte-identical.

        Kills: writing the journal in place with ``open(path, "w")``, which
        truncates the journal before the first byte of the new one is
        written.

        Might survive: a mutation that omits the ``fsync``. That is a
        durability limit, not a visibility one: this test cannot see the
        difference, and the docstring says so rather than pretending
        otherwise.
        """
        journal = tmp_path / "audit.log"
        _write_journal(journal, [_entry(i) for i in range(3)])
        before = journal.read_bytes()
        logger = AuditLogger(audit_file=journal)

        def failing_replace(src, dst):
            raise OSError("publish refused")

        monkeypatch.setattr(os, "replace", failing_replace)

        logger.log_command("newcmd", ["arg"])

        assert journal.read_bytes() == before
        # The debris of a failed publish must not accumulate next to the
        # journal either.
        assert list(tmp_path.glob(".audit.log.*.tmp")) == []

    def test_t3b_the_publish_goes_through_a_rename(self, tmp_path, monkeypatch):
        """T3b: the journal is published by a rename, not written in place.

        The journal's own inode is never truncated: a reader that opened it
        keeps the file it opened, and the new journal arrives whole.

        Kills: a mutation that writes the journal in place, or that copies
        the temporary file over it.

        Might survive: a mutation that renames a temporary file built by
        some other means. What matters here is that the journal's inode is
        replaced rather than rewritten.
        """
        journal = tmp_path / "audit.log"
        logger = AuditLogger(audit_file=journal)

        calls: list[tuple[Path, Path]] = []
        real_replace = os.replace

        def recording_replace(src, dst):
            calls.append((Path(src), Path(dst)))
            return real_replace(src, dst)

        monkeypatch.setattr(os, "replace", recording_replace)

        logger.log_command("newcmd", ["arg"])

        assert len(calls) == 1
        src, dst = calls[0]
        assert dst == journal
        # The rename comes from a temporary file beside the journal, and the
        # temporary file is gone afterwards.
        assert src.parent == journal.parent
        assert not src.exists()
        assert len(_read_raw(journal)) == 1


@pytest.mark.unit
class TestWriterLock:
    """Writers are serialised by a lock on a file of their own."""

    def test_t4_the_writer_lock_is_exclusive_and_is_released(self, tmp_path):
        """T4: the writer lock refuses other writers and is given back.

        Kills: removing the lock, locking the journal's own inode instead
        of a separate lock file (the rename retires that inode, so the lock
        would be held on a file that is no longer the journal), and taking
        a shared lock rather than an exclusive one.

        Might survive: a mutation that takes the lock around the publish
        only, leaving the read outside it -- the probe would still be
        refused while the lock is held, and the lost update would need T5
        to catch it.
        """
        journal = tmp_path / "audit.log"
        logger = AuditLogger(audit_file=journal)
        lock_path = logger._lock_file

        # The lock lives on its own file, not on the journal.
        assert lock_path != journal
        assert lock_path.name == "audit.log.lock"

        with logger._writer_lock():
            # Another writer asking for the lock must be refused.
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)

            # A shared request must be refused too: the lock is exclusive.
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            finally:
                os.close(fd)

        # Once the writer is done the lock is available again.
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
    def test_t4b_an_unusable_lock_degrades_but_does_not_fail(self, tmp_path):
        """T4b: a lock that cannot be taken costs the serialisation, not the command.

        Kills: a lock failure that propagates and breaks the command.

        Might survive: a mutation that degrades silently -- the warning
        would be gone, so the count of warnings is asserted as well.
        """
        journal = tmp_path / "audit.log"
        logger = AuditLogger(audit_file=journal)
        lock_path = logger._lock_file
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("")
        lock_path.chmod(0o400)

        with capture_logs() as logs:
            logger.log_command("newcmd", ["arg"])

        errors = [entry for entry in logs if entry.get("log_level") in ("error", "critical")]
        assert not errors
        warnings = [entry for entry in logs if entry.get("log_level") == "warning"]
        assert len(warnings) == 1
        assert "lock" in warnings[0].get("event", "")
        # The entry is still recorded: only the serialisation was lost.
        assert [entry.command for entry in logger.get_audit_log()] == ["newcmd"]

    def test_t4c_a_lock_that_cannot_be_taken_degrades_but_does_not_fail(self, tmp_path, monkeypatch):
        """T4c: a lock file that opens but cannot be locked degrades too.

        The lock file can be created and opened while the filesystem
        refuses to lock it. The command must still succeed.

        Kills: a lock failure that propagates and breaks the command.
        """
        journal = tmp_path / "audit.log"
        logger = AuditLogger(audit_file=journal)

        def refusing_flock(fd, operation):
            raise OSError("locking is not supported here")

        monkeypatch.setattr("youtrack_cli.security.fcntl.flock", refusing_flock)

        with capture_logs() as logs:
            logger.log_command("newcmd", ["arg"])

        errors = [entry for entry in logs if entry.get("log_level") in ("error", "critical")]
        assert not errors
        warnings = [entry for entry in logs if entry.get("log_level") == "warning"]
        assert len(warnings) == 1
        assert "lock" in warnings[0].get("event", "")
        assert [entry.command for entry in logger.get_audit_log()] == ["newcmd"]

    def test_t4d_without_flock_the_command_still_succeeds(self, tmp_path, monkeypatch):
        """T4d: a platform without ``fcntl`` degrades to no serialisation.

        The package claims to be OS independent, and ``fcntl`` is POSIX
        only. The tolerant read and the atomic publish still apply there;
        only the writer serialisation is lost, and the command still works.

        Kills: an unguarded ``fcntl`` import, and a lock failure that
        propagates and breaks the command.
        """
        journal = tmp_path / "audit.log"
        logger = AuditLogger(audit_file=journal)

        monkeypatch.setattr("youtrack_cli.security.fcntl", None)

        with capture_logs() as logs:
            logger.log_command("newcmd", ["arg"])

        errors = [entry for entry in logs if entry.get("log_level") in ("error", "critical")]
        assert not errors
        warnings = [entry for entry in logs if entry.get("log_level") == "warning"]
        assert len(warnings) == 1
        assert "lock" in warnings[0].get("event", "")
        assert [entry.command for entry in logger.get_audit_log()] == ["newcmd"]

    def test_t5_concurrent_writers_do_not_lose_entries(self, tmp_path, monkeypatch):
        """T5: eight writers, one journal, no lost entries.

        The race window is held open inside the subject: every writer reads
        the journal before any of them publishes, which is the window a
        read-modify-write loses entries in. The barrier is only engaged
        when the implementation is *not* serialising writers -- when it is,
        the lock has already closed the window and a barrier there would
        only deadlock.

        Kills: the lost update -- with the lock gone the writers all read
        the same snapshot and the last publish wins.

        Might survive: a mutation that serialises the writers but drops an
        entry on the floor some other way; the count is what catches that.
        """
        journal = tmp_path / "audit.log"

        writers = 4
        per_writer = 8
        barrier = threading.Barrier(writers, timeout=30)
        original_read = AuditLogger._read_audit_entries

        def read_with_barrier(self):
            lock_path = getattr(self, "_lock_file", None)
            if lock_path is None or not _lock_is_held(lock_path):
                barrier.wait()
            return original_read(self)

        monkeypatch.setattr(AuditLogger, "_read_audit_entries", read_with_barrier)

        def writer(index: int) -> None:
            own = AuditLogger(audit_file=journal)
            for step in range(per_writer):
                own.log_command(f"writer{index}-{step}", ["arg"])

        threads = [threading.Thread(target=writer, args=(index,)) for index in range(writers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
            assert not thread.is_alive()

        parsed = _read_raw(journal)
        assert len(parsed) == writers * per_writer
        assert len({entry["command"] for entry in parsed}) == writers * per_writer


@pytest.mark.unit
class TestRecoveredDegradation:
    """A recovery is a warning, not an error."""

    def test_t6_a_recovered_journal_logs_a_warning_not_an_error(self, tmp_path):
        """T6: a torn line produces one warning and no error.

        Kills: restoring ``logger.error("Failed to read audit entries", ...)``
        -- the command recovered, so an error is a false alarm, and it is
        printed on stderr for every command that touches a damaged journal.

        Might survive: a mutation that warns twice, or warns without the
        count; both are asserted.
        """
        journal = tmp_path / "audit.log"
        _write_journal(journal, [_entry(i) for i in range(3)], torn_at=1)
        logger = AuditLogger(audit_file=journal)

        with capture_logs() as logs:
            logger.log_command("newcmd", ["arg"])

        errors = [entry for entry in logs if entry.get("log_level") in ("error", "critical")]
        assert not errors
        warnings = [entry for entry in logs if entry.get("log_level") == "warning"]
        assert len(warnings) == 1
        assert warnings[0].get("skipped") == 1

    def test_t6b_an_unreadable_journal_is_still_an_error(self, tmp_path, monkeypatch):
        """T6b: a journal that cannot be read at all is a genuine failure.

        The tolerant read applies to a malformed *line*. A file that cannot
        be opened is a different thing and stays an error.
        """
        journal = tmp_path / "audit.log"
        _write_journal(journal, [_entry(i) for i in range(3)])
        logger = AuditLogger(audit_file=journal)

        real_open = open

        def failing_open(path, *args, **kwargs):
            if Path(path) == journal:
                raise OSError("journal unreadable")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", failing_open)

        with capture_logs() as logs:
            entries = logger.get_audit_log()

        assert entries == []
        errors = [entry for entry in logs if entry.get("log_level") in ("error", "critical")]
        assert len(errors) == 1

    def test_t6c_a_blank_line_is_not_a_malformed_line(self, tmp_path):
        """T6c: a blank line is skipped silently, not counted as damage.

        A blank line is not a torn line: it says nothing about the journal
        being damaged, so it must not be reported as damage.
        """
        journal = tmp_path / "audit.log"
        journal.write_text(json.dumps(_entry(0)) + "\n\n" + json.dumps(_entry(1)) + "\n")
        logger = AuditLogger(audit_file=journal)

        entries, skipped = logger.get_audit_log_with_skipped()

        assert len(entries) == 2
        assert skipped == 0

    def test_t6d_an_entry_that_is_not_an_entry_is_skipped_by_the_schema(self, tmp_path):
        """T6d: a well-formed line that is not an entry is the schema layer's business.

        The two layers compose: the syntax-level tolerance here keeps the
        line, and the schema-level validation in ``get_audit_log`` is what
        rejects it. The entries around it survive either way, and the line
        is not counted as a malformed one -- it parsed.
        """
        journal = tmp_path / "audit.log"
        journal.write_text(
            json.dumps(_entry(0)) + "\n" + json.dumps({"not": "an entry"}) + "\n" + json.dumps(_entry(1)) + "\n"
        )
        logger = AuditLogger(audit_file=journal)

        entries, skipped = logger.get_audit_log_with_skipped()

        # The line parses, so it is not counted as a malformed line ...
        assert skipped == 0
        # ... but it is not an entry either, and the entries around it are.
        assert [entry.command for entry in entries] == ["command0", "command1"]

    def test_t6e_an_entry_that_cannot_be_read_is_reported_and_skipped(self, tmp_path):
        """T6e: an entry whose timestamp cannot be parsed is reported and skipped.

        The schema layer reports it -- one warning, naming the entry -- and
        the entries around it survive.
        """
        journal = tmp_path / "audit.log"
        broken = dict(_entry(1))
        broken["timestamp"] = "not-a-timestamp"
        journal.write_text(json.dumps(_entry(0)) + "\n" + json.dumps(broken) + "\n" + json.dumps(_entry(2)) + "\n")
        logger = AuditLogger(audit_file=journal)

        with capture_logs() as logs:
            entries, skipped = logger.get_audit_log_with_skipped()

        assert skipped == 0
        assert [entry.command for entry in entries] == ["command0", "command2"]
        warnings = [entry for entry in logs if entry.get("log_level") == "warning"]
        assert len(warnings) == 1

    def test_t6f_the_limit_is_applied_and_the_count_is_reported(self, tmp_path):
        """T6f: the limit and the skipped count travel together."""
        journal = tmp_path / "audit.log"
        _write_journal(journal, [_entry(i) for i in range(5)], torn_at=2)
        logger = AuditLogger(audit_file=journal)

        entries, skipped = logger.get_audit_log_with_skipped(limit=2)

        assert len(entries) == 2
        assert skipped == 1


@pytest.mark.unit
class TestReadersSeeWholeJournals:
    """A reader never sees a half-written journal."""

    def test_t7_the_reader_never_sees_a_partial_journal(self, tmp_path, monkeypatch):
        """T7: a reader looking at a journal mid-write sees a whole one.

        The writer is stopped in the middle of writing its entries, which
        is the window in which an in-place rewrite would show the reader a
        truncated journal.

        Kills: writing the journal in place instead of publishing it with
        a rename.

        Might survive: a mutation that publishes non-atomically -- copying
        the temporary file over the journal instead of renaming it. The
        reader in this test looks while the entries are being written, and
        a copy writes the journal after that window, so the partial view
        would not be caught here.
        """
        journal = tmp_path / "audit.log"
        _write_journal(journal, [_entry(i) for i in range(3)])
        logger = AuditLogger(audit_file=journal)

        first_write = threading.Event()
        reader_done = threading.Event()
        real_dump = json.dump

        def pausing_dump(obj, fp, **kwargs):
            result = real_dump(obj, fp, **kwargs)
            if not first_write.is_set():
                first_write.set()
                if not reader_done.wait(timeout=30):
                    raise RuntimeError("the reader never finished")
            return result

        monkeypatch.setattr(json, "dump", pausing_dump)

        writer = threading.Thread(target=lambda: logger.log_command("w1", ["arg"]))
        writer.start()
        try:
            assert first_write.wait(timeout=30)
            # The writer is mid-write: the journal on disk is still whole.
            seen = _read_raw(journal)
            assert len(seen) == 3
            assert [entry["command"] for entry in seen] == ["command0", "command1", "command2"]
        finally:
            reader_done.set()
            writer.join(timeout=30)

        # And after the publish the journal is whole again.
        seen = _read_raw(journal)
        assert len(seen) == 4
        assert seen[-1]["command"] == "w1"


@pytest.mark.unit
class TestClearAudit:
    """Clearing the journal is a publish like any other."""

    def test_t9_clear_audit_waits_for_the_writer_and_leaves_a_whole_journal(self, tmp_path, monkeypatch):
        """T9: ``yt security clear-audit`` is serialised with the writers.

        The clear is stopped behind a writer that is mid-write, so the clear
        can only run once the writer is done. The journal it leaves behind
        is empty -- the writer's entries were published first and the clear
        removed them.

        Kills: clearing without the lock, which truncates the journal while
        a writer is publishing and leaves the writer's entries behind.

        Might survive: a mutation that takes the lock but truncates the
        journal in place instead of publishing it; the journal would then
        be empty all the same, and only a reader looking mid-clear would
        catch it.
        """
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        journal = tmp_path / "youtrack-cli" / "audit.log"
        journal.parent.mkdir(parents=True, exist_ok=True)
        _write_journal(journal, [_entry(i) for i in range(3)])

        logger = AuditLogger(audit_file=journal)

        first_write = threading.Event()
        writer_done = threading.Event()
        real_dump = json.dump

        def pausing_dump(obj, fp, **kwargs):
            result = real_dump(obj, fp, **kwargs)
            if not first_write.is_set():
                first_write.set()
                if not writer_done.wait(timeout=30):
                    raise RuntimeError("the writer never finished")
            return result

        monkeypatch.setattr(json, "dump", pausing_dump)

        writer = threading.Thread(target=lambda: logger.log_command("w1", ["arg"]))
        writer.start()
        assert first_write.wait(timeout=30)

        cleared = threading.Event()
        result = {}

        def run_clear():
            # --secure keeps the command itself out of the journal, so the
            # clear is the only writer this test has to reason about.
            result["outcome"] = CliRunner().invoke(main, ["--secure", "security", "clear-audit", "--force"])
            cleared.set()

        clearer = threading.Thread(target=run_clear)
        clearer.start()
        try:
            # The clear must be waiting for the writer, not running beside it.
            assert not cleared.wait(timeout=0.5)
        finally:
            writer_done.set()
            writer.join(timeout=30)
            clearer.join(timeout=30)

        assert result["outcome"].exit_code == 0
        # The writer published first and the clear removed what it wrote.
        assert journal.read_text() == ""


@pytest.mark.unit
class TestTrim:
    """The cap on the journal still holds."""

    def test_t8_the_trim_still_works(self, tmp_path):
        """T8: the journal keeps the most recent entries and drops the rest.

        This is the regression guard for the trim: the publish path was
        rewritten, and the cap is the one thing it must not have lost.
        """
        config = SecurityConfig(audit_log_max_entries=3)
        logger = AuditLogger(config, audit_file=tmp_path / "audit.log")

        for index in range(5):
            logger.log_command(f"command{index}", [f"arg{index}"])

        entries = logger.get_audit_log()
        assert len(entries) == 3
        assert entries[0].command == "command2"
        assert entries[2].command == "command4"
