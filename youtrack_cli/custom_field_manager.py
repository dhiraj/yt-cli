"""
Centralized custom field management utilities for YouTrack CLI.

This module provides a unified interface for creating, extracting, and manipulating
custom fields across the YouTrack CLI application, reducing code duplication and
improving maintainability.
"""

from collections.abc import Sequence
from typing import Any

from .custom_field_types import CustomFieldValueTypes, IssueCustomFieldTypes, get_display_name
from .exceptions import (
    CustomFieldMultiplicityUnknownError,
    CustomFieldUnresolvedReason,
    CustomFieldValueCountError,
    CustomFieldValueTypeError,
    UnsupportedCustomFieldTypeError,
)


def _require_single_value(name: str, values: list[Any], issue_field_type: str | None) -> None:
    """Refuse several values for a field that holds one.

    Every value given is a statement about what the caller wants set, so dropping all but
    the last would answer a question that was not asked -- and answer it with a success
    message. A field that holds several is reached through the multi-value branch instead,
    which is chosen by the field's own multiplicity rather than by the caller guessing it.
    """
    if len(values) > 1:
        raise CustomFieldValueCountError(name, values, issue_field_type)


def _require_writable_value(name: str, values: list[Any]) -> None:
    """Refuse a value no builder can put on the wire.

    `yt batch create --file items.json` forwards every non-null field of a JSON row
    verbatim, so this receives whatever that file holds: a bool where a number was meant,
    an object where a string was meant. Those are not values this CLI can state -- `True`
    is an `int` to `isinstance`, so a numeric field would take it as 1, and an object
    would be stringified -- and writing either would report success for something the
    caller did not ask for. Naming the field is the whole point of refusing here.
    """
    unwritable = [value for value in values if not isinstance(value, str | int | float) or isinstance(value, bool)]
    if unwritable:
        given = ", ".join(f"{type(value).__name__}" for value in unwritable)
        raise CustomFieldValueTypeError(name, given)


