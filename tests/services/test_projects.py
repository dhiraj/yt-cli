"""Tests for ProjectService."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from youtrack_cli.auth import AuthManager
from youtrack_cli.exceptions import CustomFieldUnresolvedReason
from youtrack_cli.services.projects import ProjectService


@pytest.fixture
def auth_manager():
    """Create a mock auth manager."""
    mock_auth = MagicMock(spec=AuthManager)
    return mock_auth


@pytest.fixture
def project_service(auth_manager):
    """Create a ProjectService instance."""
    return ProjectService(auth_manager)


@pytest.fixture
def mock_response():
    """Create a mock HTTP response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {"id": "PROJECT-1", "name": "Test Project"}
    response.headers = {"content-type": "application/json"}
    response.text = '{"id": "PROJECT-1", "name": "Test Project"}'
    return response


class TestProjectServiceListProjects:
    """Test project listing functionality."""

    @pytest.mark.asyncio
    async def test_list_projects_basic(self, project_service, mock_response):
        """Test basic project listing."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {
                "status": "success",
                "data": [
                    {"id": "proj-1", "name": "Project 1", "archived": False},
                    {"id": "proj-2", "name": "Project 2", "archived": True},
                ],
            }

            result = await project_service.list_projects()

            expected_params = {
                "fields": "id,name,shortName,description,leader(login,fullName),archived,createdBy(login,fullName)"
            }
            mock_request.assert_called_once_with("GET", "admin/projects", params=expected_params)
            mock_handle.assert_called_once_with(mock_response)

            # Should filter out archived projects by default
            assert result["status"] == "success"
            assert len(result["data"]) == 1
            assert result["data"][0]["id"] == "proj-1"

    @pytest.mark.asyncio
    async def test_list_projects_with_archived(self, project_service, mock_response):
        """Test listing projects including archived ones."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {
                "status": "success",
                "data": [
                    {"id": "proj-1", "name": "Project 1", "archived": False},
                    {"id": "proj-2", "name": "Project 2", "archived": True},
                ],
            }

            result = await project_service.list_projects(show_archived=True)

            # Should include all projects when show_archived=True
            assert result["status"] == "success"
            assert len(result["data"]) == 2

    @pytest.mark.asyncio
    async def test_list_projects_with_parameters(self, project_service, mock_response):
        """Test listing projects with all parameters."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": []}

            result = await project_service.list_projects(fields="id,name", top=10, skip=5, show_archived=True)

            expected_params = {"fields": "id,name", "$top": "10", "$skip": "5"}
            mock_request.assert_called_once_with("GET", "admin/projects", params=expected_params)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_list_projects_value_error(self, project_service):
        """Test list projects with ValueError."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = ValueError("Invalid data")
            mock_error.return_value = {"status": "error", "message": "Invalid data"}

            result = await project_service.list_projects()

            mock_error.assert_called_once_with("Invalid data")
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_list_projects_general_exception(self, project_service):
        """Test list projects with general exception."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = Exception("Network error")
            mock_error.return_value = {"status": "error", "message": "Error listing projects: Network error"}

            result = await project_service.list_projects()

            mock_error.assert_called_once_with("Error listing projects: Network error")
            assert result["status"] == "error"


class TestProjectServiceGetProject:
    """Test project retrieval functionality."""

    @pytest.mark.asyncio
    async def test_get_project_basic(self, project_service, mock_response):
        """Test basic project retrieval."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": {"id": "TEST", "name": "Test Project"}}

            result = await project_service.get_project("TEST")

            expected_params = {
                "fields": "id,name,shortName,description,leader(login,fullName),archived,createdBy(login,fullName),team(users(login,fullName))"
            }
            mock_request.assert_called_once_with("GET", "admin/projects/TEST", params=expected_params)
            mock_handle.assert_called_once_with(mock_response)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_project_with_custom_fields(self, project_service, mock_response):
        """Test project retrieval with custom fields."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": {"id": "TEST"}}

            result = await project_service.get_project("TEST", fields="id,name")

            expected_params = {"fields": "id,name"}
            mock_request.assert_called_once_with("GET", "admin/projects/TEST", params=expected_params)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_project_error_handling(self, project_service):
        """Test get project error handling."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = Exception("Network error")
            mock_error.return_value = {"status": "error", "message": "Error getting project: Network error"}

            result = await project_service.get_project("TEST")

            mock_error.assert_called_once_with("Error getting project: Network error")
            assert result["status"] == "error"


