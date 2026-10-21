"""Tests for CustomFieldManager and custom field utilities."""

import pytest

from youtrack_cli.custom_field_manager import CustomFieldManager, resolve_bundle_value
from youtrack_cli.custom_field_types import (
    FIELD_TYPE_DISPLAY_MAP,
    CustomFieldValueTypes,
    IssueCustomFieldTypes,
    ProjectCustomFieldTypes,
    get_display_name,
)
from youtrack_cli.exceptions import (
    CustomFieldMultiplicityUnknownError,
    CustomFieldUnresolvedReason,
    CustomFieldValueAmbiguousError,
    CustomFieldValueCountError,
    CustomFieldValueTypeError,
    CustomFieldValueUnresolvedError,
    UnsupportedCustomFieldTypeError,
)


class TestCustomFieldTypes:
    """Test custom field type constants."""

    def test_issue_custom_field_types(self):
        """Test issue custom field type constants."""
        assert IssueCustomFieldTypes.SINGLE_ENUM == "SingleEnumIssueCustomField"
        assert IssueCustomFieldTypes.MULTI_ENUM == "MultiEnumIssueCustomField"
        assert IssueCustomFieldTypes.STATE == "StateIssueCustomField"
        assert IssueCustomFieldTypes.SINGLE_USER == "SingleUserIssueCustomField"
        assert IssueCustomFieldTypes.MULTI_USER == "MultiUserIssueCustomField"
        assert IssueCustomFieldTypes.TEXT == "TextIssueCustomField"

    def test_project_custom_field_types(self):
        """Test project custom field type constants.

        The project vocabulary names the *kind* of field and nothing more. Two rules
        follow from that, and both are load-bearing: a project type written like its
        issue counterpart ("SingleUserProjectCustomField") never matches a real API
        response, and a "Multi...ProjectCustomField" never matches one either --
        multiplicity is reported on the field's `fieldType`, not in the kind's name. A
        constant naming either describes a response the API does not produce.
        """
        assert ProjectCustomFieldTypes.ENUM == "EnumProjectCustomField"
        assert ProjectCustomFieldTypes.STATE == "StateProjectCustomField"
        assert ProjectCustomFieldTypes.OWNED == "OwnedProjectCustomField"
        assert ProjectCustomFieldTypes.USER == "UserProjectCustomField"
        assert ProjectCustomFieldTypes.VERSION == "VersionProjectCustomField"
        assert ProjectCustomFieldTypes.BUILD == "BuildProjectCustomField"

    def test_project_vocabulary_names_no_multiplicity(self):
        """No project constant may claim multiplicity, because none carries it.

        A `Multi*ProjectCustomField` constant is not merely unused: it invites a lookup
        keyed on multiplicity, which then matches nothing and falls through to whatever
        the miss defaults to.
        """
        names = [name for name in vars(ProjectCustomFieldTypes) if not name.startswith("_")]
        assert not [name for name in names if "MULTI" in name.upper()]
        values = {v for k, v in vars(ProjectCustomFieldTypes).items() if not k.startswith("_") and isinstance(v, str)}
        assert not [value for value in values if "Multi" in value]

    def test_project_types_are_not_issue_spellings(self):
        """No project constant may reuse an issue-side type name."""
        project_values = {
            v for k, v in vars(ProjectCustomFieldTypes).items() if not k.startswith("_") and isinstance(v, str)
        }
        issue_values = {
            v for k, v in vars(IssueCustomFieldTypes).items() if not k.startswith("_") and isinstance(v, str)
        }
        assert not (project_values & issue_values)

    def test_custom_field_value_types(self):
        """Test custom field value type constants."""
        assert CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT == "EnumBundleElement"
        assert CustomFieldValueTypes.STATE_BUNDLE_ELEMENT == "StateBundleElement"
        assert CustomFieldValueTypes.OWNED_BUNDLE_ELEMENT == "OwnedBundleElement"
        assert CustomFieldValueTypes.USER == "User"
        assert CustomFieldValueTypes.TEXT_VALUE == "TextValue"

    def test_get_display_name(self):
        """Test display name formatting."""
        assert get_display_name("SingleEnumIssueCustomField") == "Single Enum"
        assert get_display_name("MultiUserIssueCustomField") == "Multi User"
        assert get_display_name("UserProjectCustomField") == "User"
        assert get_display_name("UnknownType") == "UnknownType"

    def test_field_type_display_map_completeness(self):
        """Test that all field types have display mappings."""
        # Test some key field types
        assert "SingleEnumIssueCustomField" in FIELD_TYPE_DISPLAY_MAP
        assert "MultiUserIssueCustomField" in FIELD_TYPE_DISPLAY_MAP
        assert FIELD_TYPE_DISPLAY_MAP["SingleEnumIssueCustomField"] == "Single Enum"

    def test_display_map_covers_every_declared_type(self):
        """Every constant in both vocabularies must resolve to a name of its own.

        A constant added without a display entry renders as its raw API string, which
        is the one output a reader cannot act on -- so the two classes are compared
        against the map rather than spot-checked.
        """
        for vocabulary in (IssueCustomFieldTypes, ProjectCustomFieldTypes):
            for name, value in vars(vocabulary).items():
                if name.startswith("_") or not isinstance(value, str):
                    continue
                assert value in FIELD_TYPE_DISPLAY_MAP, f"{vocabulary.__name__}.{name} has no display name"
                assert get_display_name(value) != value, f"{vocabulary.__name__}.{name} renders as its raw type"


