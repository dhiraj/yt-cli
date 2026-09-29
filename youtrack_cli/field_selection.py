"""Field selection optimization for YouTrack API calls.

This module provides utilities for dynamic field selection to optimize API performance
by only requesting needed fields based on the command context and user preferences.
"""

from __future__ import annotations

from .logging import get_logger

__all__ = [
    "FieldProfile",
    "FieldSelector",
    "get_field_selector",
    "FIELD_PROFILES",
    "parse_field_expression",
    "find_missing_fields",
]

logger = get_logger(__name__)


# Predefined field profiles for common use cases
FIELD_PROFILES: dict[str, dict[str, list[str]]] = {
    "issues": {
        # Two things these lists deliberately do NOT contain, both verified per-name against the
        # live instance in every spelling (lower-case, capitalised, with and without children):
        #
        # * `idReadable` is in every profile. It is the only stable public name for an issue: `id`
        #   is an internal id (`3-353`) and `numberInProject` alone is ambiguous across projects, so
        #   without it a caller cannot name what it just created or address an issue on a
        #   subsequent call. It is one short field and its absence is the entire defect (#780).
        # * `state`, `priority` and `type` are *not* top-level issue fields. The API drops them, so
        #   requesting them cost payload and returned nothing — and unlike `assignee` next to it,
        #   that is provable rather than assumed: every issue in the project carries all three, so
        #   their absence shows the field is not there. Their values arrive inside `customFields`,
        #   which `standard` and `full` already expand. They were here for a long time precisely
        #   because nothing reported that they were being dropped.
        # * `assignee` *is* a field and stays. It looks identical to the three above on a project
        #   where nothing is assigned, which is what once led to it being removed too — but an
        #   empty value is not a dropped field, and the two are told apart by `KNOWN_ISSUE_FIELDS`
        #   rather than by what a response happens to contain.
        "minimal": [
            "id",
            "idReadable",
            "numberInProject",
            "summary",
        ],
        "compact": [
            # Lean JSON-friendly set: core fields + description, but NO customFields
            # expansion, which dominates payload size on large fetches (#727).
            "id",
            "idReadable",
            "numberInProject",
            "summary",
            "description",
            "assignee(login,fullName,id)",
            "project(id,name,shortName)",
            "created",
            "updated",
        ],
        "standard": [
            "id",
            "idReadable",
            "numberInProject",
            "summary",
            "description",
            "reporter(login,fullName,id)",
            "assignee(login,fullName,id)",
            "project(id,name,shortName)",
            "created",
            "updated",
            "customFields(name,value(name,id,login,fullName,text,presentation))",
        ],
        "full": [
            "id",
            "idReadable",
            "numberInProject",
            "summary",
            "description",
            "reporter(login,fullName,id)",
            "assignee(login,fullName,id)",
            "project(id,name,shortName)",
            "created",
            "updated",
            "resolved",
            "tags(name,id)",
            "customFields(name,value(name,id,login,fullName,text,presentation))",
            "attachments(name,size,url)",
            "comments(text,author(login,fullName),created)",
            "links(linkType(name),issues(id,summary))",
        ],
    },
    "projects": {
        "minimal": [
            "id",
            "shortName",
            "name",
        ],
        "standard": [
            "id",
            "shortName",
            "name",
            "description",
            "leader(login,fullName)",
            "createdBy(login,fullName)",
            "archived",
        ],
        "full": [
            "id",
            "shortName",
            "name",
            "description",
            "leader(login,fullName)",
            "leader(id)",
            "createdBy(login,fullName)",
            "createdBy(id)",
            "archived",
            "template",
            "customFields(field(name,fieldType),canBeEmpty,emptyFieldText)",
            "team(users(login,fullName,email))",
        ],
    },
    "users": {
        "minimal": [
            "id",
            "login",
            "fullName",
        ],
        "standard": [
            "id",
            "login",
            "fullName",
            "email",
            "online",
            "lastAccessTime",
        ],
        "full": [
            "id",
            "login",
            "fullName",
            "email",
            "online",
            "lastAccessTime",
            "avatarUrl",
            "profiles(general(locale,timezone))",
            "groups(name,id)",
            "savedQueries(name,query)",
        ],
    },
    "time_entries": {
        "minimal": [
            "id",
            "duration",
            "date",
        ],
        "standard": [
            "id",
            "duration",
            "date",
            "description",
            "author(id,fullName)",
            "issue(id,summary)",
            "type(name)",
        ],
        "full": [
            "id",
            "duration",
            "date",
            "description",
            "author(id,fullName)",
            "author(login)",
            "issue(id,summary)",
            "issue(numberInProject)",
            "issue(project(shortName))",
            "type(name)",
            "type(id)",
            "workItem(name,id)",
        ],
    },
    "articles": {
        "minimal": [
            "id",
            "summary",
            "idReadable",
        ],
        "standard": [
            "id",
            "summary",
            "idReadable",
            "content",
            "updated",
            "project(id,shortName)",
            "reporter(login,fullName)",
        ],
        "full": [
            "id",
            "summary",
            "idReadable",
            "content",
            "updated",
            "created",
            "project(id,shortName)",
            "project(name)",
            "reporter(login,fullName)",
            "reporter(id)",
            "updater(login,fullName,id)",
            "visibility(permittedGroups(name),permittedUsers(login))",
            "attachments(name,size,url)",
            "comments(text,author(login,fullName),created)",
        ],
    },
}