class TestProjectServiceCreateProject:
    """Test project creation functionality."""

    @pytest.mark.asyncio
    async def test_create_project_basic(self, project_service, mock_response):
        """Test basic project creation."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": {"id": "TEST"}}

            result = await project_service.create_project("TEST", "Test Project")

            expected_data = {"shortName": "TEST", "name": "Test Project"}
            mock_request.assert_called_once_with("POST", "admin/projects", json_data=expected_data)
            mock_handle.assert_called_once_with(mock_response, success_codes=[200, 201])
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_create_project_with_all_fields(self, project_service, mock_response):
        """Test project creation with all optional fields."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.create_project(
                short_name="TEST", name="Test Project", description="Test Description", leader_login="testuser"
            )

            expected_data = {
                "shortName": "TEST",
                "name": "Test Project",
                "description": "Test Description",
                "leader": {"id": "testuser"},
            }
            mock_request.assert_called_once_with("POST", "admin/projects", json_data=expected_data)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_create_project_error_handling(self, project_service):
        """Test create project error handling."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = ValueError("Invalid data")
            mock_error.return_value = {"status": "error", "message": "Invalid data"}

            result = await project_service.create_project("TEST", "Test Project")

            mock_error.assert_called_once_with("Invalid data")
            assert result["status"] == "error"


class TestProjectServiceUpdateProject:
    """Test project update functionality."""

    @pytest.mark.asyncio
    async def test_update_project_basic(self, project_service, mock_response):
        """Test basic project update."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.update_project("TEST", name="New Name")

            expected_data = {"name": "New Name"}
            mock_request.assert_called_once_with("POST", "admin/projects/TEST", json_data=expected_data)
            mock_handle.assert_called_once_with(mock_response)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_update_project_all_fields(self, project_service, mock_response):
        """Test project update with all fields."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.update_project(
                "TEST", name="New Name", description="New Description", leader_login="newuser", archived=True
            )

            expected_data = {
                "name": "New Name",
                "description": "New Description",
                "leader": {"id": "newuser"},
                "archived": True,
            }
            mock_request.assert_called_once_with("POST", "admin/projects/TEST", json_data=expected_data)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_update_project_error_handling(self, project_service):
        """Test update project error handling."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = Exception("Network error")
            mock_error.return_value = {"status": "error", "message": "Error updating project: Network error"}

            result = await project_service.update_project("TEST", name="New Name")

            mock_error.assert_called_once_with("Error updating project: Network error")
            assert result["status"] == "error"


class TestProjectServiceDeleteProject:
    """Test project deletion functionality."""

    @pytest.mark.asyncio
    async def test_delete_project(self, project_service, mock_response):
        """Test project deletion."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.delete_project("TEST")

            mock_request.assert_called_once_with("DELETE", "admin/projects/TEST")
            mock_handle.assert_called_once_with(mock_response)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_delete_project_error_handling(self, project_service):
        """Test delete project error handling."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = ValueError("Invalid ID")
            mock_error.return_value = {"status": "error", "message": "Invalid ID"}

            result = await project_service.delete_project("TEST")

            mock_error.assert_called_once_with("Invalid ID")
            assert result["status"] == "error"


class TestProjectServiceArchive:
    """Test project archiving functionality."""

    @pytest.mark.asyncio
    async def test_archive_project(self, project_service, mock_response):
        """Test archiving a project."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.archive_project("TEST")

            expected_data = {"archived": True}
            mock_request.assert_called_once_with("POST", "admin/projects/TEST", json_data=expected_data)
            mock_handle.assert_called_once_with(mock_response)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_unarchive_project(self, project_service, mock_response):
        """Test unarchiving a project."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.unarchive_project("TEST")

            expected_data = {"archived": False}
            mock_request.assert_called_once_with("POST", "admin/projects/TEST", json_data=expected_data)
            mock_handle.assert_called_once_with(mock_response)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_archive_project_error_handling(self, project_service):
        """Test archive project error handling."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = Exception("Network error")
            mock_error.return_value = {"status": "error", "message": "Error archiving project: Network error"}

            result = await project_service.archive_project("TEST")

            mock_error.assert_called_once_with("Error archiving project: Network error")
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_unarchive_project_error_handling(self, project_service):
        """Test unarchive project error handling."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = Exception("Network error")
            mock_error.return_value = {"status": "error", "message": "Error unarchiving project: Network error"}

            result = await project_service.unarchive_project("TEST")

            mock_error.assert_called_once_with("Error unarchiving project: Network error")
            assert result["status"] == "error"