class TestCustomFieldManager:
    """Test CustomFieldManager functionality."""

    def test_create_single_enum_field(self):
        """Test creating single enum custom field."""
        field = CustomFieldManager.create_single_enum_field("Priority", "High")

        expected = {
            "$type": "SingleEnumIssueCustomField",
            "name": "Priority",
            "value": {"$type": "EnumBundleElement", "name": "High"},
        }

        assert field == expected

    def test_create_multi_enum_field(self):
        """Test creating multi enum custom field."""
        field = CustomFieldManager.create_multi_enum_field("Tags", ["bug", "urgent"])

        expected = {
            "$type": "MultiEnumIssueCustomField",
            "name": "Tags",
            "value": [{"$type": "EnumBundleElement", "name": "bug"}, {"$type": "EnumBundleElement", "name": "urgent"}],
        }

        assert field == expected

    def test_create_state_field(self):
        """Test creating state custom field."""
        field = CustomFieldManager.create_state_field("State", "Open")

        expected = {
            "$type": "StateIssueCustomField",
            "name": "State",
            "value": {"$type": "StateBundleElement", "name": "Open"},
        }

        assert field == expected

    def test_create_single_user_field(self):
        """Test creating single user custom field."""
        field = CustomFieldManager.create_single_user_field("Assignee", "john.doe")

        expected = {
            "$type": "SingleUserIssueCustomField",
            "name": "Assignee",
            "value": {"$type": "User", "login": "john.doe"},
        }

        assert field == expected

    def test_create_multi_user_field(self):
        """Test creating multi user custom field."""
        field = CustomFieldManager.create_multi_user_field("Reviewers", ["john.doe", "jane.smith"])

        expected = {
            "$type": "MultiUserIssueCustomField",
            "name": "Reviewers",
            "value": [{"$type": "User", "login": "john.doe"}, {"$type": "User", "login": "jane.smith"}],
        }

        assert field == expected

    def test_create_text_field(self):
        """Test creating text custom field."""
        field = CustomFieldManager.create_text_field("Description", "Test description")

        expected = {
            "$type": "TextIssueCustomField",
            "name": "Description",
            "value": {"$type": "TextValue", "text": "Test description"},
        }

        assert field == expected

    def test_extract_field_value_simple(self):
        """Test extracting simple field value."""
        custom_fields = [{"name": "Priority", "value": {"name": "High"}}]

        result = CustomFieldManager.extract_field_value(custom_fields, "Priority")
        assert result == "High"

    def test_extract_field_value_user(self):
        """Test extracting user field value."""
        custom_fields = [{"name": "Assignee", "value": {"login": "john.doe", "fullName": "John Doe"}}]

        result = CustomFieldManager.extract_field_value(custom_fields, "Assignee")
        assert result == "John Doe"  # fullName takes precedence according to priority order

    def test_extract_field_value_multi_value(self):
        """Test extracting multi-value field."""
        custom_fields = [{"name": "Tags", "value": [{"name": "bug"}, {"name": "urgent"}]}]

        result = CustomFieldManager.extract_field_value(custom_fields, "Tags")
        assert result == "bug, urgent"

    def test_extract_field_value_not_found(self):
        """Test extracting non-existent field."""
        custom_fields = [{"name": "Priority", "value": {"name": "High"}}]

        result = CustomFieldManager.extract_field_value(custom_fields, "NonExistent")
        assert result is None

    def test_extract_field_value_empty_list(self):
        """Test extracting from empty custom fields list."""
        result = CustomFieldManager.extract_field_value([], "Priority")
        assert result is None

    def test_extract_field_value_none_input(self):
        """Test extracting from None input."""
        result = CustomFieldManager.extract_field_value(None, "Priority")  # type: ignore
        assert result is None

    def test_get_field_id(self):
        """Test getting field ID."""
        custom_fields = [
            {"id": "field-123", "name": "Priority", "value": {"name": "High"}},
            {"id": "field-456", "name": "Assignee", "value": {"login": "john.doe"}},
        ]

        result = CustomFieldManager.get_field_id(custom_fields, "Priority")
        assert result == "field-123"

        result = CustomFieldManager.get_field_id(custom_fields, "Assignee")
        assert result == "field-456"

        result = CustomFieldManager.get_field_id(custom_fields, "NonExistent")
        assert result is None

    def test_format_field_type_for_display(self):
        """Test field type display formatting."""
        result = CustomFieldManager.format_field_type_for_display("SingleEnumIssueCustomField")
        assert result == "Single Enum"

        result = CustomFieldManager.format_field_type_for_display("UnknownType")
        assert result == "UnknownType"

    def test_get_field_with_fallback_primary_field(self):
        """Test getting field with fallback - primary field exists."""
        issue = {"priority": {"name": "High"}, "customFields": [{"name": "Priority", "value": {"name": "Medium"}}]}

        result = CustomFieldManager.get_field_with_fallback(issue, "priority", "Priority")
        assert result == {"name": "High"}

    def test_get_field_with_fallback_custom_field(self):
        """Test getting field with fallback - fallback to custom field."""
        issue = {"customFields": [{"name": "Priority", "value": {"name": "High"}}]}

        result = CustomFieldManager.get_field_with_fallback(issue, "priority", "Priority")
        assert result == "High"

    def test_get_field_with_fallback_none(self):
        """Test getting field with fallback - no field found."""
        issue = {"customFields": []}

        result = CustomFieldManager.get_field_with_fallback(issue, "priority", "Priority")
        assert result is None

    def test_create_project_enum_field_config(self):
        """Test creating project enum field configuration."""
        config = CustomFieldManager.create_project_enum_field_config(
            field_type="EnumProjectCustomField", can_be_empty=False, empty_field_text="Required field", is_public=True
        )

        expected = {
            "$type": "EnumProjectCustomField",
            "canBeEmpty": False,
            "emptyFieldText": "Required field",
            "isPublic": True,
        }

        assert config == expected

    def test_create_project_enum_field_config_defaults(self):
        """Test creating project enum field configuration with defaults."""
        config = CustomFieldManager.create_project_enum_field_config("EnumProjectCustomField")

        expected = {
            "$type": "EnumProjectCustomField",
            "canBeEmpty": True,
            "emptyFieldText": "No value",
            "isPublic": True,
        }

        assert config == expected

    def test_extract_user_field_info(self):
        """Test extracting comprehensive user information."""
        user_value = {
            "login": "john.doe",
            "fullName": "John Doe",
            "name": "John",
            "email": "john@example.com",
            "avatarUrl": "https://example.com/avatar.jpg",
        }

        result = CustomFieldManager.extract_user_field_info(user_value)

        expected = {
            "login": "john.doe",
            "fullName": "John Doe",
            "name": "John",
            "email": "john@example.com",
            "avatarUrl": "https://example.com/avatar.jpg",
        }

        assert result == expected

    def test_extract_user_field_info_empty(self):
        """Test extracting user info from empty dict."""
        result = CustomFieldManager.extract_user_field_info({})

        expected = {"login": "", "fullName": "", "name": "", "email": "", "avatarUrl": ""}

        assert result == expected

    def test_extract_user_field_info_non_dict(self):
        """Test extracting user info from non-dict input."""
        result = CustomFieldManager.extract_user_field_info("not_a_dict")  # type: ignore
        assert result == {}

    def test_is_multi_value_field(self):
        """Test checking if field type is multi-value.

        Only the issue-side vocabulary answers this: the project admin API names the
        kind of a field and reports multiplicity on the field's `fieldType`, so there is
        no project-side spelling to ask about. The project rows below are the negative
        case -- a project kind asked here is answered False whatever the field is,
        which is why discovery reads `isMultiValue` instead.
        """
        assert CustomFieldManager.is_multi_value_field("MultiEnumIssueCustomField") is True
        assert CustomFieldManager.is_multi_value_field("MultiUserIssueCustomField") is True
        assert CustomFieldManager.is_multi_value_field("MultiVersionIssueCustomField") is True
        assert CustomFieldManager.is_multi_value_field("MultiBuildIssueCustomField") is True
        assert CustomFieldManager.is_multi_value_field("MultiOwnedIssueCustomField") is True

        assert CustomFieldManager.is_multi_value_field("SingleEnumIssueCustomField") is False
        assert CustomFieldManager.is_multi_value_field("SingleUserIssueCustomField") is False
        assert CustomFieldManager.is_multi_value_field("StateIssueCustomField") is False
        assert CustomFieldManager.is_multi_value_field("VersionProjectCustomField") is False

    def test_extract_dict_value_priority_order(self):
        """Test that _extract_dict_value follows priority order."""
        # Test presentation has highest priority
        value = {"presentation": "Presentation Value", "fullName": "Full Name", "name": "Name"}
        result = CustomFieldManager._extract_dict_value(value)
        assert result == "Presentation Value"

        # Test fullName has second priority when presentation is not present
        value = {"fullName": "Full Name", "name": "Name"}
        result = CustomFieldManager._extract_dict_value(value)
        assert result == "Full Name"

        # Test name as fallback
        value = {"name": "Name"}
        result = CustomFieldManager._extract_dict_value(value)
        assert result == "Name"

    def test_extract_dict_value_list_input(self):
        """Test _extract_dict_value with list input."""
        value = [{"name": "Item 1"}, {"name": "Item 2"}]
        result = CustomFieldManager._extract_dict_value(value)
        assert result == "Item 1, Item 2"

    def test_extract_dict_value_primitive_input(self):
        """Test _extract_dict_value with primitive input."""
        assert CustomFieldManager._extract_dict_value("string") == "string"
        assert CustomFieldManager._extract_dict_value(42) == 42
        assert CustomFieldManager._extract_dict_value(True) is True

    def test_extract_dict_value_color_field(self):
        """Test _extract_dict_value with color field."""
        value = {"color": {"id": "color-123"}}
        result = CustomFieldManager._extract_dict_value(value)
        assert result == "color-123"

    def test_extract_dict_value_boolean_field(self):
        """Test _extract_dict_value with boolean field."""
        value = {"isResolved": True}
        result = CustomFieldManager._extract_dict_value(value)
        assert result == "True"


