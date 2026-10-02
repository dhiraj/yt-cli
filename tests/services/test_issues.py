"""Tests for IssueService."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from youtrack_cli.auth import AuthManager
from youtrack_cli.custom_field_types import (
    CustomFieldValueTypes,
    IssueCustomFieldTypes,
    ProjectCustomFieldTypes,
)
from youtrack_cli.exceptions import CustomFieldUnresolvedReason
from youtrack_cli.services.issues import IssueService
from youtrack_cli.services.projects import ProjectService


@pytest.fixture
def auth_manager():
    """Create a mock auth manager."""
    mock_auth = MagicMock(spec=AuthManager)
    return mock_auth


@pytest.fixture
def issue_service(auth_manager):
    """Create an IssueService instance."""
    return IssueService(auth_manager)


@pytest.fixture
def mock_response():
    """Create a mock HTTP response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {"id": "TEST-1", "summary": "Test Issue"}
    response.headers = {"content-type": "application/json"}
    response.text = '{"id": "TEST-1", "summary": "Test Issue"}'
    return response


class TestIssueServiceCreation:
    """Test issue creation functionality."""

    @pytest.mark.asyncio
    async def test_create_issue_basic(self, issue_service, mock_response):
        """Test basic issue creation."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": {"id": "TEST-1"}}

            result = await issue_service.create_issue("project-1", "Test Summary")

            mock_request.assert_called_once_with(
                "POST", "issues", json_data={"project": {"id": "project-1"}, "summary": "Test Summary"}
            )
            mock_handle.assert_called_once_with(mock_response, success_codes=[200, 201])
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_create_issue_writes_several_values_for_a_multi_valued_field(self, issue_service, mock_response):
        """The create path carries the same value list the update path does.

        Worth pinning separately because the two paths resolve fields independently: a
        create that dropped all but the last value would leave the issue created with
        one of the two versions asked for.
        """
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": {"id": "TEST-1"}}
            mock_discover.return_value = {
                "status": "success",
                "data": {
                    "project_field_type": ProjectCustomFieldTypes.ENUM,
                    "issue_field_type": IssueCustomFieldTypes.MULTI_ENUM,
                    "is_multi_value": True,
                    "bundle_element_type": CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT,
                },
            }

            result = await issue_service.create_issue(
                "project-1", "Test Summary", custom_fields={"Sprint": ["S1", "S2"]}
            )

            assert result["status"] == "success"
            sent = mock_request.call_args.kwargs["json_data"]["customFields"][0]
            assert sent["$type"] == IssueCustomFieldTypes.MULTI_ENUM
            assert [element["name"] for element in sent["value"]] == ["S1", "S2"]

    @pytest.mark.asyncio
    async def test_several_values_for_a_single_valued_field_create_no_issue(self, issue_service, mock_response):
        """A refused field must stop the create, not produce an issue missing a value.

        Half a create is worse than none: the issue exists, and the value the caller
        asked for does not, with nothing in the output to say so.
        """
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": {"id": "TEST-1"}}
            mock_discover.return_value = {
                "status": "success",
                "data": {
                    "project_field_type": ProjectCustomFieldTypes.ENUM,
                    "issue_field_type": IssueCustomFieldTypes.SINGLE_ENUM,
                },
            }

            result = await issue_service.create_issue(
                "project-1", "Test Summary", custom_fields={"Repo": ["ios", "android"]}
            )

            assert result["status"] == "error"
            assert "2 were given" in result["message"]
            mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_unwritable_value_creates_no_issue(self, issue_service, mock_response):
        """A value the CLI cannot state must not leave a half-built issue behind.

        Half a create is worse than none: the issue exists, and the value the caller asked
        for does not, with nothing in the output to say so.
        """
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": {"id": "TEST-1"}}
            mock_discover.return_value = {
                "status": "success",
                "data": {
                    "project_field_type": ProjectCustomFieldTypes.INTEGER,
                    "issue_field_type": IssueCustomFieldTypes.INTEGER,
                },
            }

            result = await issue_service.create_issue("project-1", "Test Summary", custom_fields={"Story Points": True})

            assert result["status"] == "error"
            assert "not a field value" in result["message"]
            mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_issue_with_all_fields(self, issue_service, mock_response):
        """Test issue creation with all optional fields."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await issue_service.create_issue(
                project_id="project-1",
                summary="Test Summary",
                description="Test Description",
                issue_type="Bug",
                priority="High",
                assignee="user123",
            )

            expected_data = {
                "project": {"id": "project-1"},
                "summary": "Test Summary",
                "description": "Test Description",
                "customFields": [
                    {
                        "$type": "SingleEnumIssueCustomField",
                        "name": "Priority",
                        "value": {"$type": "EnumBundleElement", "name": "High"},
                    },
                    {
                        "$type": "SingleEnumIssueCustomField",
                        "name": "Type",
                        "value": {"$type": "EnumBundleElement", "name": "Bug"},
                    },
                    {
                        "$type": "SingleUserIssueCustomField",
                        "name": "Assignee",
                        "value": {"login": "user123"},
                    },
                ],
            }

            mock_request.assert_called_once_with("POST", "issues", json_data=expected_data)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_create_issue_value_error(self, issue_service):
        """Test issue creation with ValueError."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = ValueError("Invalid data")
            mock_error.return_value = {"status": "error", "message": "Invalid data"}

            result = await issue_service.create_issue("project-1", "Test")

            mock_error.assert_called_once_with("Invalid data")
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_create_issue_general_exception(self, issue_service):
        """Test issue creation with general exception."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = Exception("Network error")
            mock_error.return_value = {"status": "error", "message": "Error creating issue: Network error"}

            result = await issue_service.create_issue("project-1", "Test")

            mock_error.assert_called_once_with("Error creating issue: Network error")
            assert result["status"] == "error"