class TestProjectServiceTeam:
    """Test project team management functionality."""

    @pytest.mark.asyncio
    async def test_get_project_team(self, project_service, mock_response):
        """Test getting project team."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": []}

            result = await project_service.get_project_team("TEST")

            expected_params = {"fields": "login,fullName,email,avatarUrl"}
            mock_request.assert_called_once_with("GET", "admin/projects/TEST/team", params=expected_params)
            mock_handle.assert_called_once_with(mock_response)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_project_team_custom_fields(self, project_service, mock_response):
        """Test getting project team with custom fields."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": []}

            result = await project_service.get_project_team("TEST", fields="login,fullName")

            expected_params = {"fields": "login,fullName"}
            mock_request.assert_called_once_with("GET", "admin/projects/TEST/team", params=expected_params)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_add_team_member(self, project_service, mock_response):
        """Test adding a team member."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.add_team_member("TEST", "testuser")

            expected_data = {"login": "testuser"}
            mock_request.assert_called_once_with("POST", "admin/projects/TEST/team", json_data=expected_data)
            mock_handle.assert_called_once_with(mock_response, success_codes=[200, 201])
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_remove_team_member(self, project_service, mock_response):
        """Test removing a team member."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.remove_team_member("TEST", "testuser")

            mock_request.assert_called_once_with("DELETE", "admin/projects/TEST/team/testuser")
            mock_handle.assert_called_once_with(mock_response)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_team_management_error_handling(self, project_service):
        """Test team management error handling."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = Exception("Network error")
            mock_error.return_value = {"status": "error", "message": "Error getting project team: Network error"}

            result = await project_service.get_project_team("TEST")

            mock_error.assert_called_once_with("Error getting project team: Network error")
            assert result["status"] == "error"


class TestProjectServiceCustomFields:
    """Test project custom fields functionality."""

    @pytest.mark.asyncio
    async def test_get_project_custom_fields(self, project_service, mock_response):
        """Test getting project custom fields."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": []}

            result = await project_service.get_project_custom_fields("TEST")

            expected_params = {"fields": "id,field(name,fieldType),canBeEmpty,isPublic,ordinal"}
            mock_request.assert_called_once_with("GET", "admin/projects/TEST/customFields", params=expected_params)
            mock_handle.assert_called_once_with(mock_response)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_attach_custom_field(self, project_service, mock_response):
        """Test attaching a custom field."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.attach_custom_field("TEST", "field-1", is_public=True)

            expected_data = {"field": {"id": "field-1"}, "isPublic": True}
            mock_request.assert_called_once_with("POST", "admin/projects/TEST/customFields", json_data=expected_data)
            mock_handle.assert_called_once_with(mock_response, success_codes=[200, 201])
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_attach_custom_field_minimal(self, project_service, mock_response):
        """Test attaching a custom field with minimal parameters."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.attach_custom_field("TEST", "field-1")

            expected_data = {"field": {"id": "field-1"}}
            mock_request.assert_called_once_with("POST", "admin/projects/TEST/customFields", json_data=expected_data)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_detach_custom_field(self, project_service, mock_response):
        """Test detaching a custom field."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.detach_custom_field("TEST", "field-1")

            mock_request.assert_called_once_with("DELETE", "admin/projects/TEST/customFields/field-1")
            mock_handle.assert_called_once_with(mock_response)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_custom_fields_error_handling(self, project_service):
        """Test custom fields error handling."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = Exception("Network error")
            mock_error.return_value = {
                "status": "error",
                "message": "Error getting project custom fields: Network error",
            }

            result = await project_service.get_project_custom_fields("TEST")

            mock_error.assert_called_once_with("Error getting project custom fields: Network error")
            assert result["status"] == "error"


class TestProjectServiceVersions:
    """Test project versions functionality."""

    @pytest.mark.asyncio
    async def test_get_project_versions(self, project_service, mock_response):
        """Test getting project versions."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": []}

            result = await project_service.get_project_versions("TEST")

            expected_params = {"fields": "id,name,description,archived,released,releaseDate"}
            mock_request.assert_called_once_with("GET", "admin/projects/TEST/versions", params=expected_params)
            mock_handle.assert_called_once_with(mock_response)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_project_versions_custom_fields(self, project_service, mock_response):
        """Test getting project versions with custom fields."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success", "data": []}

            result = await project_service.get_project_versions("TEST", fields="id,name")

            expected_params = {"fields": "id,name"}
            mock_request.assert_called_once_with("GET", "admin/projects/TEST/versions", params=expected_params)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_create_project_version_basic(self, project_service, mock_response):
        """Test creating a project version."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.create_project_version("TEST", "v1.0")

            expected_data = {"name": "v1.0"}
            mock_request.assert_called_once_with("POST", "admin/projects/TEST/versions", json_data=expected_data)
            mock_handle.assert_called_once_with(mock_response, success_codes=[200, 201])
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_create_project_version_all_fields(self, project_service, mock_response):
        """Test creating a project version with all fields."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = mock_response
            mock_handle.return_value = {"status": "success"}

            result = await project_service.create_project_version(
                "TEST", "v1.0", description="First version", released=True, archived=False
            )

            expected_data = {"name": "v1.0", "description": "First version", "released": True, "archived": False}
            mock_request.assert_called_once_with("POST", "admin/projects/TEST/versions", json_data=expected_data)
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_versions_error_handling(self, project_service):
        """Test versions error handling."""
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_create_error_response") as mock_error,
        ):
            mock_request.side_effect = Exception("Network error")
            mock_error.return_value = {"status": "error", "message": "Error getting project versions: Network error"}

            result = await project_service.get_project_versions("TEST")

            mock_error.assert_called_once_with("Error getting project versions: Network error")
            assert result["status"] == "error"


