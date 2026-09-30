"""Custom exceptions and error handling for YouTrack CLI."""

from typing import Any

__all__ = [
    "YouTrackError",
    "AuthenticationError",
    "ConnectionError",
    "ValidationError",
    "NotFoundError",
    "PermissionError",
    "RateLimitError",
    "YouTrackNetworkError",
    "YouTrackServerError",
    "CommandValidationError",
    "ParameterError",
    "UsageError",
    "TokenRefreshError",
    "TokenExpiredError",
    "CustomFieldWriteRefusal",
    "CustomFieldUnresolvedReason",
    "UnsupportedCustomFieldTypeError",
    "CustomFieldValueCountError",
    "CustomFieldValueTypeError",
    "CustomFieldMultiplicityUnknownError",
]


class YouTrackError(Exception):
    """Base exception for YouTrack CLI errors."""

    def __init__(self, message: str, suggestion: str | None = None):
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion


class AuthenticationError(YouTrackError):
    """Authentication related errors."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, suggestion="Run 'yt auth login' to authenticate with YouTrack")


class ConnectionError(YouTrackError):
    """Connection related errors."""

    def __init__(self, message: str = "Failed to connect to YouTrack"):
        super().__init__(message, suggestion="Check your internet connection and YouTrack URL")


class ValidationError(YouTrackError):
    """Input validation errors."""

    def __init__(self, message: str, field: str | None = None):
        if field:
            message = f"Invalid {field}: {message}"
        super().__init__(message)
        self.field = field


class NotFoundError(YouTrackError):
    """Resource not found errors."""

    def __init__(self, resource_type: str, identifier: str):
        super().__init__(
            f"{resource_type} '{identifier}' not found",
            suggestion=(f"Check if the {resource_type.lower()} exists and you have access to it"),
        )


class PermissionError(YouTrackError):
    """Permission denied errors."""

    def __init__(self, action: str, resource: str | None = None):
        if resource:
            message = f"Permission denied to {action} {resource}"
        else:
            message = f"Permission denied to {action}"
        super().__init__(message, suggestion="Check your user permissions in YouTrack")


class RateLimitError(YouTrackError):
    """Rate limit exceeded errors."""

    def __init__(self, retry_after: int | None = None):
        message = "Rate limit exceeded"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        super().__init__(
            message,
            suggestion=("Wait a moment and try again, or reduce the frequency of requests"),
        )


class YouTrackNetworkError(YouTrackError):
    """Network related errors that may be retryable."""

    def __init__(self, message: str = "Network error occurred"):
        super().__init__(message, suggestion="Check your internet connection and try again")


class YouTrackServerError(YouTrackError):
    """Server-side errors that may be retryable."""

    def __init__(self, message: str = "Server error occurred", status_code: int | None = None):
        if status_code:
            message = f"Server error (HTTP {status_code}): {message}"
        super().__init__(message, suggestion="The server may be temporarily unavailable. Try again later")
        self.status_code = status_code


class CommandValidationError(YouTrackError):
    """Errors related to command structure and usage."""

    def __init__(
        self,
        message: str,
        command_path: str | None = None,
        usage_example: str | None = None,
        similar_commands: list[str] | None = None,
    ):
        suggestion_parts = []
        if similar_commands:
            suggestion_parts.append(f"Did you mean: {', '.join(similar_commands)}")
        if usage_example:
            suggestion_parts.append(f"Usage: {usage_example}")

        suggestion = " | ".join(suggestion_parts) if suggestion_parts else None
        super().__init__(message, suggestion)
        self.command_path = command_path
        self.usage_example = usage_example
        self.similar_commands = similar_commands


class ParameterError(YouTrackError):
    """Errors related to command parameters and arguments."""

    def __init__(
        self,
        message: str,
        parameter_name: str | None = None,
        expected_type: str | None = None,
        usage_example: str | None = None,
        valid_choices: list[str] | None = None,
    ):
        suggestion_parts = []
        if expected_type:
            suggestion_parts.append(f"Expected {expected_type}")
        if valid_choices:
            suggestion_parts.append(f"Valid choices: {', '.join(valid_choices)}")
        if usage_example:
            suggestion_parts.append(f"Example: {usage_example}")

        suggestion = " | ".join(suggestion_parts) if suggestion_parts else None
        super().__init__(message, suggestion)
        self.parameter_name = parameter_name
        self.expected_type = expected_type
        self.usage_example = usage_example
        self.valid_choices = valid_choices


class UsageError(YouTrackError):
    """Errors that provide comprehensive usage guidance."""

    def __init__(
        self,
        message: str,
        command_path: str,
        usage_syntax: str,
        examples: list[str] | None = None,
        common_mistakes: list[str] | None = None,
    ):
        suggestion_parts = [f"Usage: {usage_syntax}"]

        if examples:
            suggestion_parts.append("Examples:")
            for i, example in enumerate(examples, 1):
                suggestion_parts.append(f"  {i}. {example}")

        if common_mistakes:
            suggestion_parts.append("Common mistakes to avoid:")
            for mistake in common_mistakes:
                suggestion_parts.append(f"  - {mistake}")

        suggestion = "\n".join(suggestion_parts)
        super().__init__(message, suggestion)
        self.command_path = command_path
        self.usage_syntax = usage_syntax
        self.examples = examples or []
        self.common_mistakes = common_mistakes or []


class TokenRefreshError(AuthenticationError):
    """Token refresh related errors."""

    def __init__(self, message: str = "Token refresh failed"):
        super().__init__(message)
        self.suggestion = "Try 'yt auth login' to re-authenticate or check if your token supports refresh"


class TokenExpiredError(AuthenticationError):
    """Token expiration related errors."""

    def __init__(self, message: str = "Token has expired"):
        super().__init__(message)
        self.suggestion = "Run 'yt auth refresh' to renew your token or 'yt auth login' to re-authenticate"


class CustomFieldWriteRefusal(YouTrackError):
    """Base for the refusals that leave a custom field unwritten rather than guessed.

    A custom field has to be written with an exact type and an exact value shape, and
    both are learned from the server: the field's ``$type`` names the kind, and
    ``fieldType.isMultiValue`` says whether it holds one value or several. When either
    cannot be established, the alternatives are a guess — and a wrong guess is rejected
    by the server as a type mismatch, which reads like a server or data problem rather
    than a CLI limitation, or (worse) is accepted and quietly means something other than
    what was asked for. Every subclass here answers one question — why was nothing sent
    for this field? — so the create and update paths report refusals by name and leave
    the issue untouched.
    """


class CustomFieldUnresolvedReason:
    """Why a discovered field could not be turned into a writable payload.

    The two causes are not the same problem and must not be reported as one: an
    unrecognised kind is a limitation of this CLI, whereas an unreported multiplicity is
    a gap in one server response for a kind this CLI handles perfectly well. Naming the
    wrong one sends the reader looking in the wrong place -- at a vocabulary, or at a
    field that is not the problem at all.

    Discovery sets one of these; the writer turns it into the matching refusal.
    """

    TYPE = "type"
    MULTIPLICITY = "multiplicity"


class UnsupportedCustomFieldTypeError(CustomFieldWriteRefusal):
    """A custom field's type is not one this CLI knows how to write.

    Raised instead of substituting a default field type. A field sent with the wrong
    type discriminator is rejected by the server as a type mismatch, which reads like
    a server or data problem rather than a CLI limitation; refusing locally names the
    field and its type and leaves the issue untouched.
    """

    def __init__(self, field_name: str, project_field_type: str | None, issue_field_type: str | None = None):
        self.field_name = field_name
        self.project_field_type = project_field_type
        self.issue_field_type = issue_field_type

        described = project_field_type or issue_field_type or "an unknown type"
        message = f"Cannot set field '{field_name}': this CLI does not know how to write a field of type '{described}'"
        suggestion = (
            "No value was sent, so the issue is unchanged. Set the field through the YouTrack UI, "
            "or use a dedicated option such as --assignee where one exists"
        )

        super().__init__(message, suggestion)


class CustomFieldValueCountError(CustomFieldWriteRefusal):
    """The number of values given cannot be written to this field.

    Two cases, worded apart because asserting something untrue is worse than saying less.
    No value at all says nothing about what the field holds -- the same call is wrong for a
    single-valued and a multi-valued field, for different reasons -- so it does not claim
    to. Several values for a field that holds one does name the cause, because that is
    exactly what is wrong.
    """

    def __init__(self, field_name: str, values: list[Any], issue_field_type: str | None = None):
        self.field_name = field_name
        self.values = list(values)
        self.issue_field_type = issue_field_type

        if not self.values:
            message = f"Cannot set field '{field_name}': no value was given"
            suggestion = (
                "No value was sent, so the issue is unchanged. Give the field a value; "
                '`-cf "Field="` is refused at the command line for the same reason'
            )
        else:
            given = ", ".join(repr(value) for value in self.values)
            message = (
                f"Cannot set field '{field_name}': it holds a single value but {len(self.values)} were given ({given})"
            )
            suggestion = (
                "No value was sent, so the issue is unchanged. Pass one value for this field. Repeating a "
                "field name sets several values, and is only meaningful for a field that holds several"
            )

        super().__init__(message, suggestion)


class CustomFieldValueTypeError(CustomFieldWriteRefusal):
    """A value's type is not one this CLI can put on the wire for a field.

    Distinct from a wrong *value*, which the server rejects in its own words: this is a
    value the CLI cannot state at all. `yt batch` forwards every non-null field of a JSON
    row verbatim, so a bool where a number was meant, or an object where a string was
    meant, arrives here rather than being caught earlier -- and a bool is an `int` to
    `isinstance`, so a numeric field would silently take `true` as 1.
    """

    def __init__(self, field_name: str, given_types: str):
        self.field_name = field_name
        self.given_types = given_types

        message = f"Cannot set field '{field_name}': a value of type {given_types} is not a field value"
        suggestion = (
            "No value was sent, so the issue is unchanged. A field value is a string, a number, or a list of "
            "them. This usually means a value in a `yt batch` input file is a JSON object or a boolean"
        )

        super().__init__(message, suggestion)


class CustomFieldMultiplicityUnknownError(CustomFieldWriteRefusal):
    """The server did not report whether a field holds one value or several.

    The value shape follows from multiplicity: a single-valued field takes one element
    and a multi-valued one takes a list, so an unreported multiplicity means an
    unstatable payload. It is reported as its own refusal rather than folded into the
    "unknown type" one, which would name a type this CLI does in fact handle.
    """

    def __init__(self, field_name: str, project_field_type: str | None = None):
        self.field_name = field_name
        self.project_field_type = project_field_type

        # The type is stated up front rather than appended: appended, it reads as though
        # "of type X" qualified "several values", which is not what it says.
        described = f" (type '{project_field_type}')" if project_field_type else ""
        message = (
            f"Cannot set field '{field_name}'{described}: the server did not report whether it holds "
            "one value or several"
        )
        suggestion = (
            "No value was sent, so the issue is unchanged. This is a gap in the server's response rather "
            "than in the field — set it through the YouTrack UI, and please report it"
        )

        super().__init__(message, suggestion)
