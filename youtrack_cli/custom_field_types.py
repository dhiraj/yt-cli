"""
Custom field type constants for YouTrack API.

This module defines constants for all YouTrack custom field types to eliminate
hardcoded strings throughout the codebase and provide a centralized reference.
"""


class IssueCustomFieldTypes:
    """Custom field types for issues."""

    SINGLE_ENUM = "SingleEnumIssueCustomField"
    MULTI_ENUM = "MultiEnumIssueCustomField"
    STATE = "StateIssueCustomField"
    SINGLE_USER = "SingleUserIssueCustomField"
    MULTI_USER = "MultiUserIssueCustomField"
    SINGLE_OWNED = "SingleOwnedIssueCustomField"
    MULTI_OWNED = "MultiOwnedIssueCustomField"
    SINGLE_VERSION = "SingleVersionIssueCustomField"
    MULTI_VERSION = "MultiVersionIssueCustomField"
    SINGLE_BUILD = "SingleBuildIssueCustomField"
    MULTI_BUILD = "MultiBuildIssueCustomField"
    TEXT = "TextIssueCustomField"
    PERIOD = "PeriodIssueCustomField"
    DATE = "DateIssueCustomField"
    DATE_TIME = "DateTimeIssueCustomField"
    INTEGER = "SimpleIssueCustomField"
    FLOAT = "SimpleIssueCustomField"


class ProjectCustomFieldTypes:
    """Custom field types for projects.

    These are the ``$type`` discriminators the *project* admin API returns. Two
    properties of that vocabulary are what the lookup built on it has to get right,
    and both were verified against a live instance rather than inferred:

    1. It names the **kind** of field (``UserProjectCustomField``), never the
       issue-side spelling (``SingleUserIssueCustomField``). A project type spelled
       like its issue counterpart matches no real response, and the lookup that
       consumes it then falls through.
    2. It carries **no multiplicity**. There is no ``MultiEnumProjectCustomField``:
       whether a field holds one value or several is a property of the attached
       field type, reported as ``field.fieldType.isMultiValue`` (alongside
       ``fieldType.id``, e.g. ``enum[1]`` or ``version[*]``). So the single/multi
       decision cannot be read off these strings — it has to be asked for, and
       naming a ``Multi…`` constant here describes a response that never occurs.
    """

    ENUM = "EnumProjectCustomField"
    STATE = "StateProjectCustomField"
    OWNED = "OwnedProjectCustomField"
    USER = "UserProjectCustomField"
    VERSION = "VersionProjectCustomField"
    BUILD = "BuildProjectCustomField"
    TEXT = "TextProjectCustomField"
    PERIOD = "PeriodProjectCustomField"
    DATE = "DateProjectCustomField"
    DATE_TIME = "DateTimeProjectCustomField"
    INTEGER = "SimpleProjectCustomField"
    FLOAT = "SimpleProjectCustomField"


class CustomFieldValueTypes:
    """Custom field value types."""

    ENUM_BUNDLE_ELEMENT = "EnumBundleElement"
    STATE_BUNDLE_ELEMENT = "StateBundleElement"
    VERSION_BUNDLE_ELEMENT = "VersionBundleElement"
    BUILD_BUNDLE_ELEMENT = "BuildBundleElement"
    OWNED_BUNDLE_ELEMENT = "OwnedBundleElement"
    USER = "User"
    PERIOD_VALUE = "PeriodValue"
    DATE_VALUE = "DateValue"
    INTEGER_VALUE = "IntegerValue"
    FLOAT_VALUE = "FloatValue"
    TEXT_VALUE = "TextValue"


class VisibilityTypes:
    """Visibility types for articles and other content."""

    UNLIMITED = "UnlimitedVisibility"
    LIMITED = "LimitedVisibility"


# Mapping for display purposes - converts API types to human-readable names
FIELD_TYPE_DISPLAY_MAP = {
    # Issue field types
    IssueCustomFieldTypes.SINGLE_ENUM: "Single Enum",
    IssueCustomFieldTypes.MULTI_ENUM: "Multi Enum",
    IssueCustomFieldTypes.STATE: "State",
    IssueCustomFieldTypes.SINGLE_USER: "Single User",
    IssueCustomFieldTypes.MULTI_USER: "Multi User",
    IssueCustomFieldTypes.SINGLE_VERSION: "Single Version",
    IssueCustomFieldTypes.MULTI_VERSION: "Multi Version",
    IssueCustomFieldTypes.SINGLE_BUILD: "Single Build",
    IssueCustomFieldTypes.MULTI_BUILD: "Multi Build",
    IssueCustomFieldTypes.SINGLE_OWNED: "Single Owned",
    IssueCustomFieldTypes.MULTI_OWNED: "Multi Owned",
    IssueCustomFieldTypes.TEXT: "Text",
    IssueCustomFieldTypes.PERIOD: "Period",
    IssueCustomFieldTypes.DATE: "Date",
    IssueCustomFieldTypes.DATE_TIME: "Date Time",
    IssueCustomFieldTypes.INTEGER: "Integer",
    IssueCustomFieldTypes.FLOAT: "Float",
    # Project field types
    ProjectCustomFieldTypes.ENUM: "Enum",
    ProjectCustomFieldTypes.STATE: "State",
    ProjectCustomFieldTypes.OWNED: "Owned",
    ProjectCustomFieldTypes.USER: "User",
    ProjectCustomFieldTypes.VERSION: "Version",
    ProjectCustomFieldTypes.BUILD: "Build",
    ProjectCustomFieldTypes.TEXT: "Text",
    ProjectCustomFieldTypes.PERIOD: "Period",
    ProjectCustomFieldTypes.DATE: "Date",
    ProjectCustomFieldTypes.DATE_TIME: "Date Time",
    ProjectCustomFieldTypes.INTEGER: "Integer",
    ProjectCustomFieldTypes.FLOAT: "Float",
}


def get_display_name(field_type: str) -> str:
    """
    Convert a YouTrack API field type to a human-readable display name.

    Args:
        field_type: The YouTrack API field type string

    Returns:
        Human-readable display name for the field type

    Examples:
        >>> get_display_name("SingleEnumIssueCustomField")
        'Single Enum'
        >>> get_display_name("TextIssueCustomField")
        'Text'
        >>> get_display_name("UnknownFieldType")
        'UnknownFieldType'
        >>> get_display_name("")
        ''
    """
    return FIELD_TYPE_DISPLAY_MAP.get(field_type, field_type)