class TestProjectToIssueFieldType:
    """Test the project-field-type -> issue-field-type lookup.

    The project admin API names a field by *kind* ("UserProjectCustomField") and reports
    multiplicity separately, on the field's `fieldType` (`isMultiValue`, or the `[*]`
    suffix on `fieldType.id`). Two things follow, and both are pinned here because
    getting either wrong silently mistypes a write:

    * there is no "Multi...ProjectCustomField" to key on -- the project side never names
      multiplicity, so a lookup keyed on it matches nothing;
    * the same kind is single-valued in one project and multi-valued in another, so the
      kind alone cannot decide the issue-side spelling.

    Every project type below is a string a real instance returned, and each
    `is_multi_value` is a value the same instance reported for that field.
    """

    @pytest.mark.parametrize(
        ("project_type", "is_multi_value", "expected"),
        [
            # Kind-only vocabulary, single-valued instances.
            ("EnumProjectCustomField", False, "SingleEnumIssueCustomField"),
            ("OwnedProjectCustomField", False, "SingleOwnedIssueCustomField"),
            ("StateProjectCustomField", False, "StateIssueCustomField"),
            ("UserProjectCustomField", False, "SingleUserIssueCustomField"),
            ("BuildProjectCustomField", False, "SingleBuildIssueCustomField"),
            ("TextProjectCustomField", False, "TextIssueCustomField"),
            ("SimpleProjectCustomField", False, "SimpleIssueCustomField"),
            # The same kinds, multi-valued instances.
            ("EnumProjectCustomField", True, "MultiEnumIssueCustomField"),
            ("OwnedProjectCustomField", True, "MultiOwnedIssueCustomField"),
            ("UserProjectCustomField", True, "MultiUserIssueCustomField"),
            ("VersionProjectCustomField", True, "MultiVersionIssueCustomField"),
            ("BuildProjectCustomField", True, "MultiBuildIssueCustomField"),
            # The pair that a kind-keyed lookup cannot express: this is one kind, and
            # which issue type it maps to is decided by the field, not by the kind.
            ("VersionProjectCustomField", False, "SingleVersionIssueCustomField"),
        ],
    )
    def test_known_project_types_map_to_issue_types(self, project_service, project_type, is_multi_value, expected):
        assert project_service._project_to_issue_field_type(project_type, is_multi_value) == expected

    @pytest.mark.parametrize(
        "project_type",
        [
            "SomethingNewProjectCustomField",
            "DateProjectCustomField",
            "PeriodProjectCustomField",
            "DateTimeProjectCustomField",
            "MultiEnumProjectCustomField",
            "MultiUserProjectCustomField",
            "MultiVersionProjectCustomField",
            "",
        ],
    )
    def test_unmapped_type_returns_none_rather_than_defaulting(self, project_service, project_type):
        """An unmapped type must be reported as unknown, never defaulted.

        Defaulting is what turned a missing mapping into a silently mistyped write: the
        caller had no way to tell a real enum field from a user field it could not map.

        The `Multi...ProjectCustomField` rows are here as the negative case that motivates
        the multiplicity argument: they are strings this CLI used to recognise, and the
        API never returns one, so a mapping keyed on them is unreachable.
        """
        assert project_service._project_to_issue_field_type(project_type, is_multi_value=False) is None

    @pytest.mark.parametrize(
        "project_type",
        [
            "EnumProjectCustomField",
            "OwnedProjectCustomField",
            "UserProjectCustomField",
            "VersionProjectCustomField",
            "BuildProjectCustomField",
        ],
    )
    def test_bundle_kind_with_unreported_multiplicity_is_unresolvable(self, project_service, project_type):
        """An unreported multiplicity must not collapse into a single/multi guess.

        The value shape follows from this answer -- one element for a single-valued
        field, a list for a multi-valued one -- so choosing either would be a guess that
        the server either rejects as a type mismatch or, worse, accepts as something
        other than what was asked for.
        """
        assert project_service._project_to_issue_field_type(project_type, is_multi_value=None) is None

    def test_unreported_multiplicity_does_not_block_kinds_that_have_no_such_distinction(self, project_service):
        """A state or text field is single-valued whatever the server says.

        Refusing these on an absent `isMultiValue` would be refusing a field whose shape
        was never in question, so the refusal is scoped to the bundle-backed kinds.
        """
        assert (
            project_service._project_to_issue_field_type("StateProjectCustomField", is_multi_value=None)
            == "StateIssueCustomField"
        )
        assert (
            project_service._project_to_issue_field_type("TextProjectCustomField", is_multi_value=None)
            == "TextIssueCustomField"
        )