# --------------------------------------------------------------------------- #
# Verifying that a `--fields` expression actually returned what it asked for.
#
# YouTrack does not fail a request that names a field it does not know: it drops the unknown
# name from the response and returns 200. So `--fields 'idReadble,summary'` — one character of
# typo — prints a payload with no `idReadable` in it, exits 0, and says nothing. The read looks
# like it worked, which is the whole problem: a caller cannot name what it just read, and cannot
# tell a short payload from a short answer.
#
# The check below therefore compares the request against the response instead of against a
# catalogue of valid field names. A catalogue would be a second thing to keep correct and would
# silently go stale whenever a server gains a field; the response is already in hand and is
# authoritative by construction.
# --------------------------------------------------------------------------- #


class _FieldNode:
    """One ``name(child, child)`` term of a ``--fields`` expression."""

    __slots__ = ("name", "children")

    def __init__(self, name: str, children: list[_FieldNode]):
        self.name = name
        self.children = children

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if not self.children:
            return self.name
        inner = ",".join(repr(c) for c in self.children)
        return f"{self.name}({inner})"


def parse_field_expression(expression: str) -> list[_FieldNode]:
    """Parse a ``--fields`` expression into a tree of :class:`_FieldNode`.

    Splits on commas at each nesting level, so ``customFields(name,value(name,id))`` parses as one
    term with two children, the second of which has two of its own. An unbalanced expression is
    parsed as far as it goes; the command's own syntactic validation reports the imbalance, and
    this function's job is to find names the server dropped.
    """
    nodes, _ = _parse_level(expression, 0)
    return nodes


_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")


def _parse_level(text: str, pos: int) -> tuple[list[_FieldNode], int]:
    """Parse comma-separated terms starting at ``pos`` until a ``)`` or the end of ``text``.

    Returns the terms and the index of the ``)`` that ended the level (or ``len(text)``), leaving
    the caller to consume it.
    """
    nodes: list[_FieldNode] = []
    end = len(text)
    while pos < end:
        char = text[pos]
        if char in ", \t":
            pos += 1
            continue
        if char == ")":
            return nodes, pos
        if char not in _NAME_CHARS:
            # Not a name and not structure (a stray quote, say): skip it rather than spin.
            pos += 1
            continue

        start = pos
        while pos < end and text[pos] in _NAME_CHARS:
            pos += 1
        name = text[start:pos]

        children: list[_FieldNode] = []
        if pos < end and text[pos] == "(":
            children, pos = _parse_level(text, pos + 1)
            if pos < end and text[pos] == ")":
                pos += 1
        nodes.append(_FieldNode(name, children))

    return nodes, pos


def _edit_distance_within(a: str, b: str, limit: int) -> bool:
    """True when ``a`` and ``b`` differ by at most ``limit`` characters.

    Used only to recognise a misspelling of a name that *did* come back, so a cheap
    bounded Levenshtein is enough; ``limit`` is 2, which catches every transposition
    and single-character slip in a field name.
    """
    if a == b:
        return False
    if abs(len(a) - len(b)) > limit:
        return False
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        best = i
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            best = min(best, value)
        if best > limit:
            return False
        previous = current
    return previous[-1] <= limit


# How close a requested name must be to a name that *did* come back to count as a misspelling of
# it. 2 catches every single-character slip and every transposition, which is what a hand-typed
# field name actually suffers from.
_MISSPELLING_LIMIT = 2