class CustomFieldManager:
    """Centralized manager for YouTrack custom field operations."""

    @staticmethod
    def create_single_enum_field(name: str, value: str) -> dict[str, Any]:
        """
        Create a single enum custom field dictionary.

        Args:
            name: The field name
            value: The enum value name

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.SINGLE_ENUM,
            "name": name,
            "value": {"$type": CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT, "name": value},
        }

    @staticmethod
    def create_multi_enum_field(name: str, values: list[str]) -> dict[str, Any]:
        """
        Create a multi enum custom field dictionary.

        Args:
            name: The field name
            values: List of enum value names

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.MULTI_ENUM,
            "name": name,
            "value": [{"$type": CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT, "name": value} for value in values],
        }

    @staticmethod
    def create_state_field(name: str, value: str) -> dict[str, Any]:
        """
        Create a state custom field dictionary.

        Args:
            name: The field name
            value: The state value name

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.STATE,
            "name": name,
            "value": {"$type": CustomFieldValueTypes.STATE_BUNDLE_ELEMENT, "name": value},
        }

    @staticmethod
    def create_single_owned_field(name: str, owned_name: str) -> dict[str, Any]:
        """
        Create a single owned custom field dictionary.

        An owned field is bundle-backed like an enum, but it has its own issue-side type
        and its own value type: YouTrack rejects an OwnedBundleElement sent through the
        enum field type, and rejects a bare string sent through the owned field type.

        Args:
            name: The field name
            owned_name: The owned value name

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.SINGLE_OWNED,
            "name": name,
            "value": {"$type": CustomFieldValueTypes.OWNED_BUNDLE_ELEMENT, "name": owned_name},
        }

    @staticmethod
    def create_single_user_field(name: str, user_login: str) -> dict[str, Any]:
        """
        Create a single user custom field dictionary.

        Args:
            name: The field name
            user_login: The user login/ID

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.SINGLE_USER,
            "name": name,
            "value": {"$type": CustomFieldValueTypes.USER, "login": user_login},
        }

    @staticmethod
    def create_multi_user_field(name: str, user_logins: list[str]) -> dict[str, Any]:
        """
        Create a multi user custom field dictionary.

        Args:
            name: The field name
            user_logins: List of user logins/IDs

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.MULTI_USER,
            "name": name,
            "value": [{"$type": CustomFieldValueTypes.USER, "login": user_login} for user_login in user_logins],
        }

    @staticmethod
    def create_text_field(name: str, text: str) -> dict[str, Any]:
        """
        Create a text custom field dictionary.

        Args:
            name: The field name
            text: The text value

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.TEXT,
            "name": name,
            "value": {"$type": CustomFieldValueTypes.TEXT_VALUE, "text": text},
        }

    @staticmethod
    def extract_field_value(custom_fields: list[dict[str, Any]], field_name: str) -> Any:
        """
        Extract a custom field value by field name.

        Args:
            custom_fields: List of custom field dictionaries
            field_name: Name of the field to extract

        Returns:
            The field value or None if not found
        """
        if not custom_fields:
            return None

        for field in custom_fields:
            # Handle invalid field structures
            if not isinstance(field, dict):
                continue

            if field.get("name") == field_name:
                value = field.get("value")
                if value is None:
                    return None

                # Handle different value types
                return CustomFieldManager._extract_dict_value(value)

        return None

    @staticmethod
    def _extract_dict_value(value: dict | list | str | int | float) -> Any:
        """
        Extract value from a custom field value dictionary or list.

        Args:
            value: The value dictionary, list, or primitive value

        Returns:
            Extracted value in appropriate format
        """
        if isinstance(value, list):
            # Multi-value field - extract values and join with comma
            extracted_values = [CustomFieldManager._extract_dict_value(item) for item in value]
            # Filter out None values and join with comma
            valid_values = [str(v) for v in extracted_values if v is not None]
            return ", ".join(valid_values) if valid_values else None

        if not isinstance(value, dict):
            # Primitive value
            return value

        # Handle empty dictionaries
        if not value:
            return None

        # Priority-based extraction following the documented order
        extraction_keys = [
            "presentation",
            "fullName",
            "localizedName",
            "text",
            "name",
            "buildLink",
            "avatarUrl",
            "minutes",
            "isResolved",
            "color",
            "login",
            "id",
        ]

        for key in extraction_keys:
            if key in value and value[key] is not None:
                extracted_value = value[key]
                # Handle nested structures for color(id)
                if key == "color" and isinstance(extracted_value, dict):
                    return extracted_value.get("id", str(extracted_value))
                # Convert boolean and numeric values to strings
                return str(extracted_value)

        # Return the whole dictionary if no specific field found
        return value

    @staticmethod
    def get_field_id(custom_fields: list[dict[str, Any]], field_name: str) -> str | None:
        """
        Get the ID of a custom field by name.

        Args:
            custom_fields: List of custom field dictionaries
            field_name: Name of the field

        Returns:
            Field ID or None if not found
        """
        if not custom_fields:
            return None

        for field in custom_fields:
            if field.get("name") == field_name:
                return field.get("id")

        return None

    @staticmethod
    def format_field_type_for_display(field_type: str) -> str:
        """
        Format a field type string for display purposes.

        Args:
            field_type: The YouTrack API field type

        Returns:
            Human-readable field type name
        """
        return get_display_name(field_type)

    @staticmethod
    def get_field_with_fallback(issue: dict[str, Any], primary_field: str, fallback_field: str) -> Any:
        """
        Get a field value with fallback to custom fields.

        Args:
            issue: The issue dictionary
            primary_field: Primary field name to check
            fallback_field: Fallback custom field name

        Returns:
            Field value from primary field or custom fields
        """
        # Try primary field first
        primary_value = issue.get(primary_field)
        if primary_value is not None:
            return primary_value

        # Fallback to custom fields
        custom_fields = issue.get("customFields", [])
        return CustomFieldManager.extract_field_value(custom_fields, fallback_field)

    @staticmethod
    def create_project_enum_field_config(
        field_type: str, can_be_empty: bool = True, empty_field_text: str = "No value", is_public: bool = True
    ) -> dict[str, Any]:
        """
        Create configuration for attaching an enum field to a project.

        Args:
            field_type: The project custom field type
            can_be_empty: Whether the field can be empty
            empty_field_text: Text to show when field is empty
            is_public: Whether the field is public

        Returns:
            Configuration dictionary for the field
        """
        return {
            "$type": field_type,
            "canBeEmpty": can_be_empty,
            "emptyFieldText": empty_field_text,
            "isPublic": is_public,
        }

    @staticmethod
    def extract_user_field_info(user_value: dict[str, Any]) -> dict[str, str]:
        """
        Extract comprehensive user information from a user field value.

        Args:
            user_value: User field value dictionary

        Returns:
            Dictionary with user information (login, fullName, etc.)
        """
        if not isinstance(user_value, dict):
            return {}

        return {
            "login": user_value.get("login", ""),
            "fullName": user_value.get("fullName", ""),
            "name": user_value.get("name", ""),
            "email": user_value.get("email", ""),
            "avatarUrl": user_value.get("avatarUrl", ""),
        }

    @staticmethod
    def is_multi_value_field(field_type: str) -> bool:
        """
        Check if a field type is multi-value.

        Only meaningful for the *issue*-side vocabulary, which is the one that spells
        multiplicity into the type name. The project admin API names only the kind of
        field and reports multiplicity separately, on the field's ``fieldType``
        (``isMultiValue``, or the ``[*]`` suffix on ``fieldType.id``) -- so a
        ``ProjectCustomFieldTypes`` value passed here is always answered False, and
        asking the project side this way cannot work.

        Args:
            field_type: The field type string

        Returns:
            True if the field type supports multiple values
        """
        multi_value_types = {
            IssueCustomFieldTypes.MULTI_ENUM,
            IssueCustomFieldTypes.MULTI_USER,
            IssueCustomFieldTypes.MULTI_VERSION,
            IssueCustomFieldTypes.MULTI_BUILD,
            IssueCustomFieldTypes.MULTI_OWNED,
        }
        return field_type in multi_value_types

    @staticmethod
    def create_simple_field(name: str, value: int | float | str) -> dict[str, Any]:
        """
        Create a simple (integer/float) custom field.

        Args:
            name: The field name
            value: The numeric value

        Returns:
            Dictionary representing the custom field
        """
        # Convert to appropriate numeric type
        try:
            if isinstance(value, int | float):
                numeric_value = value
            else:
                # Try int first, then float
                numeric_value = int(value) if str(value).isdigit() else float(value)
        except (ValueError, TypeError):
            # Fallback to string representation if conversion fails
            numeric_value = str(value)

        return {
            "$type": IssueCustomFieldTypes.INTEGER,
            "name": name,
            "value": numeric_value,
        }

    @staticmethod
    def create_date_field(name: str, value: str) -> dict[str, Any]:
        """
        Create a date custom field.

        Args:
            name: The field name
            value: The date value (Unix timestamp in milliseconds)

        Returns:
            Dictionary representing the custom field
        """
        try:
            timestamp = int(value)
        except (ValueError, TypeError):
            timestamp = int(value)  # Will raise if invalid

        return {
            "$type": IssueCustomFieldTypes.DATE,
            "name": name,
            "value": timestamp,
        }

    @staticmethod
    def create_single_version_field(name: str, value: str) -> dict[str, Any]:
        """
        Create a single version custom field.

        Args:
            name: The field name
            value: The version name

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.SINGLE_VERSION,
            "name": name,
            "value": {"$type": CustomFieldValueTypes.VERSION_BUNDLE_ELEMENT, "name": value},
        }

    @staticmethod
    def create_single_build_field(name: str, value: str) -> dict[str, Any]:
        """
        Create a single build custom field.

        Args:
            name: The field name
            value: The build name

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.SINGLE_BUILD,
            "name": name,
            "value": {"$type": CustomFieldValueTypes.BUILD_BUNDLE_ELEMENT, "name": value},
        }

    @staticmethod
    def create_multi_version_field(name: str, values: list[str]) -> dict[str, Any]:
        """
        Create a multi version custom field.

        Args:
            name: The field name
            values: List of version names

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.MULTI_VERSION,
            "name": name,
            "value": [{"$type": CustomFieldValueTypes.VERSION_BUNDLE_ELEMENT, "name": value} for value in values],
        }

    @staticmethod
    def create_multi_build_field(name: str, values: list[str]) -> dict[str, Any]:
        """
        Create a multi build custom field.

        Args:
            name: The field name
            values: List of build names

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.MULTI_BUILD,
            "name": name,
            "value": [{"$type": CustomFieldValueTypes.BUILD_BUNDLE_ELEMENT, "name": value} for value in values],
        }

    @staticmethod
    def create_multi_owned_field(name: str, values: list[str]) -> dict[str, Any]:
        """
        Create a multi owned custom field.

        Args:
            name: The field name
            values: List of owned value names

        Returns:
            Dictionary representing the custom field
        """
        return {
            "$type": IssueCustomFieldTypes.MULTI_OWNED,
            "name": name,
            "value": [{"$type": CustomFieldValueTypes.OWNED_BUNDLE_ELEMENT, "name": value} for value in values],
        }

    @staticmethod
    def create_field_by_type(
        field_info: dict[str, Any], name: str, value: str | int | float | Sequence[Any]
    ) -> dict[str, Any]:
        """
        Create a custom field using discovered type information.

        Args:
            field_info: Field information from discover_custom_field
            name: Field name
            value: One value, or several for a field that holds several. A sequence is
                read as the field's values and a non-sequence as one value of whatever
                scalar type it has -- `yt batch` forwards every non-null field from a JSON
                row verbatim, so a numeric custom field arrives as a number, not a string.
                A value that is neither a string, a number, nor a sequence of them is
                refused rather than coerced.

        Returns:
            Formatted custom field dictionary

        Raises:
            UnsupportedCustomFieldTypeError: The field's type is not one this CLI knows
                how to write. Raised rather than guessed: an unrecognised type sent as an
                enum is rejected by the server as a confusing type mismatch, and the wrong
                value shape is indistinguishable from a bad value at the call site.
            CustomFieldMultiplicityUnknownError: The field is bundle-backed and the server
                did not report whether it holds one value or several, so the value shape
                cannot be stated.
            CustomFieldValueCountError: No value was given, or several were given for a
                field that holds one. Refused rather than resolved by keeping the last,
                which would report success for a request that did not say what it meant.
            CustomFieldValueTypeError: A value is not a string, a number, or a sequence of
                them, so no builder can state it.
        """
        issue_field_type = field_info.get("issue_field_type")
        project_field_type = field_info.get("project_field_type")
        values = (
            list(value)
            if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray | memoryview)
            else [value]
        )

        # A field whose *type* could not be resolved is settled first, then whether a value
        # was supplied, then whether that value can be stated -- in the order each answer
        # becomes reachable. The other order reports "no value was given" for a field this
        # CLI cannot write anyway, pointing the reader at a value they never supplied while
        # the real cause surfaces only on the next attempt.
        if issue_field_type is None:
            if field_info.get("unresolved_reason") == CustomFieldUnresolvedReason.MULTIPLICITY:
                raise CustomFieldMultiplicityUnknownError(name, project_field_type)
            raise UnsupportedCustomFieldTypeError(name, project_field_type, issue_field_type)

        if not values:
            # An empty list is not a value the caller can have meant: `-cf "Field="` is
            # rejected at the CLI boundary, so one here came from a programmatic caller
            # (`yt batch` forwards an empty JSON list verbatim). Writing it would clear a
            # field on the strength of nothing.
            raise CustomFieldValueCountError(name, values, issue_field_type)

        _require_writable_value(name, values)

        # Multi-valued fields take a list, and the value element carries the same bundle
        # discriminator a single-valued one does -- so these are the same payloads with a
        # list, not a different kind of write. The enum forms are dispatched separately
        # because they are the only ones that need the discovered element type; the rest
        # fix their own from the kind.
        if issue_field_type == IssueCustomFieldTypes.MULTI_ENUM:
            return CustomFieldManager._create_multi_bundle_backed_enum_field(name, values, field_info)

        multi_value_builders = {
            IssueCustomFieldTypes.MULTI_USER: CustomFieldManager.create_multi_user_field,
            IssueCustomFieldTypes.MULTI_VERSION: CustomFieldManager.create_multi_version_field,
            IssueCustomFieldTypes.MULTI_BUILD: CustomFieldManager.create_multi_build_field,
            IssueCustomFieldTypes.MULTI_OWNED: CustomFieldManager.create_multi_owned_field,
        }
        if issue_field_type in multi_value_builders:
            return multi_value_builders[issue_field_type](name, values)

        # Map issue field types to creation methods. Every single-valued branch goes
        # through the same count check: a branch that quietly took the first of several
        # values would drop one without saying so, which is the behaviour this replaced.
        if issue_field_type == IssueCustomFieldTypes.TEXT:
            _require_single_value(name, values, issue_field_type)
            return CustomFieldManager.create_text_field(name, values[0])
        elif issue_field_type == IssueCustomFieldTypes.INTEGER:
            _require_single_value(name, values, issue_field_type)
            return CustomFieldManager.create_simple_field(name, values[0])
        elif issue_field_type == IssueCustomFieldTypes.SINGLE_USER:
            _require_single_value(name, values, issue_field_type)
            return CustomFieldManager.create_single_user_field(name, values[0])
        elif issue_field_type == IssueCustomFieldTypes.SINGLE_OWNED:
            _require_single_value(name, values, issue_field_type)
            return CustomFieldManager.create_single_owned_field(name, values[0])
        elif issue_field_type == IssueCustomFieldTypes.SINGLE_VERSION:
            _require_single_value(name, values, issue_field_type)
            return CustomFieldManager.create_single_version_field(name, values[0])
        elif issue_field_type == IssueCustomFieldTypes.SINGLE_BUILD:
            _require_single_value(name, values, issue_field_type)
            return CustomFieldManager.create_single_build_field(name, values[0])
        elif issue_field_type == IssueCustomFieldTypes.SINGLE_ENUM:
            _require_single_value(name, values, issue_field_type)
            return CustomFieldManager._create_bundle_backed_enum_field(name, values[0], field_info)
        elif issue_field_type == IssueCustomFieldTypes.STATE:
            _require_single_value(name, values, issue_field_type)
            return CustomFieldManager.create_state_field(name, values[0])
        else:
            # A type that resolved but has no branch here: a constant added to the issue
            # vocabulary and mapped without a writer. Refused rather than defaulted.
            raise UnsupportedCustomFieldTypeError(name, project_field_type, issue_field_type)

    @staticmethod
    def _create_bundle_backed_enum_field(
        name: str,
        value: str,
        field_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Build an enum-shaped field, taking the value discriminator from discovery.

        A bundle that reports its element type is authoritative. A plain enum field always
        reports EnumBundleElement, which is also the right default when the bundle is empty
        and so has nothing to report.
        """
        element_type = field_info.get("bundle_element_type") or CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT
        return {
            "$type": IssueCustomFieldTypes.SINGLE_ENUM,
            "name": name,
            "value": {"$type": element_type, "name": value},
        }

    @staticmethod
    def _create_multi_bundle_backed_enum_field(
        name: str,
        values: list[str],
        field_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a multi enum-shaped field, taking the value discriminator from discovery.

        The list form of `_create_bundle_backed_enum_field`, and for the same reason: a
        bundle that reports its element type is authoritative, and a plain enum field
        always reports EnumBundleElement.
        """
        element_type = field_info.get("bundle_element_type") or CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT
        return {
            "$type": IssueCustomFieldTypes.MULTI_ENUM,
            "name": name,
            "value": [{"$type": element_type, "name": value} for value in values],
        }