class TestDiscoverCustomField:
    """Test the discovery result the write path is built from.

    `discover_custom_field` is what tells `create_field_by_type` a field's type, whether
    it holds one value or several, and -- when neither can be established -- *why* not.
    Every other custom-field test mocks this function, so its own decision logic is only
    observable here: a wrong `is_multi_value` silently mistypes every write, and a wrong
    `unresolved_reason` blames the wrong cause on the reader.
    """

    @staticmethod
    def _listed(name, project_type, is_multi_value):
        return {
            "id": "180-26",
            "$type": project_type,
            "field": {"name": name, "fieldType": {"isMultiValue": is_multi_value}},
        }

    @staticmethod
    def _detail(project_type, is_multi_value):
        return {
            "id": "180-26",
            "$type": project_type,
            "field": {"name": "Sprint", "fieldType": {"isMultiValue": is_multi_value}},
        }

    @staticmethod
    async def _discover(project_service, listed, detail, field_name=None):
        # Discovery looks the field up by name, so the name asked for has to be the one
        # the listing carries unless a case is specifically about a name that is not there.
        asked = field_name if field_name is not None else (listed["field"]["name"])
        with (
            patch.object(
                project_service,
                "get_project_custom_fields",
                new=AsyncMock(return_value={"status": "success", "data": [listed]}),
            ),
            patch.object(
                project_service,
                "get_custom_field_details",
                new=AsyncMock(return_value={"status": "success", "data": detail}),
            ),
        ):
            return await project_service.discover_custom_field("VAN", asked)

    @pytest.fixture(autouse=True)
    def _clear_field_cache(self):
        """Discovery memoises per project, so a cached result would mask the next case."""
        from youtrack_cli.services.field_cache import get_field_cache

        get_field_cache().clear()
        yield
        get_field_cache().clear()

    @pytest.mark.asyncio
    async def test_a_multi_valued_field_is_reported_as_such(self, project_service):
        result = await self._discover(
            project_service,
            self._listed("Sprint", "EnumProjectCustomField", True),
            self._detail("EnumProjectCustomField", True),
        )
        assert result["status"] == "success"
        assert result["data"]["is_multi_value"] is True
        assert result["data"]["issue_field_type"] == "MultiEnumIssueCustomField"
        assert result["data"]["unresolved_reason"] is None

    @pytest.mark.asyncio
    async def test_a_single_valued_field_is_reported_as_such(self, project_service):
        result = await self._discover(
            project_service,
            self._listed("Repo", "EnumProjectCustomField", False),
            self._detail("EnumProjectCustomField", False),
        )
        assert result["data"]["is_multi_value"] is False
        assert result["data"]["issue_field_type"] == "SingleEnumIssueCustomField"
        assert result["data"]["unresolved_reason"] is None

    @pytest.mark.asyncio
    async def test_an_unrecognised_kind_is_blamed_on_the_type(self, project_service):
        result = await self._discover(
            project_service,
            self._listed("Due", "DateProjectCustomField", False),
            self._detail("DateProjectCustomField", False),
        )
        assert result["data"]["issue_field_type"] is None
        assert result["data"]["unresolved_reason"] == CustomFieldUnresolvedReason.TYPE

    @pytest.mark.asyncio
    async def test_an_unreported_multiplicity_is_blamed_on_the_multiplicity(self, project_service):
        """The two causes must stay apart: one is a CLI gap, the other a response gap.

        Reporting a missing `isMultiValue` as an unknown type would send the reader
        looking for a vocabulary problem in a kind this CLI handles perfectly well.
        """
        detail = {"id": "180-26", "$type": "EnumProjectCustomField", "field": {"name": "Sprint"}}
        listed = {"id": "180-26", "$type": "EnumProjectCustomField", "field": {"name": "Sprint"}}
        result = await self._discover(project_service, listed, detail)
        assert result["data"]["is_multi_value"] is None
        assert result["data"]["issue_field_type"] is None
        assert result["data"]["unresolved_reason"] == CustomFieldUnresolvedReason.MULTIPLICITY

    @pytest.mark.asyncio
    async def test_an_unreported_multiplicity_on_a_single_valued_kind_is_still_a_type_gap(self, project_service):
        """A state field's shape was never in question, so its absence is not the cause.

        `isMultiValue` is absent for kinds that have no single/multi distinction, and
        blaming that on the response would refuse a field whose payload is fully known.
        """
        result = await self._discover(
            project_service,
            self._listed("State", "StateProjectCustomField", None),
            self._detail("StateProjectCustomField", None),
        )
        assert result["data"]["issue_field_type"] == "StateIssueCustomField"
        assert result["data"]["unresolved_reason"] is None

    @pytest.mark.asyncio
    async def test_the_list_entry_answers_when_the_detail_read_omits_the_flag(self, project_service):
        """Both reads see the same field, and either can be the one carrying the flag."""
        result = await self._discover(
            project_service,
            self._listed("Fix versions", "VersionProjectCustomField", True),
            {"id": "180-26", "$type": "VersionProjectCustomField", "field": {"name": "Fix versions"}},
        )
        assert result["data"]["is_multi_value"] is True
        assert result["data"]["issue_field_type"] == "MultiVersionIssueCustomField"

    @pytest.mark.asyncio
    async def test_the_bundle_element_type_is_reported_for_enum_fields(self, project_service):
        """The value discriminator comes from the bundle, and the write path needs it."""
        detail = self._detail("EnumProjectCustomField", True)
        detail["bundle"] = {"values": [{"$type": "EnumBundleElement", "id": "0-0", "name": "Sprint 1"}]}
        with (
            patch.object(
                project_service,
                "get_project_custom_fields",
                new=AsyncMock(
                    return_value={"status": "success", "data": [self._listed("Sprint", "EnumProjectCustomField", True)]}
                ),
            ),
            patch.object(
                project_service,
                "get_custom_field_details",
                new=AsyncMock(return_value={"status": "success", "data": detail}),
            ),
        ):
            result = await project_service.discover_custom_field("VAN", "Sprint")
        assert result["data"]["bundle_element_type"] == "EnumBundleElement"

    @pytest.mark.asyncio
    async def test_the_field_name_is_matched_case_insensitively(self, project_service):
        result = await self._discover(
            project_service,
            self._listed("Sprint", "EnumProjectCustomField", True),
            self._detail("EnumProjectCustomField", True),
        )
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_an_unknown_field_lists_what_is_available(self, project_service):
        """A name that is not there is answered with the names that are."""
        listed = self._listed("Sprint", "EnumProjectCustomField", True)
        with (
            patch.object(
                project_service,
                "get_project_custom_fields",
                new=AsyncMock(return_value={"status": "success", "data": [listed]}),
            ),
            patch.object(project_service, "get_custom_field_details", new=AsyncMock()) as mock_details,
        ):
            result = await project_service.discover_custom_field("VAN", "Sprints")

        assert result["status"] == "error"
        assert "Sprint" in result["available_fields"]
        mock_details.assert_not_called()


