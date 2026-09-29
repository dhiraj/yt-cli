"""Tests for field selection optimization functionality."""

from unittest.mock import Mock, patch

from youtrack_cli.field_selection import (
    FIELD_PROFILES,
    FieldProfile,
    FieldSelector,
    find_missing_fields,
    get_field_selector,
    parse_field_expression,
)


class TestFieldProfile:
    """Test field profile functionality."""

    def test_field_profile_creation(self):
        """Test creating a field profile."""
        fields = ["id", "summary", "state(name)"]
        profile = FieldProfile("issues", "minimal", fields)

        assert profile.entity_type == "issues"
        assert profile.profile_name == "minimal"
        assert profile.fields == fields

    def test_get_fields_string(self):
        """Test getting fields as string."""
        fields = ["id", "summary", "state(name,id)"]
        profile = FieldProfile("issues", "minimal", fields)

        result = profile.get_fields_string()
        assert result == "id,summary,state(name,id)"

    def test_get_fields_list(self):
        """Test getting fields as list."""
        fields = ["id", "summary", "state(name)"]
        profile = FieldProfile("issues", "minimal", fields)

        result = profile.get_fields_list()
        assert result == fields
        assert result is not fields  # Should be a copy

    def test_string_representation(self):
        """Test string representation."""
        profile = FieldProfile("issues", "minimal", ["id", "summary"])
        assert str(profile) == "issues:minimal"