def find_missing_fields(expression: str, records: object) -> list[str]:
    """Return the top-level names in ``expression`` that the API did not return.

    ``records`` is the decoded response — a list of issue dicts, or a single dict. The result is
    sorted and de-duplicated so the message is stable across runs.

    **No catalogue of valid field names is consulted, and that is the whole design.** Two earlier
    designs were tried and both were unsound:

    * Comparing purely against the response reported any name that was absent, which refuses a
      correct read: ``parentIssueLink`` is a real field, absent from every issue in a project where
      nothing is a sub-task, and that response is indistinguishable from a typo.
    * Adding a hand-written list of the documented fields fixed that and created the opposite
      failure, because such a list is a copy that goes stale — a transcription of one server
      version quietly accepts names a later one rejects, and a hand-maintained list is a second
      thing to keep correct.

    So a name is reported only when the response gives positive evidence against it, from one of
    two signals that need no knowledge of the schema:

    * **Nothing requested came back at all.** A request whose every name is absent is not a
      request that happened to be empty; the whole expression is wrong. This catches the one-name
      case, where there is nothing else to compare against.
    * **It is a near-miss for a name that did come back** — within two characters. ``idReadble``
      next to a returned ``idReadable`` is a typo whatever the schema says, so it is reported
      without needing to know that ``idReadable`` is a field.

    A name that is merely absent is not reported: an empty value is indistinguishable from an
    unknown field, and refusing a read that worked is the worse failure. The cost is that an
    invented name with no near neighbour — ``notAField`` beside ``summary`` — slips through and is
    dropped, which is the behaviour this check replaced. That is the deliberate trade: a caller
    still gets a loud, actionable error for the common slip, and no working read is ever broken.

    Nested subfields are never reported. The API answers by returning *only what it was asked for*,
    so a nested subfield that does not apply to a field's type produces the same bytes as one that
    was misspelled — ``value(name)`` on a text field returns ``{"$type": "TextFieldValue"}`` and
    ``value(bogus)`` returns ``{"$type": ...}``. There is no signal to separate them.
    """
    if not expression or not expression.strip():
        return []

    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not records:
        # Nothing came back, so there is nothing to compare against. That is an empty result,
        # not a bad expression, and the caller reports it as such.
        return []

    requested = {node.name for node in parse_field_expression(expression)}
    if not requested:
        return []

    present: set[str] = set()
    for record in records:
        if isinstance(record, dict):
            present |= set(record)

    absent = requested - present
    if not absent:
        return []

    # Every requested name is absent: the expression is wrong, whatever the schema says.
    if not requested & present:
        return sorted(absent)

    # Otherwise report only the names that look like a misspelling of something that did arrive.
    return sorted(
        name for name in absent if any(_edit_distance_within(name, other, _MISSPELLING_LIMIT) for other in present)
    )


class FieldProfile:
    """Represents a field selection profile for a specific entity type."""

    def __init__(self, entity_type: str, profile_name: str, fields: list[str]):
        self.entity_type = entity_type
        self.profile_name = profile_name
        self.fields = fields

    def get_fields_string(self) -> str:
        """Get the fields as a comma-separated string for API calls."""
        return ",".join(self.fields)

    def get_fields_list(self) -> list[str]:
        """Get the fields as a list."""
        return self.fields.copy()

    def __str__(self) -> str:
        return f"{self.entity_type}:{self.profile_name}"