class TestCustomFieldSelectors:
    """The `fields=` selectors these reads send, and what the write path needs from them.

    A selector is the only way to ask for a field of a response: YouTrack returns exactly
    what is named and nothing else. So a selector that quietly omits `isMultiValue` does
    not degrade -- it makes every bundle-backed `--custom-field` refuse, while the rest of
    the suite stays green, because every other test mocks these two methods. The strings
    are therefore asserted here, not just the parsing of a hand-built response.
    """

    MULTIPLICITY = "isMultiValue"
    ARITY = "id"

    @staticmethod
    async def _selector_used_by_detail_read(project_service):
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = MagicMock(spec=httpx.Response)
            mock_handle.return_value = {"status": "success", "data": {"id": "180-26"}}
            await project_service.get_custom_field_details("VAN", "180-26", include_bundle=False)
        return mock_request.call_args.kwargs["params"]["fields"]

    @staticmethod
    async def _selector_used_by_discovery(project_service):
        with (
            patch.object(project_service, "get_project_custom_fields", new_callable=AsyncMock) as mock_list,
            patch.object(project_service, "get_custom_field_details", new_callable=AsyncMock) as mock_details,
        ):
            mock_list.return_value = {"status": "success", "data": []}
            mock_details.return_value = {"status": "success", "data": {"$type": "EnumProjectCustomField"}}
            await project_service.discover_custom_field("VAN", "Sprint")
        return mock_list.call_args.kwargs["fields"]

    @pytest.mark.asyncio
    async def test_the_detail_read_asks_for_the_field_types_multiplicity(self, project_service):
        selector = await self._selector_used_by_detail_read(project_service)
        assert "field(fieldType(" in selector, "multiplicity is read off the attached field type"
        assert self.MULTIPLICITY in selector

    @pytest.mark.asyncio
    async def test_the_list_read_asks_for_the_field_types_multiplicity(self, project_service):
        selector = await self._selector_used_by_discovery(project_service)
        assert "field(fieldType(" in selector
        assert self.MULTIPLICITY in selector

    @pytest.mark.asyncio
    async def test_both_selectors_name_the_multiplicity_inside_the_field_type(self, project_service):
        """`isMultiValue` has to be selected on the field's own type, not top level.

        Selected at the top level it comes back absent rather than wrong: the request
        succeeds, the field is simply not in the response, and every bundle-backed write
        refuses with a multiplicity complaint about a server that did report it.
        """
        for selector in (
            await self._selector_used_by_detail_read(project_service),
            await self._selector_used_by_discovery(project_service),
        ):
            # Asserted on the nested fragment, not the whole selector: the whole selector
            # opens with a bare `id`, which would satisfy an `ARITY` check by accident.
            nested = selector.split("field(fieldType(", 1)[1].split(")", 1)[0]
            assert self.MULTIPLICITY in nested
            assert self.ARITY in nested, "the arity suffix is the second, independent source"

    @pytest.mark.asyncio
    async def test_a_selector_that_already_names_a_field_is_not_given_a_second_clause(self, project_service):
        """The `field(name)` fallback must not be appended on top of a nested selector.

        `get_project_custom_fields` appends `field(name)` when the caller's selector does
        not look like it already asks for a name. That test used to be run per
        comma-separated fragment, and a `field(...)` clause containing commas of its own
        is one fragment that *does* name a field -- so the check failed, a duplicate
        `field(name)` was appended, and the request asked for the same projection twice.
        Whether the server tolerates that is not something to find out in production, and
        the failure mode is total: discovery returns a field with no `fieldType` and every
        bundle-backed write refuses.

        Asserted against what reaches `_make_request`, because that composed string --
        not the string handed to this method -- is what the server sees.
        """
        composed = await self._selector_sent_to_the_server(
            project_service,
            "id,name,fieldType,localizedName,isPublic,ordinal,field(fieldType(id,name,isMultiValue),name,$type)",
        )
        assert composed == (
            "id,name,fieldType,localizedName,isPublic,ordinal,field(fieldType(id,name,isMultiValue),name,$type)"
        )
        assert composed.count("field(") == 1

    @pytest.mark.asyncio
    async def test_a_selector_without_any_field_clause_still_gets_one(self, project_service):
        """The fallback is for callers who did not ask; it must still fire for them."""
        composed = await self._selector_sent_to_the_server(project_service, "id,name,isPublic")
        assert composed == "id,name,isPublic,field(name)"

    @pytest.mark.asyncio
    async def test_a_nested_name_is_not_mistaken_for_the_fields_own(self, project_service):
        """`field(fieldType(id,name))` asks for the *field type's* name, not the field's.

        Reading it as satisfied suppresses the `field(name)` the display path needs, and
        every name then renders as `N/A`. A substring test cannot tell that apart from
        `field(fieldType(name),name)`, which does name the field.
        """
        composed = await self._selector_sent_to_the_server(project_service, "id,name,field(fieldType(id,name))")
        assert composed == "id,name,field(fieldType(id,name)),field(name)"

    @pytest.mark.asyncio
    async def test_a_name_beside_a_nested_one_still_counts(self, project_service):
        composed = await self._selector_sent_to_the_server(project_service, "id,name,field(fieldType(name),name,$type)")
        assert composed == "id,name,field(fieldType(name),name,$type)"
        assert composed.count("field(") == 1

    @pytest.mark.asyncio
    async def test_a_nested_field_name_clause_still_counts(self, project_service):
        """A `field(name)` nested inside another clause is still a request for a name.

        The scan resumes *inside* a clause rather than past it, so this is answered
        without appending a second `field(...)`; dropping that behaviour leaves the
        request asking for the same projection twice.
        """
        composed = await self._selector_sent_to_the_server(project_service, "id,name,field(field(name),x)")
        assert composed == "id,name,field(field(name),x)"
        assert composed.count("field(") == 2

    @pytest.mark.asyncio
    async def test_a_comma_inside_brackets_still_separates_arguments(self, project_service):
        """Only parentheses nest, so a comma inside brackets separates arguments.

        YouTrack's `fields` syntax has no bracketed form; treating `[` as nesting too
        would be a rule about a syntax that does not exist. Either way this clause does
        not name the field, so the fallback is appended -- what is pinned here is that
        the answer does not depend on the bracket handling.
        """
        composed = await self._selector_sent_to_the_server(project_service, "id,name,field(fieldType[id,name])")
        assert composed == "id,name,field(fieldType[id,name]),field(name)"

    @pytest.mark.asyncio
    async def test_an_unterminated_clause_does_not_hang_or_claim_a_name(self, project_service):
        """A malformed selector is the server's to reject, not a reason to hang here."""
        composed = await self._selector_sent_to_the_server(project_service, "id,field(name")
        assert composed == "id,field(name,field(name)"

    @staticmethod
    async def _selector_sent_to_the_server(project_service, fields):
        with (
            patch.object(project_service, "_make_request", new_callable=AsyncMock) as mock_request,
            patch.object(project_service, "_handle_response", new_callable=AsyncMock) as mock_handle,
        ):
            mock_request.return_value = MagicMock(spec=httpx.Response)
            mock_handle.return_value = {"status": "success", "data": []}
            await project_service.get_project_custom_fields("VAN", fields=fields)
        return mock_request.call_args.kwargs["params"]["fields"]