class TestFieldSelector:
    """Test field selector functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.selector = FieldSelector()

    def test_initialization(self):
        """Test field selector initialization."""
        assert self.selector._profiles == FIELD_PROFILES
        assert "issues" in self.selector._default_profiles
        assert self.selector._default_profiles["issues"] == "standard"

    def test_get_profile_valid(self):
        """Test getting a valid profile."""
        profile = self.selector.get_profile("issues", "minimal")

        assert profile is not None
        assert profile.entity_type == "issues"
        assert profile.profile_name == "minimal"
        assert "id" in profile.fields

    def test_compact_profile_is_lean_json(self):
        """compact (#727) carries description + core fields but omits the heavy
        customFields expansion that dominates large JSON payloads."""
        fields = self.selector.get_fields("issues", "compact")

        assert "summary" in fields
        assert "description" in fields
        assert "customFields" not in fields

    def test_get_profile_invalid_entity(self):
        """Test getting profile for invalid entity type."""
        profile = self.selector.get_profile("invalid", "minimal")
        assert profile is None

    def test_get_profile_invalid_profile(self):
        """Test getting invalid profile name."""
        profile = self.selector.get_profile("issues", "invalid")
        assert profile is None

    def test_get_fields_default_profile(self):
        """Test getting fields with default profile."""
        fields = self.selector.get_fields("issues")

        # Should use standard profile by default
        assert "id" in fields
        assert "summary" in fields
        assert "description" in fields

    def test_get_fields_minimal_profile(self):
        """Test getting fields with minimal profile."""
        fields = self.selector.get_fields("issues", "minimal")

        assert "id" in fields
        assert "summary" in fields
        # Minimal profile should not include description
        assert "description" not in fields

    def test_get_fields_full_profile(self):
        """Test getting fields with full profile."""
        fields = self.selector.get_fields("issues", "full")

        assert "id" in fields
        assert "summary" in fields
        assert "description" in fields
        assert "customFields" in fields
        assert "attachments" in fields

    def test_get_fields_custom_fields(self):
        """Test adding custom fields."""
        fields = self.selector.get_fields("issues", "minimal", custom_fields=["priority(name)", "tags(name)"])

        assert "priority(name)" in fields
        assert "tags(name)" in fields
        assert "id" in fields  # Should still include base fields

    def test_get_fields_exclude_fields(self):
        """Test excluding specific fields."""
        fields = self.selector.get_fields("issues", "standard", exclude_fields=["description", "priority(name,id)"])

        assert "description" not in fields
        assert "priority(name,id)" not in fields
        assert "id" in fields  # Should still include essential fields

    def test_get_fields_unknown_entity_fallback(self):
        """Test fallback behavior for unknown entity type."""
        fields = self.selector.get_fields("unknown_entity", "minimal")

        # Should fallback to basic fields
        assert "id" in fields
        assert "summary" in fields

    def test_get_available_profiles(self):
        """Test getting available profiles."""
        profiles = self.selector.get_available_profiles("issues")

        assert "minimal" in profiles
        assert "standard" in profiles
        assert "full" in profiles

    def test_get_supported_entities(self):
        """Test getting supported entities."""
        entities = self.selector.get_supported_entities()

        assert "issues" in entities
        assert "projects" in entities
        assert "users" in entities

    def test_set_default_profile_valid(self):
        """Test setting valid default profile."""
        result = self.selector.set_default_profile("issues", "minimal")

        assert result is True
        assert self.selector._default_profiles["issues"] == "minimal"

    def test_set_default_profile_invalid_entity(self):
        """Test setting default for invalid entity."""
        result = self.selector.set_default_profile("invalid", "minimal")
        assert result is False

    def test_set_default_profile_invalid_profile(self):
        """Test setting invalid default profile."""
        result = self.selector.set_default_profile("issues", "invalid")
        assert result is False

    def test_validate_fields_valid(self):
        """Test field validation with valid fields."""
        fields = "id,summary,state(name,id),assignee(login,fullName)"
        result = self.selector.validate_fields(fields, "issues")
        assert result is True

    def test_validate_fields_unbalanced_parentheses(self):
        """Test field validation with unbalanced parentheses."""
        fields = "id,summary,state(name"
        result = self.selector.validate_fields(fields, "issues")
        assert result is False

    def test_validate_fields_empty(self):
        """Test field validation with empty fields."""
        result = self.selector.validate_fields("", "issues")
        assert result is False

    def test_validate_fields_invalid_characters(self):
        """Test field validation with invalid characters."""
        fields = "id,summary,state(name);DROP TABLE issues"
        result = self.selector.validate_fields(fields, "issues")
        assert result is False


class TestFieldSelectorWithConfig:
    """Test field selector with configuration manager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_config = Mock()
        self.selector = FieldSelector(self.mock_config)

    def test_load_config_defaults(self):
        """Test loading defaults from configuration."""
        self.mock_config.get_config.side_effect = lambda key: {
            "FIELD_PROFILE_ISSUES": "minimal",
            "FIELD_PROFILE_PROJECTS": "full",
        }.get(key)

        selector = FieldSelector(self.mock_config)

        assert selector._default_profiles["issues"] == "minimal"
        assert selector._default_profiles["projects"] == "full"

    def test_load_config_invalid_profile(self):
        """Test loading invalid profile from config is ignored."""
        self.mock_config.get_config.return_value = "invalid_profile"

        selector = FieldSelector(self.mock_config)

        # Should use default since config value is invalid
        assert selector._default_profiles["issues"] == "standard"

    def test_save_default_to_config_success(self):
        """Test saving default to configuration."""
        result = self.selector.save_default_to_config("issues", "minimal")

        assert result is True
        self.mock_config.set_config.assert_called_with("FIELD_PROFILE_ISSUES", "minimal")

    def test_save_default_to_config_invalid_profile(self):
        """Test saving invalid profile to config fails."""
        result = self.selector.save_default_to_config("issues", "invalid")

        assert result is False
        self.mock_config.set_config.assert_not_called()

    def test_save_default_to_config_error(self):
        """Test handling config save error."""
        self.mock_config.set_config.side_effect = Exception("Config error")

        result = self.selector.save_default_to_config("issues", "minimal")

        assert result is False

    def test_no_config_manager(self):
        """Test behavior without config manager."""
        selector = FieldSelector(None)

        result = selector.save_default_to_config("issues", "minimal")
        assert result is False


class TestGlobalFieldSelector:
    """Test global field selector functions."""

    def test_get_field_selector_singleton(self):
        """Test global field selector is singleton."""
        with patch("youtrack_cli.field_selection._field_selector", None):
            selector1 = get_field_selector()
            selector2 = get_field_selector()

            assert selector1 is selector2

    def test_get_field_selector_with_config(self):
        """Test getting field selector with config manager."""
        mock_config = Mock()

        with patch("youtrack_cli.field_selection._field_selector", None):
            selector = get_field_selector(mock_config)

            assert selector._config_manager is mock_config


class TestFieldProfiles:
    """Test predefined field profiles."""

    def test_all_entities_have_profiles(self):
        """Test all entities have required profiles."""
        required_profiles = ["minimal", "standard", "full"]

        for entity_type, profiles in FIELD_PROFILES.items():
            for profile_name in required_profiles:
                assert profile_name in profiles, f"Missing {profile_name} profile for {entity_type}"

    def test_minimal_profiles_have_id(self):
        """Test minimal profiles always include ID field."""
        for entity_type, profiles in FIELD_PROFILES.items():
            minimal_fields = profiles["minimal"]
            assert "id" in minimal_fields, f"Minimal profile for {entity_type} missing ID field"

    def test_standard_profiles_include_minimal(self):
        """Test standard profiles include minimal fields."""
        for entity_type, profiles in FIELD_PROFILES.items():
            minimal_set = set(profiles["minimal"])
            standard_set = set(profiles["standard"])

            assert minimal_set.issubset(standard_set), (
                f"Standard profile for {entity_type} doesn't include all minimal fields"
            )

    def test_full_profiles_include_standard(self):
        """Test full profiles include standard fields."""
        for entity_type, profiles in FIELD_PROFILES.items():
            standard_set = set(profiles["standard"])
            full_set = set(profiles["full"])

            assert standard_set.issubset(full_set), (
                f"Full profile for {entity_type} doesn't include all standard fields"
            )


class TestFieldSelection:
    """Integration tests for field selection functionality."""

    def test_issues_minimal_profile(self):
        """Test issues minimal profile has essential fields."""
        selector = FieldSelector()
        fields = selector.get_fields("issues", "minimal")

        # Should have basic issue identification
        assert "id" in fields
        assert "numberInProject" in fields
        assert "summary" in fields
        assert "idReadable" in fields

    def test_issues_standard_profile(self):
        """Test issues standard profile has common fields."""
        selector = FieldSelector()
        fields = selector.get_fields("issues", "standard")

        # Should include reporter and project info
        assert "reporter(login,fullName,id)" in fields
        assert "project(id,name,shortName)" in fields
        assert "description" in fields

    def test_no_issues_profile_names_a_field_the_api_drops(self):
        """`state`, `priority` and `type` are not top-level issue fields.

        Provable rather than assumed: every issue in the project carries all three inside
        `customFields`, and requesting them directly still returns nothing — so the field is absent
        because it does not exist, not because the value is empty. `assignee` is the contrast case
        and must stay: it looks identical on a project where nothing is assigned, which is what
        once led to it being removed too, but an empty value is not a dropped field.
        """
        selector = FieldSelector()
        for profile_name in selector.get_available_profiles("issues"):
            requested = [f.strip() for f in selector.get_fields("issues", profile_name).split(",")]
            for dropped in ("state", "priority", "type", "State", "Priority", "Type"):
                assert not any(f == dropped or f.startswith(f"{dropped}(") for f in requested), (
                    f"issues:{profile_name} still requests {dropped}, which is not an issue field"
                )

    def test_assignee_is_still_requested_where_it_applies(self):
        # Pinned so the false removal of round 2 cannot come back: an all-null assignee must not
        # read as a dropped field, and a profile that stops asking loses the value where one exists.
        selector = FieldSelector()
        for profile_name in ("compact", "standard", "full"):
            requested = [f.strip() for f in selector.get_fields("issues", profile_name).split(",")]
            assert any(f.startswith("assignee(") for f in requested), (
                f"issues:{profile_name} stopped requesting assignee"
            )

    def test_projects_minimal_vs_full(self):
        """Test projects field profiles have appropriate scope."""
        selector = FieldSelector()

        minimal = selector.get_fields("projects", "minimal")
        full = selector.get_fields("projects", "full")

        # Minimal should be much shorter
        minimal_count = len(minimal.split(","))
        full_count = len(full.split(","))

        assert minimal_count < full_count / 2, "Minimal profile should be significantly smaller"

    def test_custom_fields_addition(self):
        """Test adding custom fields to profile."""
        selector = FieldSelector()

        base_fields = selector.get_fields("issues", "minimal")
        custom_fields = selector.get_fields("issues", "minimal", custom_fields="priority(name),tags(name)")

        # Custom fields should add to the base
        assert "priority(name)" in custom_fields
        assert "tags(name)" in custom_fields
        assert len(custom_fields) > len(base_fields)

    def test_field_exclusion(self):
        """Test excluding fields from profile."""
        selector = FieldSelector()

        full_fields = selector.get_fields("issues", "full")
        excluded_fields = selector.get_fields(
            "issues", "full", exclude_fields=["description", "attachments(name,size,url)"]
        )

        # Excluded fields should not be present
        assert "description" not in excluded_fields
        assert "attachments(name,size,url)" not in excluded_fields
        assert len(excluded_fields) < len(full_fields)


class TestIssueProfilesExposeIdReadable:
    """Every `issues` profile must carry `idReadable` (#780).

    `id` is an internal id (`3-353`) and `numberInProject` is ambiguous across projects, so
    `idReadable` is the only stable public name for an issue. It is what a caller prints after
    creating one and what it addresses on the next call. A profile without it cannot name an
    issue, which is the whole defect — and `minimal` is included, because a caller that asked
    for the smallest possible payload still needs to know what it just made.
    """

    def test_every_issues_profile_includes_id_readable(self):
        selector = FieldSelector()
        for profile_name in selector.get_available_profiles("issues"):
            selected = selector.get_fields("issues", profile_name).split(",")
            assert "idReadable" in selected, f"issues:{profile_name} cannot name an issue"

    def test_the_articles_profiles_still_carry_it_too(self):
        # They always did; pinned so a later edit to one entity does not quietly drop the other.
        selector = FieldSelector()
        for profile_name in selector.get_available_profiles("articles"):
            selected = selector.get_fields("articles", profile_name).split(",")
            assert "idReadable" in selected, f"articles:{profile_name} lost idReadable"


class TestParseFieldExpression:
    """A `--fields` expression has to be understood before it can be checked against a response."""

    def test_nests_children(self):
        nodes = parse_field_expression("customFields(name,value(name,id))")
        assert [n.name for n in nodes] == ["customFields"]
        assert [c.name for c in nodes[0].children] == ["name", "value"]
        assert [c.name for c in nodes[0].children[1].children] == ["name", "id"]

    def test_splits_top_level_terms(self):
        nodes = parse_field_expression("idReadable,summary,tags(name)")
        assert [n.name for n in nodes] == ["idReadable", "summary", "tags"]

    def test_handles_the_shape_the_spec_gate_sends(self):
        # The deep expression the standing gate relies on: two terms, three levels.
        nodes = parse_field_expression("idReadable,links(direction,linkType(name),issues(idReadable))")
        links = nodes[1]
        assert links.name == "links"
        assert [c.name for c in links.children] == ["direction", "linkType", "issues"]
        assert [c.name for c in links.children[1].children] == ["name"]
        assert [c.name for c in links.children[2].children] == ["idReadable"]

    def test_tolerates_whitespace_and_unbalanced_input(self):
        # Unbalanced input is the command's syntactic validator's job to report; this must not
        # raise on its way to the response comparison.
        assert [n.name for n in parse_field_expression(" idReadable , summary ")] == ["idReadable", "summary"]
        assert [n.name for n in parse_field_expression("value(name")] == ["value"]

    def test_skips_a_character_that_cannot_start_a_name(self):
        # Defensive: a stray quote or bracket must be stepped over rather than looped on or
        # mistaken for structure. What follows a stray character still parses as its own name,
        # which is the right outcome for malformed input — the server will not return it, so it
        # is reported as a field that was asked for and not given, rather than silently dropped.
        assert [n.name for n in parse_field_expression("[idReadable]")] == ["idReadable"]
        assert [n.name for n in parse_field_expression('idReadable"x"')] == ["idReadable", "x"]


class TestFindMissingFields:
    """The defect: the API drops an unknown field and answers 200, so a typo is invisible."""

    def test_reports_a_misspelled_name_that_has_a_neighbour_in_the_response(self):
        # `idReadable` was asked for too and arrived, so `idReadble` beside it is a typo whatever
        # the schema says. This is the case the check is actually good at.
        records = [{"idReadable": "V", "summary": "s"}]
        assert find_missing_fields("idReadble,idReadable,summary", records) == ["idReadble"]

    def test_reports_an_invented_top_level_name_only_when_nothing_came_back(self):
        # With `idReadable` absent too, nothing requested arrived — an expression that is wrong
        # rather than one that happened to be empty — so both names are reported. When something
        # *did* arrive, an invented name with no near neighbour is not; see the next test.
        assert find_missing_fields("idReadable,notAField", [{"summary": "s"}]) == ["idReadable", "notAField"]

    def test_clean_expression_reports_nothing(self):
        assert find_missing_fields("idReadable,summary", [{"idReadable": "VAN-1", "summary": "s"}]) == []

    def test_a_nested_typo_beside_a_correct_sibling_is_not_reported(self):
        # The deliberate limit of the check, pinned so it is not mistaken for a guarantee.
        #
        # `linkType(nom)` is a misspelling, and a stricter rule would want to report it. It is not
        # reported, because `{"name": "Depend"}` is real data and there is no way to tell a
        # misspelled subfield from one that simply does not apply to this object's type — the same
        # ambiguity that makes a text field's `{"text": ...}` a legitimate answer to `value(name,id)`.
        # Reporting it would reject correct reads, which is the worse failure.
        #
        # What this costs: the typo slips through and the name is dropped, which is the behaviour
        # this module replaced. It never turns a good read into a failed one.
        records = [{"links": [{"direction": "OUTWARD", "linkType": {"name": "Depend"}, "issues": []}]}]
        assert find_missing_fields("links(direction,linkType(nom))", records) == []

    def test_a_misspelled_id_beside_correct_data_is_not_reported(self):
        # Same trade, on the path that motivated the change: `issues(idReadble)` alongside data
        # that came back correctly is not reported. See the test above for why.
        records = [{"links": [{"direction": "OUTWARD", "issues": [{"idReadable": "V"}]}]}]
        assert find_missing_fields("links(direction,issues(idReadble))", records) == []

    def test_a_polymorphic_bundle_value_is_not_a_missing_field(self):
        # The profiles ask for one union of subfields across every bundle type; an enum answers
        # name/id and a user answers login/fullName. Flagging the absent siblings would reject
        # the CLI's own `standard` profile on a perfectly correct response.
        records = [
            {
                "customFields": [
                    {"name": "Priority", "value": {"name": "Major", "id": "1"}},
                    {"name": "Assignee", "value": None},
                ]
            }
        ]
        expression = "customFields(name,value(name,id,login,fullName,text,presentation))"
        assert find_missing_fields(expression, records) == []

    def test_a_text_valued_field_is_not_a_missing_field(self):
        # The false rejection that would have broken the spec gate. A text custom field asked for
        # `value(name,id)` answers `{"text": ...}`: the requested subfield does not apply to that
        # field's type, which is not a dropped field. The gate's own expression is `value(name)`.
        records = [{"customFields": [{"name": "Due date", "value": {"text": "2026-01-01"}}]}]
        assert find_missing_fields("customFields(name,value(name))", records) == []
        assert find_missing_fields("customFields(name,value(name,id))", records) == []

    def test_a_user_valued_field_is_not_a_missing_field(self):
        records = [{"customFields": [{"name": "Assignee", "value": {"login": "u", "fullName": "U"}}]}]
        assert find_missing_fields("customFields(name,value(name,id))", records) == []

    def test_an_object_returning_nothing_is_not_a_missing_field(self):
        # `{}` carries no keys at all, so there is nothing there to have been dropped — which is
        # different from an object carrying only `$type`, the API's stripped-response signature.
        assert find_missing_fields("idReadable,reporter(login)", [{"idReadable": "V", "reporter": {}}]) == []

    def test_a_nested_subfield_is_not_reported_even_when_it_came_back_empty(self):
        # The design limit, pinned with the reason, because a reviewer will otherwise read it as a
        # bug. The API answers by returning *only what it was asked for*, so a nested subfield that
        # does not apply to a field's type is byte-for-byte identical to a misspelled one: a text
        # custom field asked for `value(name)` returns `{"$type": "TextFieldValue"}` and a value
        # asked for `value(bogus)` returns `{"$type": ...}`. Nothing separates them.
        text_field = [{"customFields": [{"name": "Due date", "value": {"$type": "TextFieldValue"}}]}]
        assert find_missing_fields("customFields(name,value(name))", text_field) == []
        assert find_missing_fields("customFields(name,value(bogus))", text_field) == []

    def test_a_documented_field_that_is_empty_is_not_reported(self):
        # `parentIssueLink` is a real field, absent from every issue in a project where nothing is
        # a sub-task. Refusing it breaks a read that worked, which is the one failure that must not
        # happen, and an absent value is indistinguishable from an unknown name in a response.
        assert find_missing_fields("idReadable,parentIssueLink", [{"idReadable": "V"}]) == []
        assert find_missing_fields("idReadable,assignee(login)", [{"idReadable": "V"}]) == []

    def test_a_misspelling_of_a_field_that_arrived_is_reported(self):
        # The near-miss rule needs no schema: `idReadble` beside a returned `idReadable` is a typo
        # whatever the entity actually has, so it is reported.
        records = [{"idReadable": "V", "summary": "s"}]
        assert find_missing_fields("idReadble,summary", records) == ["idReadble"]
        assert find_missing_fields("idReadabl,summary", records) == ["idReadabl"]

    def test_a_request_where_nothing_came_back_is_reported(self):
        # Every requested name absent means the expression is wrong, not that the values are empty.
        # This is the one-name case, where there is no neighbour to compare against.
        assert find_missing_fields("idReadble", [{"summary": "s"}]) == ["idReadble"]

    def test_an_invented_name_with_no_near_neighbour_is_not_reported(self):
        # The accepted cost, stated rather than hidden. `notAField` beside `summary` is too far
        # from anything that arrived to call a misspelling, and guessing from a schema is what
        # made two earlier designs unsound. The name is dropped, as it was before this check.
        assert find_missing_fields("idReadable,notAField", [{"idReadable": "V"}]) == []

    def test_a_name_present_in_any_record_counts_as_returned(self):
        # Aggregation, not per-record: a field that is empty on one issue but set on another is
        # present, and must not be reported.
        records = [{"idReadable": "V", "resolved": None}, {"idReadable": "W", "resolved": "2026-01-01"}]
        assert find_missing_fields("idReadable,resolved", records) == []

    def test_a_null_value_is_an_empty_answer_not_a_dropped_field(self):
        records = [{"customFields": [{"name": "Assignee", "value": None}]}]
        assert find_missing_fields("customFields(name,value(name,id))", records) == []

    def test_an_empty_collection_is_an_empty_answer_not_a_dropped_field(self):
        # An untagged issue legitimately returns `tags: []`.
        assert find_missing_fields("tags(name)", [{"tags": []}]) == []

    def test_a_collection_of_non_objects_asserts_nothing(self):
        # A list that carries no objects has no keys to check either way, so it must not be
        # reported — the same reasoning as an empty collection.
        assert find_missing_fields("tags(name)", [{"tags": ["a", "b"]}]) == []

    def test_a_scalar_carrying_no_keys_is_not_a_missing_field(self):
        assert find_missing_fields("resolved", [{"resolved": None, "idReadable": "V"}]) == []

    def test_no_records_is_an_empty_result_not_a_bad_expression(self):
        # Nothing came back, so there is nothing to compare against; the caller reports emptiness.
        assert find_missing_fields("idReadable", []) == []

    def test_accepts_a_single_record(self):
        assert find_missing_fields("idReadable", {"idReadable": "VAN-1"}) == []
        assert find_missing_fields("idReadble", {"idReadable": "VAN-1"}) == ["idReadble"]

    def test_empty_expression_reports_nothing(self):
        assert find_missing_fields("", [{"summary": "s"}]) == []
        assert find_missing_fields("   ", [{"summary": "s"}]) == []

    def test_the_gate_expression_validates_against_a_gate_shaped_payload(self):
        expression = "id,idReadable,summary,resolved,description,customFields(name,value(name)),tags(name),links(direction,linkType(name),issues(idReadable))"
        records = [
            {
                "id": "3-70",
                "idReadable": "VAN-1",
                "summary": "s",
                "resolved": None,
                "description": "d",
                "customFields": [{"name": "Priority", "value": {"name": "Major"}}],
                "tags": [{"name": "lane-root"}],
                "links": [
                    {
                        "direction": "OUTWARD",
                        "linkType": {"name": "Depend"},
                        "issues": [{"idReadable": "VAN-2"}],
                    }
                ],
            }
        ]
        assert find_missing_fields(expression, records) == []