class TestIssueServiceRetrieval:
    """Test issue retrieval functionality."""

    @pytest.mark.asyncio
    async def test_get_issue_basic(self, issue_service, mock_response):
        """Test basic issue retrieval."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"data": {"id": "TEST-1"}}

            result = await issue_service.get_issue("TEST-1")

            expected_params = {
                "fields": (
                    "id,idReadable,summary,description,resolved,"
                    "assignee(login,fullName),project(id,name),created,updated,"
                    "tags(name),links(linkType(name),direction,issues(id,summary)),"
                    "customFields(id,name,value(login,fullName,name))"
                )
            }
            mock_request.assert_called_once_with("GET", "issues/TEST-1", params=expected_params)
            assert result["data"]["id"] == "TEST-1"

    @pytest.mark.asyncio
    async def test_get_issue_default_fields_name_the_issue_and_its_links(self, issue_service, mock_response):
        """Three properties of the default field list, all of which were wrong.

        `idReadable` is the only stable public name for an issue, so a caller that fetched one
        issue as data had no way to name it (#780 — every profile carries it for this reason).

        `linkType(name)` rather than a bare `linkType`: asked for on its own the API returns an
        object carrying only `$type`, so the name never arrived and each renderer read
        `linkType.get("name", "")` and got an empty string. Verified against the live instance.

        `resolved` because it is the field that says whether the issue shipped, which is the one
        thing a single-issue read is for — the tracker's gate requires the state to be delivered
        *and* `resolved` to be set, so a read that omits it cannot answer "has this landed?" (#498).
        """
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"data": {"id": "TEST-1"}}

            await issue_service.get_issue("TEST-1")

            fields = mock_request.call_args.kwargs["params"]["fields"]
            assert "idReadable" in fields, "a single-issue read must be able to name the issue"
            assert "linkType(name)" in fields, "a bare linkType returns no name"
            assert "links(linkType," not in fields, "the bare form is what returns no name"
            assert "resolved" in fields, "whether the issue shipped must be readable"

    @pytest.mark.asyncio
    async def test_get_issue_with_custom_fields(self, issue_service, mock_response):
        """Test issue retrieval with custom fields."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"data": {"id": "TEST-1"}}

            result = await issue_service.get_issue("TEST-1", fields="id,summary")

            mock_request.assert_called_once_with("GET", "issues/TEST-1", params={"fields": "id,summary"})
            assert result["data"]["id"] == "TEST-1"

    @pytest.mark.asyncio
    async def test_search_issues_basic(self, issue_service, mock_response):
        """Test basic issue search."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"data": [{"id": "TEST-1"}]}

            result = await issue_service.search_issues("assignee: me")

            expected_params = {
                "query": "assignee: me",
                "fields": (
                    "id,idReadable,summary,description,"
                    "assignee(login,fullName),project(id,name,shortName),"
                    "created,updated,tags(name),"
                    "customFields(id,name,value(login,fullName,name))"
                ),
            }
            mock_request.assert_called_once_with("GET", "issues", params=expected_params)
            assert result["data"][0]["id"] == "TEST-1"

    @pytest.mark.asyncio
    async def test_search_issues_with_pagination(self, issue_service, mock_response):
        """Test issue search with pagination."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"data": []}

            await issue_service.search_issues(query="state: Open", fields="id,summary", top=10, skip=5)

            expected_params = {"query": "state: Open", "fields": "id,summary", "$top": "10", "$skip": "5"}
            mock_request.assert_called_once_with("GET", "issues", params=expected_params)


class TestIssueServiceUpdate:
    """Test issue update functionality."""

    @pytest.mark.asyncio
    async def test_update_issue_basic(self, issue_service, mock_response):
        """Test basic issue update."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await issue_service.update_issue("TEST-1", summary="New Summary")

            expected_data = {"$type": "Issue", "summary": "New Summary"}
            mock_request.assert_called_once_with("POST", "issues/TEST-1", json_data=expected_data)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_update_issue_with_custom_fields(self, issue_service, mock_response):
        """Test issue update with state and priority."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch.object(issue_service, "_discover_state_field_for_project", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = "TEST"
            mock_discover.return_value = {"field_name": "State", "bundle_type": "EnumBundleElement"}

            await issue_service.update_issue("TEST-1", summary="Updated Summary", state="In Progress", priority="High")

            expected_data = {
                "$type": "Issue",
                "summary": "Updated Summary",
                "customFields": [
                    {
                        "$type": "SingleEnumIssueCustomField",
                        "name": "State",
                        "value": {"$type": "EnumBundleElement", "name": "In Progress"},
                    },
                    {
                        "$type": "SingleEnumIssueCustomField",
                        "name": "Priority",
                        "value": {"$type": "EnumBundleElement", "name": "High"},
                    },
                ],
            }
            mock_request.assert_called_once_with("POST", "issues/TEST-1", json_data=expected_data)

    @pytest.mark.asyncio
    async def test_update_issue_custom_fields_without_state_discovers_type(self, issue_service, mock_response):
        """A custom-fields-only update must discover each field's real type.

        Regression: `project_id` was only ever bound inside the `state` branch,
        so calling this without a state raised UnboundLocalError. The broad
        `except` around field discovery swallowed it and downgraded every field
        to a guessed enum, which happens to be correct for enum fields and
        silently wrong for every other type.
        """
        discovered = {
            "field_name": "Assigned",
            "field_id": "cf-1",
            "issue_field_type": IssueCustomFieldTypes.TEXT,
        }
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch("youtrack_cli.services.projects.ProjectService") as mock_project_service,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = "TEST"
            mock_project_service.return_value.discover_custom_field = AsyncMock(
                return_value={"status": "success", "data": discovered}
            )

            result = await issue_service.update_issue("TEST-1", custom_fields={"Assigned": "someone"})

            assert result["status"] == "success"
            # The project must be resolved even though no state was given.
            mock_get_project.assert_awaited_once_with("TEST-1")
            # Discovery must run against that project rather than falling back.
            mock_project_service.return_value.discover_custom_field.assert_awaited_once_with("TEST", "Assigned")
            mock_request.assert_called_once_with(
                "POST",
                "issues/TEST-1",
                json_data={
                    "$type": "Issue",
                    "customFields": [
                        {
                            "$type": IssueCustomFieldTypes.TEXT,
                            "name": "Assigned",
                            "value": {"$type": "TextValue", "text": "someone"},
                        },
                    ],
                },
            )

    @pytest.mark.asyncio
    async def test_update_issue_custom_fields_refuses_when_project_unresolvable(self, issue_service, mock_response):
        """An unresolvable project must refuse the write, not send a guessed type.

        Without the project there is no way to learn the field's type, and a guessed
        enum is rejected by the server as a type mismatch. Refusing locally names the
        cause and leaves the issue untouched.
        """
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = None

            result = await issue_service.update_issue("TEST-1", custom_fields={"Assigned": "someone"})

            assert result["status"] == "error"
            assert "Could not resolve the project" in result["message"]
            assert "No values were sent" in result["message"]
            # Nothing may be sent: a partial write would apply the fields it could type.
            mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_issue_custom_fields_use_real_type_for_user_field(self, issue_service, mock_response):
        """A user field must be written as a user, not as a guessed enum.

        Regression: the project->issue type lookup keyed on issue-side spellings
        ("SingleUserProjectCustomField") that the admin API never returns, so every
        user/version/build field missed the table and fell through to a default enum
        payload, which YouTrack rejects with a type error.
        """
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = "TEST"
            mock_discover.return_value = {
                "status": "success",
                "data": {
                    "project_field_type": ProjectCustomFieldTypes.USER,
                    "issue_field_type": IssueCustomFieldTypes.SINGLE_USER,
                },
            }

            await issue_service.update_issue("TEST-1", custom_fields={"Assigned": ["someone"]})

            mock_request.assert_called_once_with(
                "POST",
                "issues/TEST-1",
                json_data={
                    "$type": "Issue",
                    "customFields": [
                        {
                            "$type": IssueCustomFieldTypes.SINGLE_USER,
                            "name": "Assigned",
                            "value": {"$type": CustomFieldValueTypes.USER, "login": "someone"},
                        }
                    ],
                },
            )

    @pytest.mark.asyncio
    async def test_update_issue_custom_fields_owned_field_uses_owned_bundle(self, issue_service, mock_response):
        """An owned field carries an OwnedBundleElement value, not an EnumBundleElement."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = "TEST"
            mock_discover.return_value = {
                "status": "success",
                "data": {
                    "project_field_type": ProjectCustomFieldTypes.OWNED,
                    "issue_field_type": IssueCustomFieldTypes.SINGLE_OWNED,
                    "bundle_element_type": None,
                },
            }

            await issue_service.update_issue("TEST-1", custom_fields={"Team": "core"})

            sent = mock_request.call_args.kwargs["json_data"]["customFields"][0]
            assert sent["$type"] == IssueCustomFieldTypes.SINGLE_OWNED
            assert sent["value"] == {"$type": CustomFieldValueTypes.OWNED_BUNDLE_ELEMENT, "name": "core"}

    @pytest.mark.asyncio
    async def test_update_issue_custom_fields_enum_field_keeps_discovered_element_type(
        self, issue_service, mock_response
    ):
        """A bundle-backed field prefers the element type discovery actually reports."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = "TEST"
            mock_discover.return_value = {
                "status": "success",
                "data": {
                    "project_field_type": ProjectCustomFieldTypes.ENUM,
                    "issue_field_type": IssueCustomFieldTypes.SINGLE_ENUM,
                    "bundle_element_type": CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT,
                },
            }

            await issue_service.update_issue("TEST-1", custom_fields={"Repo": ["root"]})

            sent = mock_request.call_args.kwargs["json_data"]["customFields"][0]
            assert sent["value"] == {"$type": CustomFieldValueTypes.ENUM_BUNDLE_ELEMENT, "name": "root"}

    @pytest.mark.asyncio
    async def test_update_issue_custom_fields_unmappable_type_blocks_whole_update(self, issue_service, mock_response):
        """One untypable field must stop the update, not half-apply it."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = "TEST"

            async def discover(_project_id, field_name):
                if field_name == "Repo":
                    return {
                        "status": "success",
                        "data": {
                            "project_field_type": ProjectCustomFieldTypes.ENUM,
                            "issue_field_type": IssueCustomFieldTypes.SINGLE_ENUM,
                        },
                    }
                return {
                    "status": "success",
                    "data": {"project_field_type": "SomethingNewProjectCustomField", "issue_field_type": None},
                }

            mock_discover.side_effect = discover

            result = await issue_service.update_issue(
                "TEST-1", summary="Renamed", custom_fields={"Repo": ["root"], "Mystery": ["x"]}
            )

            assert result["status"] == "error"
            assert "Mystery" in result["message"]
            assert "SomethingNewProjectCustomField" in result["message"]
            # The summary change must not land either: the update is all-or-nothing.
            mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_issue_writes_several_values_for_a_multi_valued_field(self, issue_service, mock_response):
        """A field that holds several is written as a list, in the order given.

        The end-to-end shape of the feature: the CLI's repeated `-cf` reaches the wire
        as one field with several values, not as two fields fighting over one name.
        """
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = "TEST"
            mock_discover.return_value = {
                "status": "success",
                "data": {
                    "project_field_type": ProjectCustomFieldTypes.VERSION,
                    "issue_field_type": IssueCustomFieldTypes.MULTI_VERSION,
                    "is_multi_value": True,
                },
            }

            await issue_service.update_issue("TEST-1", custom_fields={"Fix versions": ["1.0", "1.1"]})

            mock_request.assert_called_once_with(
                "POST",
                "issues/TEST-1",
                json_data={
                    "$type": "Issue",
                    "customFields": [
                        {
                            "$type": IssueCustomFieldTypes.MULTI_VERSION,
                            "name": "Fix versions",
                            "value": [
                                {"$type": CustomFieldValueTypes.VERSION_BUNDLE_ELEMENT, "name": "1.0"},
                                {"$type": CustomFieldValueTypes.VERSION_BUNDLE_ELEMENT, "name": "1.1"},
                            ],
                        }
                    ],
                },
            )

    @pytest.mark.asyncio
    async def test_several_values_for_a_single_valued_field_block_the_whole_update(self, issue_service, mock_response):
        """Two values for a one-value field is refused, and nothing is sent.

        Keeping the last would report success for a request that did not say what it
        meant, and the other value would vanish with no trace. The refusal also has to
        hold the all-or-nothing property the other refusals have: a summary change given
        in the same command must not land on its own.
        """
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = "TEST"
            mock_discover.return_value = {
                "status": "success",
                "data": {
                    "project_field_type": ProjectCustomFieldTypes.ENUM,
                    "issue_field_type": IssueCustomFieldTypes.SINGLE_ENUM,
                },
            }

            result = await issue_service.update_issue(
                "TEST-1", summary="Renamed", custom_fields={"Repo": ["ios", "android"]}
            )

            assert result["status"] == "error"
            assert "2 were given" in result["message"]
            assert "Repo" in result["message"]
            mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_unwritable_value_blocks_the_whole_update(self, issue_service, mock_response):
        """A JSON object or boolean where a value belongs is refused, and nothing is sent.

        `yt batch create --file items.json` forwards every non-null field of a row
        verbatim, so this reaches the writer -- and a boolean is an `int` to `isinstance`,
        so a numeric field would otherwise take `true` as 1 and report success.
        """
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = "TEST"
            mock_discover.return_value = {
                "status": "success",
                "data": {
                    "project_field_type": ProjectCustomFieldTypes.INTEGER,
                    "issue_field_type": IssueCustomFieldTypes.INTEGER,
                },
            }

            result = await issue_service.update_issue(
                "TEST-1", summary="Renamed", custom_fields={"Story Points": {"value": 8}}
            )

            assert result["status"] == "error"
            assert "not a field value" in result["message"]
            assert "Story Points" in result["message"]
            mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_issue_writes_a_multi_valued_field_from_one_value(self, issue_service, mock_response):
        """One value for a field that holds several is a one-element list, not a refusal.

        The field can hold many; asking for one of them is an ordinary request, and
        refusing it sent users to the web UI for something the API answers exactly.
        """
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = "TEST"
            mock_discover.return_value = {
                "status": "success",
                "data": {
                    "project_field_type": ProjectCustomFieldTypes.VERSION,
                    "issue_field_type": IssueCustomFieldTypes.MULTI_VERSION,
                    "is_multi_value": True,
                },
            }

            result = await issue_service.update_issue("TEST-1", custom_fields={"Fix versions": ["1.0"]})

            assert result["status"] == "success"
            sent = mock_request.call_args.kwargs["json_data"]["customFields"][0]
            assert sent["value"] == [{"$type": CustomFieldValueTypes.VERSION_BUNDLE_ELEMENT, "name": "1.0"}]

    @pytest.mark.asyncio
    async def test_unreported_multiplicity_blocks_the_whole_update(self, issue_service, mock_response):
        """A field whose shape the server did not report is refused, not guessed.

        Reporting it as an unknown *type* would send the reader looking at the wrong
        vocabulary; the cause is a missing field in the response for a kind this CLI
        handles, and the message says so.
        """
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch.object(ProjectService, "discover_custom_field", new_callable=AsyncMock) as mock_discover,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}
            mock_get_project.return_value = "TEST"
            mock_discover.return_value = {
                "status": "success",
                "data": {
                    "project_field_type": ProjectCustomFieldTypes.ENUM,
                    "issue_field_type": None,
                    "is_multi_value": None,
                    "unresolved_reason": CustomFieldUnresolvedReason.MULTIPLICITY,
                },
            }

            result = await issue_service.update_issue("TEST-1", custom_fields={"Sprint": ["S1"]})

            assert result["status"] == "error"
            assert "one value or several" in result["message"]
            mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_issue_with_assignee(self, issue_service, mock_response):
        """Test issue update with assignee field."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await issue_service.update_issue("TEST-1", assignee="admin")

            expected_data = {
                "$type": "Issue",
                "customFields": [
                    {"$type": "SingleUserIssueCustomField", "name": "Assignee", "value": {"login": "admin"}}
                ],
            }
            mock_request.assert_called_once_with("POST", "issues/TEST-1", json_data=expected_data)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_update_issue_with_assignee_and_other_fields(self, issue_service, mock_response):
        """Test issue update with assignee and other fields."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await issue_service.update_issue(
                "TEST-1", summary="Updated Summary", assignee="admin", priority="High"
            )

            expected_data = {
                "$type": "Issue",
                "summary": "Updated Summary",
                "customFields": [
                    {"$type": "SingleUserIssueCustomField", "name": "Assignee", "value": {"login": "admin"}},
                    {
                        "$type": "SingleEnumIssueCustomField",
                        "name": "Priority",
                        "value": {"$type": "EnumBundleElement", "name": "High"},
                    },
                ],
            }
            mock_request.assert_called_once_with("POST", "issues/TEST-1", json_data=expected_data)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_update_issue_with_empty_assignee(self, issue_service, mock_response):
        """Test issue update with empty assignee (unassign)."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await issue_service.update_issue("TEST-1", assignee="")

            expected_data = {
                "$type": "Issue",
                "customFields": [{"$type": "SingleUserIssueCustomField", "name": "Assignee", "value": None}],
            }
            mock_request.assert_called_once_with("POST", "issues/TEST-1", json_data=expected_data)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_assign_issue(self, issue_service, mock_response):
        """Test issue assignment."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            await issue_service.assign_issue("TEST-1", "user123")

            expected_data = {
                "$type": "Issue",
                "customFields": [
                    {"$type": "SingleUserIssueCustomField", "name": "Assignee", "value": {"login": "user123"}}
                ],
            }
            mock_request.assert_called_once_with("POST", "issues/TEST-1", json_data=expected_data)

    @pytest.mark.asyncio
    async def test_assign_issue_with_resolved_username(self, issue_service, mock_response):
        """Test issue assignment with resolved username (not 'me' directly)."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            # The command layer should resolve 'me' to actual username before calling the service
            await issue_service.assign_issue("TEST-1", "actual-username")

            expected_data = {
                "$type": "Issue",
                "customFields": [
                    {"$type": "SingleUserIssueCustomField", "name": "Assignee", "value": {"login": "actual-username"}}
                ],
            }
            mock_request.assert_called_once_with("POST", "issues/TEST-1", json_data=expected_data)


class TestIssueServiceDelete:
    """Test issue deletion functionality."""

    @pytest.mark.asyncio
    async def test_delete_issue(self, issue_service, mock_response):
        """Test issue deletion."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await issue_service.delete_issue("TEST-1")

            mock_request.assert_called_once_with("DELETE", "issues/TEST-1")
            assert result["status"] == "success"


class TestIssueServiceMove:
    """Test issue move functionality."""

    @pytest.mark.asyncio
    async def test_move_issue_no_parameters(self, issue_service):
        """Test move issue with no parameters."""
        with patch.object(issue_service, "_create_error_response") as mock_error:
            mock_error.return_value = {"status": "error", "message": "Either state or project_id must be provided"}

            result = await issue_service.move_issue("TEST-1")

            mock_error.assert_called_once_with("Either state or project_id must be provided")
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_move_issue_to_project_success(self, issue_service):
        """Test successful move issue to project."""
        with (
            patch.object(issue_service, "_move_issue_to_project", new_callable=AsyncMock) as mock_move,
        ):
            mock_move.return_value = {
                "status": "success",
                "message": "Issue 'TEST-1' successfully moved from 'Old Project' to 'new-project'",
            }

            result = await issue_service.move_issue("TEST-1", project_id="new-project")

            mock_move.assert_called_once_with("TEST-1", "new-project")
            assert result["status"] == "success"
            assert "successfully moved" in result["message"]

    @pytest.mark.asyncio
    async def test_move_issue_to_project_not_found(self, issue_service):
        """Test move issue to project when target project not found."""
        with (
            patch.object(issue_service, "_move_issue_to_project", new_callable=AsyncMock) as mock_move,
        ):
            mock_move.return_value = {
                "status": "error",
                "message": "Target project 'NONEXISTENT' not found. Please check the project short name or ID and ensure you have access to it.",
            }

            result = await issue_service.move_issue("TEST-1", project_id="NONEXISTENT")

            mock_move.assert_called_once_with("TEST-1", "NONEXISTENT")
            assert result["status"] == "error"
            assert "not found" in result["message"]

    @pytest.mark.asyncio
    async def test_move_issue_successful(self, issue_service):
        """Test successful issue state move with dynamic field discovery."""
        # Mock the update request
        update_response = MagicMock(spec=httpx.Response)
        update_response.status_code = 200

        with (
            patch.object(issue_service, "_get_project_id_from_issue", new_callable=AsyncMock) as mock_get_project,
            patch.object(issue_service, "_discover_state_field_for_project", new_callable=AsyncMock) as mock_discover,
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            # Mock dynamic field discovery
            mock_get_project.return_value = "TEST"
            mock_discover.return_value = {"field_name": "State", "bundle_type": "StateBundleElement"}

            # Mock API response
            mock_request.return_value = update_response
            mock_handle.return_value = {"status": "success", "message": "Issue TEST-1 moved to In Progress state"}

            result = await issue_service.move_issue("TEST-1", state="In Progress")

            # Verify field discovery was called
            mock_get_project.assert_called_once_with("TEST-1")
            mock_discover.assert_called_once_with("TEST")

            # Verify update request
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[0] == ("POST", "issues/TEST-1")
            update_data = call_args[1]["json_data"]
            assert update_data["$type"] == "Issue"
            assert len(update_data["customFields"]) == 1
            assert update_data["customFields"][0]["name"] == "State"
            assert update_data["customFields"][0]["$type"] == "SingleEnumIssueCustomField"
            assert update_data["customFields"][0]["value"]["$type"] == "StateBundleElement"
            assert update_data["customFields"][0]["value"]["name"] == "In Progress"

            assert result["status"] == "success"


class TestIssueServiceTags:
    """Test tag-related functionality."""

    @pytest.mark.asyncio
    async def test_add_tag(self, issue_service, mock_response):
        """Test adding a tag to an issue."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            # First call returns tag lookup result, second call returns add result
            mock_handle.side_effect = [
                {"status": "success", "data": [{"id": "10-1", "name": "urgent"}]},  # find_tag_by_name
                {"status": "success"},  # add_tag
            ]

            await issue_service.add_tag("TEST-1", "urgent")

            # Should call find_tag_by_name first, then add_tag with ID
            assert mock_request.call_count == 2
            mock_request.assert_any_call("GET", "tags", params={"fields": "id,name"})
            mock_request.assert_any_call("POST", "issues/TEST-1/tags", json_data={"id": "10-1"})

    @pytest.mark.asyncio
    async def test_remove_tag(self, issue_service, mock_response):
        """Test removing a tag from an issue."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            # First call returns tag lookup result, second call returns remove result
            mock_handle.side_effect = [
                {"status": "success", "data": [{"id": "10-1", "name": "urgent"}]},  # find_tag_by_name
                {"status": "success"},  # remove_tag
            ]

            await issue_service.remove_tag("TEST-1", "urgent")

            # Should call find_tag_by_name first, then remove_tag with ID
            assert mock_request.call_count == 2
            mock_request.assert_any_call("GET", "tags", params={"fields": "id,name"})
            mock_request.assert_any_call("DELETE", "issues/TEST-1/tags/10-1")

    @pytest.mark.asyncio
    async def test_list_tags(self, issue_service, mock_response):
        """Test listing tags for an issue."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"data": [{"name": "urgent"}]}

            await issue_service.list_tags("TEST-1")

            mock_request.assert_called_once_with("GET", "issues/TEST-1/tags", params={"fields": "id,name"})

    @pytest.mark.asyncio
    async def test_find_tag_by_name(self, issue_service, mock_response):
        """Test finding a tag by name."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": [{"id": "tag-1", "name": "urgent"}]}

            result = await issue_service.find_tag_by_name("urgent")

            mock_request.assert_called_once_with("GET", "tags", params={"fields": "id,name"})
            # Should filter the result to find the matching tag
            assert result["data"]["id"] == "tag-1"
            assert result["data"]["name"] == "urgent"

    @pytest.mark.asyncio
    async def test_create_tag(self, issue_service, mock_response):
        """Test creating a new tag."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": {"id": "tag-1"}}

            await issue_service.create_tag("new-tag")

            mock_request.assert_called_once_with("POST", "tags", json_data={"name": "new-tag"})
            mock_handle.assert_called_once_with(mock_response, success_codes=[200, 201])


class TestIssueServiceComments:
    """Test comment-related functionality."""

    @pytest.mark.asyncio
    async def test_add_comment(self, issue_service, mock_response):
        """Test adding a comment to an issue."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            await issue_service.add_comment("TEST-1", "This is a comment")

            mock_request.assert_called_once_with(
                "POST", "issues/TEST-1/comments", json_data={"text": "This is a comment"}
            )
            mock_handle.assert_called_once_with(mock_response, success_codes=[200, 201])

    @pytest.mark.asyncio
    async def test_list_comments(self, issue_service, mock_response):
        """Test listing comments for an issue."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"data": [{"id": "comment-1"}]}

            await issue_service.list_comments("TEST-1")

            mock_request.assert_called_once_with(
                "GET", "issues/TEST-1/comments", params={"fields": "id,text,created,updated,author(login,fullName)"}
            )

    @pytest.mark.asyncio
    async def test_update_comment(self, issue_service, mock_response):
        """Test updating a comment."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            await issue_service.update_comment("TEST-1", "comment-1", "Updated text")

            mock_request.assert_called_once_with(
                "POST", "issues/TEST-1/comments/comment-1", json_data={"text": "Updated text"}
            )

    @pytest.mark.asyncio
    async def test_delete_comment(self, issue_service, mock_response):
        """Test deleting a comment."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            await issue_service.delete_comment("TEST-1", "comment-1")

            mock_request.assert_called_once_with("DELETE", "issues/TEST-1/comments/comment-1")


class TestIssueServiceAttachments:
    """Test attachment-related functionality."""

    @pytest.mark.asyncio
    async def test_upload_attachment_success(self, issue_service):
        """Test successful attachment upload."""
        with (
            patch.object(issue_service, "_get_base_url") as mock_base_url,
            patch.object(issue_service, "_get_auth_headers") as mock_headers,
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Setup mocks
            mock_base_url.return_value = "https://youtrack.example.com"
            mock_headers.return_value = {"Authorization": "Bearer token"}

            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"id": "attachment-1"}'
            mock_response.json.return_value = {"id": "attachment-1"}
            mock_client.post.return_value = mock_response

            result = await issue_service.upload_attachment("TEST-1", "file.txt", b"content")

            assert result["status"] == "success"
            assert result["message"] == "Attachment uploaded successfully"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_attachment_success(self, issue_service):
        """Test successful attachment download."""
        with (
            patch.object(issue_service, "_get_base_url") as mock_base_url,
            patch.object(issue_service, "_get_auth_headers") as mock_headers,
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Setup mocks
            mock_base_url.return_value = "https://youtrack.example.com"
            mock_headers.return_value = {"Authorization": "Bearer token"}

            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock metadata response
            mock_metadata_response = MagicMock()
            mock_metadata_response.status_code = 200
            mock_metadata_response.json.return_value = {"name": "test.txt", "size": 12}

            # Mock content response
            mock_content_response = MagicMock()
            mock_content_response.status_code = 200
            mock_content_response.content = b"test content"
            mock_content_response.headers = {"content-type": "text/plain"}

            # Setup client get method to return different responses
            mock_client.get.side_effect = [mock_metadata_response, mock_content_response]

            result = await issue_service.download_attachment("TEST-1", "attachment-1")

            assert result["status"] == "success"
            assert result["data"]["content"] == b"test content"
            assert result["data"]["filename"] == "test.txt"
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_list_attachments(self, issue_service, mock_response):
        """Test listing attachments for an issue."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"data": [{"id": "attachment-1"}]}

            await issue_service.list_attachments("TEST-1")

            mock_request.assert_called_once_with(
                "GET", "issues/TEST-1/attachments", params={"fields": "id,name,size,created,author(login,fullName)"}
            )

    @pytest.mark.asyncio
    async def test_delete_attachment(self, issue_service, mock_response):
        """Test deleting an attachment."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            await issue_service.delete_attachment("TEST-1", "attachment-1")

            mock_request.assert_called_once_with("DELETE", "issues/TEST-1/attachments/attachment-1")


class TestIssueServiceLinks:
    """Test link-related functionality."""

    @pytest.mark.asyncio
    async def test_list_links(self, issue_service, mock_response):
        """Test listing links for an issue."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"data": [{"id": "link-1"}]}

            await issue_service.list_links("TEST-1")

            mock_request.assert_called_once_with(
                "GET",
                "issues/TEST-1/links",
                params={"fields": "id,direction,linkType(name),issues(id,idReadable,summary)"},
            )

    @pytest.mark.asyncio
    async def test_list_links_with_custom_fields(self, issue_service, mock_response):
        """Test listing links with custom fields."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"data": []}

            await issue_service.list_links("TEST-1", fields="id,linkType")

            mock_request.assert_called_once_with("GET", "issues/TEST-1/links", params={"fields": "id,linkType"})


class TestIssueServiceCustomFields:
    """Test custom field functionality."""

    @pytest.mark.asyncio
    async def test_get_custom_field_value(self, issue_service, mock_response):
        """Test getting custom field value."""
        with (
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(issue_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"data": {"customFields": [{"name": "Priority", "value": "High"}]}}

            await issue_service.get_custom_field_value("TEST-1", "Priority")

            mock_request.assert_called_once_with(
                "GET", "issues/TEST-1", params={"fields": "customFields(id,name,value)"}
            )


class TestIssueServiceErrorHandling:
    """Test error handling across all methods."""

    @pytest.mark.asyncio
    async def test_method_error_handling(self, issue_service):
        """Test that all methods handle exceptions properly."""
        methods_to_test = [
            ("get_issue", ("TEST-1",)),
            ("search_issues", ("query",)),
            ("delete_issue", ("TEST-1",)),
            ("add_tag", ("TEST-1", "tag")),
            ("remove_tag", ("TEST-1", "tag")),
            ("list_tags", ("TEST-1",)),
            ("find_tag_by_name", ("tag",)),
            ("create_tag", ("tag",)),
            ("add_comment", ("TEST-1", "text")),
            ("list_comments", ("TEST-1",)),
            ("update_comment", ("TEST-1", "comment-1", "text")),
            ("delete_comment", ("TEST-1", "comment-1")),
            ("list_attachments", ("TEST-1",)),
            ("delete_attachment", ("TEST-1", "attachment-1")),
            ("list_links", ("TEST-1",)),
            ("get_custom_field_value", ("TEST-1", "field")),
        ]

        for method_name, args in methods_to_test:
            with (
                patch.object(issue_service, "_make_request", new_callable=AsyncMock) as mock_request,
                patch.object(issue_service, "_create_error_response") as mock_error,
            ):
                mock_request.side_effect = Exception("Network error")
                mock_error.return_value = {"status": "error", "message": f"Error {method_name}: Network error"}

                method = getattr(issue_service, method_name)
                result = await method(*args)

                assert result["status"] == "error"
                # add_tag and remove_tag methods call _create_error_response twice (for find_tag_by_name and add_tag/remove_tag)
                if method_name in ["add_tag", "remove_tag"]:
                    assert mock_error.call_count == 2
                else:
                    mock_error.assert_called_once()


class TestCreateLinkNamesTheIssuesTheCallerTyped:
    """The link message must use the readable ids the caller passed (#780).

    `create_link` resolves both endpoints to internal ids (`3-482`) before posting, because the
    endpoint requires them — but the variables it overwrote were the ones the message then
    reported, so a successful link said `Link created between 3-482 and 3-481`. That is the same
    defect the create command had: the user typed a readable id, and an internal one is neither
    what they typed nor something they can paste into another command.
    """

    @pytest.mark.asyncio
    async def test_the_message_reports_what_the_caller_typed(self, issue_service, mock_response):
        with (
            patch.object(issue_service, "_resolve_issue_id", new_callable=AsyncMock) as resolve,
            patch.object(issue_service, "_make_request", new_callable=AsyncMock) as request,
        ):
            # The API needs internal ids; the message must not show them.
            resolve.side_effect = ["3-482", "3-481"]
            request.return_value = mock_response
            mock_response.status_code = 200

            result = await issue_service.create_link("PROJ-9", "PROJ-8", "166-1s")

        assert result["status"] == "success"
        assert "PROJ-9" in result["message"] and "PROJ-8" in result["message"]
        assert "3-482" not in result["message"], "an internal id is not an address a user can reuse"