class TestCreateFieldByType:
    """Test payload construction from discovered field information."""

    @staticmethod
    def _info(project_type, issue_type, element_type=None, unresolved=None):
        return {
            "project_field_type": project_type,
            "issue_field_type": issue_type,
            "bundle_element_type": element_type,
            "unresolved_reason": unresolved,
        }

    @pytest.mark.parametrize(
        ("issue_type", "expected"),
        [
            (
                IssueCustomFieldTypes.SINGLE_USER,
                {"$type": "SingleUserIssueCustomField", "name": "F", "value": {"$type": "User", "login": "v"}},
            ),
            (
                IssueCustomFieldTypes.SINGLE_VERSION,
                {
                    "$type": "SingleVersionIssueCustomField",
                    "name": "F",
                    "value": {"$type": "VersionBundleElement", "name": "v"},
                },
            ),
            (
                IssueCustomFieldTypes.SINGLE_BUILD,
                {
                    "$type": "SingleBuildIssueCustomField",
                    "name": "F",
                    "value": {"$type": "BuildBundleElement", "name": "v"},
                },
            ),
            (
                IssueCustomFieldTypes.TEXT,
                {"$type": "TextIssueCustomField", "name": "F", "value": {"$type": "TextValue", "text": "v"}},
            ),
        ],
    )
    def test_builds_the_discovered_type(self, issue_type, expected):
        assert (
            CustomFieldManager.create_field_by_type(self._info("XProjectCustomField", issue_type), "F", "v") == expected
        )

    def test_numeric_and_state_fields_take_their_own_value_shape(self):
        """A numeric field is coerced to a number; a state field is bundle-backed.

        Neither is bundle-shaped in the same way as the kinds above, and both take a
        single value -- so the value each one puts on the wire is pinned here rather
        than assumed to be a bundle element.
        """
        assert CustomFieldManager.create_field_by_type(
            self._info(ProjectCustomFieldTypes.INTEGER, IssueCustomFieldTypes.INTEGER),
            "Story Points",
            ["8"],
        ) == {"$type": "SimpleIssueCustomField", "name": "Story Points", "value": 8}

        assert CustomFieldManager.create_field_by_type(
            self._info(ProjectCustomFieldTypes.STATE, IssueCustomFieldTypes.STATE),
            "State",
            ["In Progress"],
        ) == {
            "$type": "StateIssueCustomField",
            "name": "State",
            "value": {"$type": "StateBundleElement", "name": "In Progress"},
        }

    def test_owned_field_uses_its_own_type_and_bundle(self):
        """An owned field is not enum-shaped: it has its own issue type and value type."""
        result = CustomFieldManager.create_field_by_type(
            self._info(ProjectCustomFieldTypes.OWNED, IssueCustomFieldTypes.SINGLE_OWNED), "Team", "core"
        )
        assert result == {
            "$type": "SingleOwnedIssueCustomField",
            "name": "Team",
            "value": {"$type": "OwnedBundleElement", "name": "core"},
        }

    def test_discovered_element_type_is_used_for_enum_fields(self):
        """A bundle that reports its element type is authoritative for an enum field."""
        result = CustomFieldManager.create_field_by_type(
            self._info(
                ProjectCustomFieldTypes.ENUM,
                IssueCustomFieldTypes.SINGLE_ENUM,
                element_type=CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT,
            ),
            "Repo",
            "root",
        )
        assert result["value"]["$type"] == CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT

    def test_multi_valued_type_is_written_as_a_list(self):
        """A field that holds several takes a list, so one value is a one-element list.

        This is the case the CLI used to refuse outright. It is writable, and refusing it
        sent users to the web UI for a field the API answers exactly.
        """
        result = CustomFieldManager.create_field_by_type(
            self._info(ProjectCustomFieldTypes.VERSION, IssueCustomFieldTypes.MULTI_VERSION),
            "Fix versions",
            "1.0",
        )
        assert result == {
            "$type": "MultiVersionIssueCustomField",
            "name": "Fix versions",
            "value": [{"$type": "VersionBundleElement", "name": "1.0"}],
        }

    @pytest.mark.parametrize(
        ("project_type", "issue_type", "expected_type", "element_type", "value_key"),
        [
            (
                ProjectCustomFieldTypes.ENUM,
                IssueCustomFieldTypes.MULTI_ENUM,
                "MultiEnumIssueCustomField",
                "EnumBundleElement",
                "name",
            ),
            (
                ProjectCustomFieldTypes.USER,
                IssueCustomFieldTypes.MULTI_USER,
                "MultiUserIssueCustomField",
                "User",
                "login",
            ),
            (
                ProjectCustomFieldTypes.VERSION,
                IssueCustomFieldTypes.MULTI_VERSION,
                "MultiVersionIssueCustomField",
                "VersionBundleElement",
                "name",
            ),
            (
                ProjectCustomFieldTypes.BUILD,
                IssueCustomFieldTypes.MULTI_BUILD,
                "MultiBuildIssueCustomField",
                "BuildBundleElement",
                "name",
            ),
            (
                ProjectCustomFieldTypes.OWNED,
                IssueCustomFieldTypes.MULTI_OWNED,
                "MultiOwnedIssueCustomField",
                "OwnedBundleElement",
                "name",
            ),
        ],
    )
    def test_every_multi_valued_kind_keeps_its_own_value_type(
        self, project_type, issue_type, expected_type, element_type, value_key
    ):
        """Each multi-valued kind carries its own element type and its own value key.

        An owned value sent as an enum element is rejected as a type mismatch, and a
        user value is a login rather than a name, so the list form is only correct if it
        keeps both of the things the single-valued form gets from the kind.
        """
        result = CustomFieldManager.create_field_by_type(self._info(project_type, issue_type), "F", ["a", "b"])
        assert result["$type"] == expected_type
        assert [element["$type"] for element in result["value"]] == [element_type, element_type]
        assert [element[value_key] for element in result["value"]] == ["a", "b"]

    def test_multi_user_values_are_resolved_by_login(self):
        """A user value is a login, and the list form is no different from the single one."""
        result = CustomFieldManager.create_field_by_type(
            self._info(ProjectCustomFieldTypes.USER, IssueCustomFieldTypes.MULTI_USER),
            "Reviewers",
            ["ann", "bo"],
        )
        assert result["value"] == [
            {"$type": "User", "login": "ann"},
            {"$type": "User", "login": "bo"},
        ]

    def test_discovered_element_type_is_used_for_multi_enum_fields(self):
        """A bundle that reports its element type is authoritative for a multi enum too."""
        result = CustomFieldManager.create_field_by_type(
            self._info(
                ProjectCustomFieldTypes.ENUM,
                IssueCustomFieldTypes.MULTI_ENUM,
                element_type="StateBundleElement",
            ),
            "Sprint",
            ["S1"],
        )
        assert result["value"] == [{"$type": "StateBundleElement", "name": "S1"}]

    def test_empty_bundle_defaults_the_multi_enum_element_type(self):
        """An empty bundle reports nothing, so the default stands -- as it does for single."""
        result = CustomFieldManager.create_field_by_type(
            self._info(ProjectCustomFieldTypes.ENUM, IssueCustomFieldTypes.MULTI_ENUM, element_type=None),
            "Sprint",
            ["S1"],
        )
        assert result["value"] == [{"$type": "EnumBundleElement", "name": "S1"}]

    @pytest.mark.parametrize(
        ("project_type", "issue_type"),
        [
            (ProjectCustomFieldTypes.USER, IssueCustomFieldTypes.SINGLE_USER),
            (ProjectCustomFieldTypes.OWNED, IssueCustomFieldTypes.SINGLE_OWNED),
            (ProjectCustomFieldTypes.VERSION, IssueCustomFieldTypes.SINGLE_VERSION),
            (ProjectCustomFieldTypes.BUILD, IssueCustomFieldTypes.SINGLE_BUILD),
            (ProjectCustomFieldTypes.ENUM, IssueCustomFieldTypes.SINGLE_ENUM),
            (ProjectCustomFieldTypes.TEXT, IssueCustomFieldTypes.TEXT),
            (ProjectCustomFieldTypes.INTEGER, IssueCustomFieldTypes.INTEGER),
            (ProjectCustomFieldTypes.STATE, IssueCustomFieldTypes.STATE),
        ],
    )
    def test_several_values_for_a_single_valued_field_are_refused(self, project_type, issue_type):
        """Every value given is a statement, so all but the last cannot be silently dropped.

        Keeping the last would report success for a request that did not say what it
        meant, and the caller would have no way to know a value was dropped.
        """
        with pytest.raises(CustomFieldValueCountError) as exc:
            CustomFieldManager.create_field_by_type(self._info(project_type, issue_type), "Repo", ["a", "b"])
        message = str(exc.value)
        assert "2 were given" in message
        assert "'a'" in message and "'b'" in message

    def test_a_single_value_for_a_single_valued_field_is_unchanged(self):
        """The one-value case must not be caught by the count refusal."""
        result = CustomFieldManager.create_field_by_type(
            self._info(ProjectCustomFieldTypes.VERSION, IssueCustomFieldTypes.SINGLE_VERSION), "F", ["1.0"]
        )
        assert result["value"] == {"$type": "VersionBundleElement", "name": "1.0"}

    def test_no_values_at_all_is_refused_rather_than_writing_an_empty_field(self):
        """An empty list is not a request the caller can have meant.

        `-cf "Field="` is rejected at the CLI boundary, so an empty list here means a
        caller built one -- and writing it would clear a field on the strength of nothing.
        """
        with pytest.raises(CustomFieldValueCountError):
            CustomFieldManager.create_field_by_type(
                self._info(ProjectCustomFieldTypes.ENUM, IssueCustomFieldTypes.SINGLE_ENUM), "Repo", []
            )

    @pytest.mark.parametrize(
        "issue_type",
        [IssueCustomFieldTypes.SINGLE_ENUM, IssueCustomFieldTypes.MULTI_VERSION],
    )
    def test_the_empty_value_refusal_does_not_claim_what_the_field_holds(self, issue_type):
        """The message must not assert a multiplicity it has not been told.

        Wording the empty case as "it holds a single value" is false for a multi-valued
        field, and the advice that would follow it ("pass one value") is wrong for
        exactly that field -- so the message states only that no value arrived.
        """
        with pytest.raises(CustomFieldValueCountError) as exc:
            CustomFieldManager.create_field_by_type(
                self._info(ProjectCustomFieldTypes.VERSION, issue_type), "Fix versions", []
            )
        message = str(exc.value)
        assert "no value was given" in message
        assert "single value" not in message
        assert "0 were given" not in message

    @pytest.mark.parametrize(
        ("project_type", "field_name", "unresolved", "expected"),
        [
            # A kind this CLI cannot write, whatever the value.
            ("DateProjectCustomField", "Due", None, UnsupportedCustomFieldTypeError),
            # A bundle-backed kind whose multiplicity the server did not report.
            (
                ProjectCustomFieldTypes.ENUM,
                "Sprint",
                CustomFieldUnresolvedReason.MULTIPLICITY,
                CustomFieldMultiplicityUnknownError,
            ),
        ],
    )
    def test_an_unresolved_field_is_blamed_before_an_absent_value(self, project_type, field_name, unresolved, expected):
        """No value at all must not outrank a field that cannot be written anyway.

        Both refusals send nothing, so only the diagnosis is at stake -- and the wrong
        one sends the reader after a value they never supplied, with the real cause
        surfacing only on the next attempt. Reachable: `yt batch create --file` forwards
        an empty JSON list verbatim, since it filters only `None`.

        The two rows use kinds discovery can actually produce those reasons for: a date
        field resolves to no issue type, and a bundle-backed kind is the only one whose
        unreported multiplicity is reported as such.
        """
        with pytest.raises(expected) as exc:
            CustomFieldManager.create_field_by_type(
                self._info(project_type, None, unresolved=unresolved), field_name, []
            )
        assert "no value was given" not in str(exc.value)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (8, 8),
            (8.5, 8.5),
            ("8", 8),
            (["8"], 8),
        ],
    )
    def test_a_numeric_value_is_one_value_not_something_to_iterate(self, value, expected):
        """A non-sequence is one value whatever its type.

        `yt batch create --file items.json` forwards every non-null field from a JSON row
        verbatim, so a numeric custom field arrives as a number. Treating anything that is
        not a string as a list of values made that raise `TypeError: 'int' object is not
        iterable`, which is not a refusal and so escaped the handlers that name the field.
        """
        result = CustomFieldManager.create_field_by_type(
            self._info(ProjectCustomFieldTypes.INTEGER, IssueCustomFieldTypes.INTEGER), "Story Points", value
        )
        assert result["$type"] == "SimpleIssueCustomField"
        # Compared by type as well as value: `8 == 8.0`, so an equality check alone would
        # pass against an implementation that coerced every number to a float.
        assert result["value"] == expected
        assert type(result["value"]) is type(expected)

    @pytest.mark.parametrize(
        ("value", "described"),
        [
            (True, "bool"),
            ({"a": 1}, "dict"),
            (None, "NoneType"),
            (["a", ["b"]], "list"),
        ],
    )
    def test_a_value_no_builder_can_state_is_refused(self, value, described):
        """Refused rather than coerced, and the message names the type it was given.

        A bool is an `int` to `isinstance`, so a numeric field would otherwise take `true`
        as 1 and report success; an object would be stringified. `yt batch` forwards every
        non-null field of a JSON row verbatim, so these arrive rather than being caught
        at the command line.
        """
        with pytest.raises(CustomFieldValueTypeError) as exc:
            CustomFieldManager.create_field_by_type(
                self._info(ProjectCustomFieldTypes.INTEGER, IssueCustomFieldTypes.INTEGER), "Effort", value
            )
        message = str(exc.value)
        assert described in message
        assert "Effort" in message

    def test_an_unsupported_field_is_blamed_before_its_values_are(self):
        """A field this CLI cannot write is the real cause, whatever the value looks like.

        Reporting the value instead points the reader at their input file, and the real
        cause only surfaces on the next attempt -- with the same result and less
        information.
        """
        with pytest.raises(UnsupportedCustomFieldTypeError) as exc:
            CustomFieldManager.create_field_by_type(self._info("DateProjectCustomField", None), "Due", {"year": 2026})
        assert "DateProjectCustomField" in str(exc.value)
        assert "dict" not in str(exc.value)

    def test_unreported_multiplicity_is_also_blamed_before_the_values(self):
        with pytest.raises(CustomFieldMultiplicityUnknownError) as exc:
            CustomFieldManager.create_field_by_type(
                self._info(
                    ProjectCustomFieldTypes.ENUM,
                    None,
                    unresolved=CustomFieldUnresolvedReason.MULTIPLICITY,
                ),
                "Sprint",
                {"name": "S1"},
            )
        assert "one value or several" in str(exc.value)
        assert "dict" not in str(exc.value)

    @pytest.mark.parametrize("value", [b"ab", bytearray(b"ab"), memoryview(b"ab")])
    def test_byte_like_values_are_refused_rather_than_read_as_several_numbers(self, value):
        """`bytes` is excluded from the sequence gate, so its siblings must be too.

        `bytearray(b"ab")` is a `Sequence` of `int` and not `bytes`, so it was expanded
        into two values -- and written as bundle elements named 97 and 98.
        """
        with pytest.raises(CustomFieldValueTypeError):
            CustomFieldManager.create_field_by_type(
                self._info(ProjectCustomFieldTypes.VERSION, IssueCustomFieldTypes.MULTI_VERSION),
                "Fix versions",
                value,
            )

    def test_a_tuple_of_values_is_treated_as_several_values(self):
        """Sequences are read as value lists, whatever sequence type carries them."""
        result = CustomFieldManager.create_field_by_type(
            self._info(ProjectCustomFieldTypes.VERSION, IssueCustomFieldTypes.MULTI_VERSION),
            "Fix versions",
            ("1.0", "1.1"),
        )
        assert [element["name"] for element in result["value"]] == ["1.0", "1.1"]

    def test_unreported_multiplicity_is_refused_as_its_own_cause(self):
        """Naming it "unknown type" would blame the vocabulary for a missing server field."""
        with pytest.raises(CustomFieldMultiplicityUnknownError) as exc:
            CustomFieldManager.create_field_by_type(
                self._info(
                    ProjectCustomFieldTypes.ENUM,
                    None,
                    unresolved=CustomFieldUnresolvedReason.MULTIPLICITY,
                ),
                "Sprint",
                "S1",
            )
        message = str(exc.value)
        assert "one value or several" in message
        assert "EnumProjectCustomField" in message

    def test_unmappable_type_raises_instead_of_guessing_enum(self):
        """Refusing is the point: a guessed enum is rejected by the server as a type error."""
        with pytest.raises(UnsupportedCustomFieldTypeError) as exc:
            CustomFieldManager.create_field_by_type(self._info("SomethingNewProjectCustomField", None), "Mystery", "x")
        assert "Mystery" in str(exc.value)
        assert "SomethingNewProjectCustomField" in str(exc.value)