class TestIsMultiValue:
    """Test reading multiplicity off a discovered field."""

    def test_reads_is_multi_value_from_the_field_detail_read(self, project_service):
        field_data = {"$type": "VersionProjectCustomField", "field": {"fieldType": {"isMultiValue": True}}}
        assert project_service._is_multi_value(field_data, {}) is True

    def test_falls_back_to_the_list_entry_when_the_detail_omits_it(self, project_service):
        """Both reads see the same field, and either can be the one that carries it.

        The detail read is preferred because it is the field being written, but a
        response that omits the flag there while carrying it in the list entry is
        still answerable, and refusing it would refuse a field we can state exactly.
        """
        field_data = {"$type": "VersionProjectCustomField", "field": {"fieldType": {"id": "version[*]"}}}
        listed = {"field": {"fieldType": {"isMultiValue": True}}}
        assert project_service._is_multi_value(field_data, listed) is True

    def test_falls_back_to_the_star_suffix_on_the_field_type_id(self, project_service):
        """`fieldType.id` spells the same fact: `enum[1]` vs `version[*]`.

        Kept as a second source because a response carrying the id but not the boolean
        is still a complete answer about shape, and `[*]` is unambiguous.
        """
        field_data = {"$type": "VersionProjectCustomField", "field": {"fieldType": {"id": "version[*]"}}}
        assert project_service._is_multi_value(field_data, {}) is True

    def test_single_valued_field_type_id_is_not_multi(self, project_service):
        field_data = {"$type": "BuildProjectCustomField", "field": {"fieldType": {"id": "build[1]"}}}
        assert project_service._is_multi_value(field_data, {}) is False

    def test_absent_from_both_reads_is_unknown_rather_than_single(self, project_service):
        """Neither reported means unknown, which is not the same as one value.

        Collapsing the two is what makes a missing flag indistinguishable from a
        single-valued field -- and therefore a guess rather than a refusal.
        """
        field_data = {"$type": "EnumProjectCustomField", "field": {"fieldType": {"$type": "FieldType"}}}
        assert project_service._is_multi_value(field_data, {}) is None

    def test_a_false_flag_is_honoured_over_a_star_suffix_in_the_other_read(self, project_service):
        """An explicit `false` is an answer; a `[*]` spelled elsewhere must not override it.

        The two reads are of the same field, so a disagreement means one selection was
        dropped, not that the field changed. The boolean wins because it *is* the
        multiplicity and the arity suffix only spells it -- whichever read carried the
        boolean, the arity in the other read does not get to overrule it.
        """
        field_data = {"$type": "BuildProjectCustomField", "field": {"fieldType": {"isMultiValue": False}}}
        listed = {"field": {"fieldType": {"id": "build[*]"}}}
        assert project_service._is_multi_value(field_data, listed) is False

    def test_the_detail_read_wins_within_the_arity_signal_too(self, project_service):
        """The precedence has two levels, and this pins the second.

        Every `isMultiValue` beats every arity `id`; *within* a signal, the detail read --
        the field being written -- beats the list read. So when both reads carry an arity
        and they disagree, the detail read's is the answer.
        """
        detail_says_single = {"$type": "BuildProjectCustomField", "field": {"fieldType": {"id": "build[1]"}}}
        list_says_multi = {"field": {"fieldType": {"id": "build[*]"}}}
        assert project_service._is_multi_value(detail_says_single, list_says_multi) is False

    def test_an_arity_in_the_only_read_that_carries_one_answers(self, project_service):
        """The case that keeps the second loop reachable at all.

        With no boolean in either read, an arity is the only evidence there is, and
        refusing here would refuse a field whose shape the response did state. The
        detail-read-only half of this is covered by
        `test_single_valued_field_type_id_is_not_multi`; what is new here is an arity
        that arrives solely from the *list* read, which no other case exercises.
        """
        ar_only_in_list = {"$type": "VersionProjectCustomField", "field": {"name": "Fix versions"}}
        listed = {"field": {"fieldType": {"id": "version[*]"}}}
        assert project_service._is_multi_value(ar_only_in_list, listed) is True