class FieldSelector:
    """Manages field selection optimization for YouTrack API calls."""

    def __init__(self, config_manager=None):
        self._profiles = FIELD_PROFILES
        self._config_manager = config_manager
        self._default_profiles = {
            "issues": "standard",
            "projects": "standard",
            "users": "standard",
            "time_entries": "standard",
            "articles": "standard",
        }
        self._load_config_defaults()

    def _load_config_defaults(self) -> None:
        """Load default field profiles from configuration."""
        if self._config_manager is None:
            return

        try:
            for entity_type in self._default_profiles:
                config_key = f"FIELD_PROFILE_{entity_type.upper()}"
                configured_profile = self._config_manager.get_config(config_key)
                if configured_profile and configured_profile in self.get_available_profiles(entity_type):
                    self._default_profiles[entity_type] = configured_profile
                    logger.debug(
                        "Loaded default profile from config", entity_type=entity_type, profile=configured_profile
                    )
        except Exception as e:
            logger.warning("Failed to load field profile defaults from config", error=str(e))

    def save_default_to_config(self, entity_type: str, profile_name: str) -> bool:
        """Save default profile preference to configuration.

        Args:
            entity_type: Type of entity
            profile_name: Profile name to save as default

        Returns:
            True if saved successfully, False otherwise
        """
        if self._config_manager is None:
            logger.warning("No config manager available to save defaults")
            return False

        if not self.set_default_profile(entity_type, profile_name):
            return False

        try:
            config_key = f"FIELD_PROFILE_{entity_type.upper()}"
            self._config_manager.set_config(config_key, profile_name)
            logger.info(
                "Saved default profile to config", entity_type=entity_type, profile=profile_name, config_key=config_key
            )
            return True
        except Exception as e:
            logger.error("Failed to save default profile to config", error=str(e))
            return False

    def get_profile(self, entity_type: str, profile_name: str) -> FieldProfile | None:
        """Get a specific field profile.

        Args:
            entity_type: Type of entity (issues, projects, users, etc.)
            profile_name: Name of profile (minimal, standard, full)

        Returns:
            FieldProfile if found, None otherwise
        """
        if entity_type not in self._profiles:
            logger.warning("Unknown entity type for field selection", entity_type=entity_type)
            return None

        profiles = self._profiles[entity_type]
        if profile_name not in profiles:
            logger.warning(
                "Unknown profile for entity type",
                entity_type=entity_type,
                profile_name=profile_name,
                available_profiles=list(profiles.keys()),
            )
            return None

        return FieldProfile(entity_type, profile_name, profiles[profile_name])

    def get_fields(
        self,
        entity_type: str,
        profile: str | None = None,
        custom_fields: str | list[str] | None = None,
        exclude_fields: list[str] | None = None,
    ) -> str:
        """Get optimized field selection for an entity type.

        Args:
            entity_type: Type of entity (issues, projects, users, etc.)
            profile: Profile name (minimal, standard, full) or None for default
            custom_fields: Custom field specification (string or list)
            exclude_fields: Fields to exclude from the selection

        Returns:
            Comma-separated field string for API calls
        """
        # Use default profile if none specified
        if profile is None:
            profile = self._default_profiles.get(entity_type, "standard")

        # Get the base profile
        field_profile = self.get_profile(entity_type, profile)
        if not field_profile:
            # Fallback to full profile for unknown entity/profile
            logger.warning("Falling back to full profile", entity_type=entity_type, requested_profile=profile)
            field_profile = self.get_profile(entity_type, "full")
            if not field_profile:
                # Last resort - return basic fields
                return "id,summary" if entity_type != "users" else "id,login,fullName"

        fields_set = set(field_profile.get_fields_list())

        # Add custom fields if specified
        if custom_fields:
            if isinstance(custom_fields, str):
                custom_fields = [f.strip() for f in custom_fields.split(",")]
            fields_set.update(custom_fields)

        # Remove excluded fields
        if exclude_fields:
            fields_set -= set(exclude_fields)

        # Ensure we always have at least an ID field
        if entity_type == "users":
            fields_set.add("id")
            fields_set.add("login")
        else:
            fields_set.add("id")

        result = ",".join(sorted(fields_set))

        logger.debug(
            "Generated field selection",
            entity_type=entity_type,
            profile=profile,
            field_count=len(fields_set),
            fields=result[:100] + "..." if len(result) > 100 else result,
        )

        return result

    def get_available_profiles(self, entity_type: str) -> list[str]:
        """Get available profiles for an entity type."""
        return list(self._profiles.get(entity_type, {}).keys())

    def get_supported_entities(self) -> list[str]:
        """Get list of supported entity types."""
        return list(self._profiles.keys())

    def set_default_profile(self, entity_type: str, profile_name: str) -> bool:
        """Set the default profile for an entity type.

        Args:
            entity_type: Type of entity
            profile_name: Name of profile to set as default

        Returns:
            True if successful, False if entity type or profile doesn't exist
        """
        if entity_type not in self._profiles:
            return False
        if profile_name not in self._profiles[entity_type]:
            return False

        self._default_profiles[entity_type] = profile_name
        logger.info("Default profile updated", entity_type=entity_type, profile=profile_name)
        return True

    def validate_fields(self, fields: str, entity_type: str) -> bool:
        """Validate that field specification is syntactically correct.

        Args:
            fields: Comma-separated field specification
            entity_type: Type of entity for context

        Returns:
            True if fields appear valid, False otherwise
        """
        if not fields or not fields.strip():
            return False

        try:
            # Check overall parentheses balance first
            open_parens = fields.count("(")
            close_parens = fields.count(")")
            if open_parens != close_parens:
                logger.warning("Unbalanced parentheses in field specification", fields=fields)
                return False

            # Check for valid characters
            allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789().,_ ")
            if not all(c in allowed_chars for c in fields):
                logger.warning("Invalid characters in field specification", fields=fields)
                return False

            # Basic field name validation - ensure we have at least one alphanumeric character
            cleaned = fields.replace("(", "").replace(")", "").replace(",", "").replace(".", "").replace(" ", "")
            if not cleaned or not any(c.isalnum() for c in cleaned):
                logger.warning("No valid field names found", fields=fields)
                return False

            return True

        except Exception as e:
            logger.warning("Field validation error", fields=fields, error=str(e))
            return False


# Global field selector instance
_field_selector: FieldSelector | None = None


def get_field_selector(config_manager=None) -> FieldSelector:
    """Get the global field selector instance.

    Args:
        config_manager: Optional config manager for loading/saving preferences

    Returns:
        FieldSelector instance
    """
    global _field_selector
    if _field_selector is None:
        _field_selector = FieldSelector(config_manager)
    # Type assertion: _field_selector is guaranteed not None after initialization
    from typing import cast

    field_selector = cast(FieldSelector, _field_selector)
    return field_selector