class TestResolveBundleValue:
    """Which form a token is, decided by the field's own vocabulary.

    The form is never decided by the token's shape: a legal value *name* can look
    exactly like an id, and a rule that recognised ids by their pattern would
    mis-address such a name.
    """

    PRIORITY = [
        {"id": "157-1", "name": "Critical"},
        {"id": "157-2", "name": "Major"},
    ]

    def test_a_name_is_a_name(self):
        assert resolve_bundle_value("Critical", self.PRIORITY, "Priority") == ("name", "Critical")

    def test_an_id_is_an_id(self):
        assert resolve_bundle_value("157-2", self.PRIORITY, "Priority") == ("id", "157-2")

    def test_an_unknown_token_is_refused(self):
        with pytest.raises(CustomFieldValueUnresolvedError) as exc:
            resolve_bundle_value("157-9", self.PRIORITY, "Priority")
        message = str(exc.value)
        assert "not a valid Priority" in message
        assert "Critical (157-1)" in message, "the legal values are named with the ids they answer to"

    def test_a_token_that_is_both_a_name_and_an_id_is_refused(self):
        """Neither reading can be chosen, so neither is chosen."""
        vocabulary = [{"id": "157-2", "name": "157-2"}]

        with pytest.raises(CustomFieldValueAmbiguousError) as exc:
            resolve_bundle_value("157-2", vocabulary, "Priority")
        assert "ambiguously" in str(exc.value)

    def test_a_field_with_no_values_reports_that_rather_than_a_bare_list(self):
        with pytest.raises(CustomFieldValueUnresolvedError) as exc:
            resolve_bundle_value("anything", [], "Fix versions")
        assert "no values" in str(exc.value)


class TestBundleValuesByNameOrId:
    """What a bundle-backed builder puts on the wire, for both forms of a value.

    An id goes on the wire as the id, not as the name it currently has: the id is the
    only identifier a rename cannot invalidate, and the CLI caches field discovery for
    five minutes, so a name resolved through the cache could be a stale one.
    """

    PRIORITY = [
        {"id": "157-1", "name": "Critical"},
        {"id": "157-2", "name": "Major"},
    ]

    @staticmethod
    def _info(issue_type, values, element_type=CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT, project_type=None):
        """A discovered field, with the bundle discovery reported."""
        return {
            "project_field_type": project_type or ProjectCustomFieldTypes.ENUM,
            "issue_field_type": issue_type,
            "bundle_element_type": element_type,
            "field_details": {"bundle": {"values": values}},
        }

    def test_an_id_is_written_as_an_id(self):
        result = CustomFieldManager.create_field_by_type(
            self._info(IssueCustomFieldTypes.SINGLE_ENUM, self.PRIORITY), "Priority", "157-2"
        )
        assert result == {
            "$type": IssueCustomFieldTypes.SINGLE_ENUM,
            "name": "Priority",
            "value": {"$type": CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT, "id": "157-2"},
        }

    def test_a_name_is_still_written_as_a_name(self):
        result = CustomFieldManager.create_field_by_type(
            self._info(IssueCustomFieldTypes.SINGLE_ENUM, self.PRIORITY), "Priority", "Major"
        )
        assert result == {
            "$type": IssueCustomFieldTypes.SINGLE_ENUM,
            "name": "Priority",
            "value": {"$type": CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT, "name": "Major"},
        }

    def test_an_id_of_another_fields_bundle_is_refused_rather_than_written(self):
        """The most dangerous thing a resolver could do is pass any id through.

        An id belongs to the field whose vocabulary carries it, so writing one against
        another field is a write to a value that does not exist there.
        """
        with pytest.raises(CustomFieldValueUnresolvedError) as exc:
            CustomFieldManager.create_field_by_type(
                self._info(IssueCustomFieldTypes.SINGLE_ENUM, self.PRIORITY), "Priority", "159-2"
            )
        assert "not a valid Priority" in str(exc.value)

    def test_a_multi_valued_field_takes_a_mix_of_names_and_ids(self):
        result = CustomFieldManager.create_field_by_type(
            self._info(IssueCustomFieldTypes.MULTI_ENUM, self.PRIORITY), "Priority", ["Critical", "157-2"]
        )
        assert result["value"] == [
            {"$type": CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT, "name": "Critical"},
            {"$type": CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT, "id": "157-2"},
        ]

    @pytest.mark.parametrize(
        ("issue_type", "project_type", "element_type", "field_name", "value_name", "value_id"),
        [
            (
                IssueCustomFieldTypes.MULTI_VERSION,
                ProjectCustomFieldTypes.VERSION,
                CustomFieldValueTypes.VERSION_BUNDLE_ELEMENT,
                "Fix versions",
                "2026-1",
                "133-24",
            ),
            (
                IssueCustomFieldTypes.MULTI_BUILD,
                ProjectCustomFieldTypes.BUILD,
                CustomFieldValueTypes.BUILD_BUNDLE_ELEMENT,
                "Fixed in build",
                "2026.1",
                "133-25",
            ),
            (
                IssueCustomFieldTypes.MULTI_OWNED,
                ProjectCustomFieldTypes.OWNED,
                CustomFieldValueTypes.OWNED_BUNDLE_ELEMENT,
                "Subsystem",
                "Backend",
                "133-26",
            ),
        ],
    )
    def test_a_multi_valued_field_of_any_kind_takes_a_mix_of_names_and_ids(
        self, issue_type, project_type, element_type, field_name, value_name, value_id
    ):
        """Every multi-valued builder resolves its own list, and each value in it.

        The version, build and owned builders are separate code from the enum one, so
        the enum mix test says nothing about them. A builder that decided the form
        once for the whole list -- taking the first value's form for every value --
        would write the second value in the first value's form, and the value the
        caller named by id would reach the server as a name that does not exist.
        """
        values = [{"id": value_id, "name": value_name}]
        result = CustomFieldManager.create_field_by_type(
            self._info(issue_type, values, element_type=element_type, project_type=project_type),
            field_name,
            [value_name, value_id],
        )
        assert result["value"] == [
            {"$type": element_type, "name": value_name},
            {"$type": element_type, "id": value_id},
        ]

    def test_a_state_field_by_id(self):
        states = [{"id": "159-2", "name": "In Progress"}]
        result = CustomFieldManager.create_field_by_type(
            self._info(
                IssueCustomFieldTypes.STATE,
                states,
                element_type=CustomFieldValueTypes.STATE_BUNDLE_ELEMENT,
            ),
            "State",
            "159-2",
        )
        assert result == {
            "$type": IssueCustomFieldTypes.STATE,
            "name": "State",
            "value": {"$type": CustomFieldValueTypes.STATE_BUNDLE_ELEMENT, "id": "159-2"},
        }

    def test_one_grammar_both_forms(self):
        """Both forms address the same field, with the same type, in the same payload.

        The only difference is which key carries the value -- which is the whole claim:
        there is one grammar for a field value, and a name and an id are two ways of
        saying the same thing in it.
        """
        states = [{"id": "159-2", "name": "In Progress"}]
        info = self._info(
            IssueCustomFieldTypes.STATE,
            states,
            element_type=CustomFieldValueTypes.STATE_BUNDLE_ELEMENT,
        )

        by_name = CustomFieldManager.create_field_by_type(info, "State", "In Progress")
        by_id = CustomFieldManager.create_field_by_type(info, "State", "159-2")

        assert by_name["name"] == by_id["name"] == "State"
        assert by_name["$type"] == by_id["$type"]
        assert by_name["value"]["$type"] == by_id["value"]["$type"]
        assert by_name["value"] == {"$type": CustomFieldValueTypes.STATE_BUNDLE_ELEMENT, "name": "In Progress"}
        assert by_id["value"] == {"$type": CustomFieldValueTypes.STATE_BUNDLE_ELEMENT, "id": "159-2"}

    def test_a_name_that_looks_like_an_id_stays_a_name(self):
        """A version field routinely carries names like `2026-1`.

        A rule that recognised ids by their pattern would take `2026-1` for an id and
        write the wrong thing -- or write nothing at all, because `2026-1` is not an
        id of that bundle either.
        """
        versions = [{"id": "133-24", "name": "2026-1"}]
        result = CustomFieldManager.create_field_by_type(
            self._info(
                IssueCustomFieldTypes.SINGLE_VERSION,
                versions,
                element_type=CustomFieldValueTypes.VERSION_BUNDLE_ELEMENT,
            ),
            "Fix versions",
            "2026-1",
        )
        assert result["value"] == {"$type": CustomFieldValueTypes.VERSION_BUNDLE_ELEMENT, "name": "2026-1"}

    def test_a_field_with_no_vocabulary_is_written_by_name(self):
        """With no values in hand there is no id the token could have meant.

        A field whose bundle reports no values -- a version field with no versions
        attached, say -- has nothing to resolve against, so the value is written by
        name and the server stays the authority on whether that name exists.
        """
        result = CustomFieldManager.create_field_by_type(
            self._info(IssueCustomFieldTypes.SINGLE_VERSION, []), "Fix versions", "1.0"
        )
        assert result["value"] == {"$type": CustomFieldValueTypes.VERSION_BUNDLE_ELEMENT, "name": "1.0"}
