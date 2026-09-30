"""Project service for YouTrack API operations."""

import re
from typing import Any

from ..custom_field_types import IssueCustomFieldTypes, ProjectCustomFieldTypes
from ..exceptions import CustomFieldUnresolvedReason
from .base import BaseService
from .field_cache import get_field_cache

# The arity a field type id ends in: `enum[1]` and `user[1]` hold one value, `version[*]`
# holds several. It is the same fact as `fieldType.isMultiValue`, spelled in the id, and it
# answers in both directions -- so a response that carries the id without the boolean is
# still a complete answer about the value's shape.
_FIELD_TYPE_ARITY_SUFFIX = re.compile(r"\[(\*|\d+)\]$")


def _split_selector_arguments(arguments: str) -> list[str]:
    """Split a selector's argument list on the commas that are not inside parentheses.

    Parentheses are the only nesting this needs to understand: YouTrack's ``fields``
    syntax nests projections that way (``field(fieldType(id,name),name)``) and has no
    bracketed form, so treating ``[`` as nesting too would be a rule about a syntax that
    does not exist -- and one no selector here could exercise.
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in arguments:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts]


def _selector_names_a_field(selector: str) -> bool:
    """Whether a ``fields=`` selector already asks for a field's own name.

    Only a *top-level* ``name`` argument of a ``field(...)`` clause counts. A ``name``
    nested inside that clause belongs to something else -- ``field(fieldType(id,name))``
    asks for the field *type's* name, not the field's -- and reading it as satisfied
    suppresses the ``field(name)`` that the display path then needs, which renders every
    name as ``N/A``. A substring test cannot tell the two apart, because
    ``field(fieldType(name),name)`` contains ``name`` at both depths.
    """
    index = 0
    while (open_paren := selector.find("field(", index)) != -1:
        cursor = open_paren + len("field(")
        depth = 1
        while cursor < len(selector) and depth:
            if selector[cursor] == "(":
                depth += 1
            elif selector[cursor] == ")":
                depth -= 1
            cursor += 1
        if "name" in _split_selector_arguments(selector[open_paren + len("field(") : cursor - 1]):
            return True
        # Resume *inside* this clause rather than past it, so a `field(name)` nested in it
        # is examined on the next pass. `index` still advances by at least the width of the
        # token it just consumed, so this terminates.
        index = open_paren + len("field(")
    return False


# Bundle-backed project kinds mapped to (single-valued, multi-valued) issue types. A kind
# whose values live in a bundle -- enum, owned, user, version, build -- can hold one value
# or several, and the project `$type` says only which kind it is. The multiplicity belongs
# to the attached field type (`fieldType.isMultiValue`), so the pair is resolved against
# that rather than against the kind. Built once: the constants are import-time, and a
# function here would rebuild the same dict for every field discovered.
_BUNDLE_ISSUE_FIELD_TYPES = {
    ProjectCustomFieldTypes.ENUM: (IssueCustomFieldTypes.SINGLE_ENUM, IssueCustomFieldTypes.MULTI_ENUM),
    ProjectCustomFieldTypes.OWNED: (IssueCustomFieldTypes.SINGLE_OWNED, IssueCustomFieldTypes.MULTI_OWNED),
    ProjectCustomFieldTypes.USER: (IssueCustomFieldTypes.SINGLE_USER, IssueCustomFieldTypes.MULTI_USER),
    ProjectCustomFieldTypes.VERSION: (IssueCustomFieldTypes.SINGLE_VERSION, IssueCustomFieldTypes.MULTI_VERSION),
    ProjectCustomFieldTypes.BUILD: (IssueCustomFieldTypes.SINGLE_BUILD, IssueCustomFieldTypes.MULTI_BUILD),
}


class ProjectService(BaseService):
    """Service for YouTrack project API operations.

    Handles all HTTP communication with YouTrack's projects API endpoints.
    Pure API service with no business logic or presentation concerns.
    """

    async def list_projects(
        self,
        fields: str | None = None,
        top: int | None = None,
        skip: int | None = None,
        show_archived: bool = False,
    ) -> dict[str, Any]:
        """List all projects via API.

        Args:
            fields: Comma-separated list of project fields to return
            top: Maximum number of projects to return
            skip: Number of projects to skip
            show_archived: Whether to include archived projects

        Returns:
            API response with project list
        """
        try:
            params = {}

            if fields:
                params["fields"] = fields
            else:
                params["fields"] = (
                    "id,name,shortName,description,leader(login,fullName),archived,createdBy(login,fullName)"
                )

            if top is not None:
                params["$top"] = str(top)
            if skip is not None:
                params["$skip"] = str(skip)

            response = await self._make_request("GET", "admin/projects", params=params)
            result = await self._handle_response(response)

            # Filter archived projects if requested
            if result["status"] == "success" and not show_archived:
                projects = result["data"]
                if isinstance(projects, list):
                    filtered_projects = [p for p in projects if p is not None and not p.get("archived", False)]
                    result["data"] = filtered_projects

            return result

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error listing projects: {str(e)}")

    async def get_project(self, project_id: str, fields: str | None = None) -> dict[str, Any]:
        """Get a specific project via API.

        Args:
            project_id: Project ID or short name
            fields: Comma-separated list of fields to return

        Returns:
            API response with project data
        """
        try:
            params = {}

            if fields:
                params["fields"] = fields
            else:
                params["fields"] = (
                    "id,name,shortName,description,leader(login,fullName),"
                    "archived,createdBy(login,fullName),team(users(login,fullName))"
                )

            response = await self._make_request("GET", f"admin/projects/{project_id}", params=params)
            return await self._handle_response(response)

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error getting project: {str(e)}")

    async def create_project(
        self,
        short_name: str,
        name: str,
        description: str | None = None,
        leader_login: str | None = None,
    ) -> dict[str, Any]:
        """Create a new project via API.

        Args:
            short_name: Project short name (ID)
            name: Project full name
            description: Project description
            leader_login: Project leader user ID (resolved from username by manager)

        Returns:
            API response with created project data
        """
        try:
            project_data = {
                "shortName": short_name,
                "name": name,
            }

            if description:
                project_data["description"] = description
            if leader_login:
                # Use user ID instead of login for reliable API resolution
                project_data["leader"] = {"id": leader_login}

            response = await self._make_request("POST", "admin/projects", json_data=project_data)
            return await self._handle_response(response, success_codes=[200, 201])

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error creating project: {str(e)}")

    async def update_project(
        self,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        leader_login: str | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        """Update an existing project via API.

        Args:
            project_id: Project ID to update
            name: New project name
            description: New project description
            leader_login: New project leader user ID (resolved from username by manager)
            archived: Archive status

        Returns:
            API response
        """
        try:
            update_data: dict[str, Any] = {}

            if name is not None:
                update_data["name"] = name
            if description is not None:
                update_data["description"] = description
            if leader_login is not None:
                # Use user ID instead of login for reliable API resolution
                update_data["leader"] = {"id": leader_login}
            if archived is not None:
                update_data["archived"] = archived

            response = await self._make_request("POST", f"admin/projects/{project_id}", json_data=update_data)
            return await self._handle_response(response)

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error updating project: {str(e)}")

    async def delete_project(self, project_id: str) -> dict[str, Any]:
        """Delete a project via API.

        Args:
            project_id: Project ID to delete

        Returns:
            API response
        """
        try:
            response = await self._make_request("DELETE", f"admin/projects/{project_id}")
            return await self._handle_response(response)

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error deleting project: {str(e)}")

    async def archive_project(self, project_id: str) -> dict[str, Any]:
        """Archive a project via API.

        Args:
            project_id: Project ID to archive

        Returns:
            API response
        """
        try:
            update_data = {"archived": True}
            response = await self._make_request("POST", f"admin/projects/{project_id}", json_data=update_data)
            return await self._handle_response(response)

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error archiving project: {str(e)}")

    async def unarchive_project(self, project_id: str) -> dict[str, Any]:
        """Unarchive a project via API.

        Args:
            project_id: Project ID to unarchive

        Returns:
            API response
        """
        try:
            update_data = {"archived": False}
            response = await self._make_request("POST", f"admin/projects/{project_id}", json_data=update_data)
            return await self._handle_response(response)

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error unarchiving project: {str(e)}")

    async def get_project_team(self, project_id: str, fields: str | None = None) -> dict[str, Any]:
        """Get project team members via API.

        Args:
            project_id: Project ID
            fields: Comma-separated list of user fields to return

        Returns:
            API response with team member list
        """
        try:
            params = {}
            if fields:
                params["fields"] = fields
            else:
                params["fields"] = "login,fullName,email,avatarUrl"

            response = await self._make_request("GET", f"admin/projects/{project_id}/team", params=params)
            return await self._handle_response(response)

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error getting project team: {str(e)}")

    async def add_team_member(self, project_id: str, user_login: str) -> dict[str, Any]:
        """Add a user to project team via API.

        Args:
            project_id: Project ID
            user_login: User login to add

        Returns:
            API response
        """
        try:
            user_data = {"login": user_login}
            response = await self._make_request("POST", f"admin/projects/{project_id}/team", json_data=user_data)
            return await self._handle_response(response, success_codes=[200, 201])

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error adding team member: {str(e)}")

    async def remove_team_member(self, project_id: str, user_login: str) -> dict[str, Any]:
        """Remove a user from project team via API.

        Args:
            project_id: Project ID
            user_login: User login to remove

        Returns:
            API response
        """
        try:
            response = await self._make_request("DELETE", f"admin/projects/{project_id}/team/{user_login}")
            return await self._handle_response(response)

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error removing team member: {str(e)}")

    async def get_project_custom_fields(self, project_id: str, fields: str | None = None) -> dict[str, Any]:
        """Get project custom fields via API.

        Args:
            project_id: Project ID
            fields: Comma-separated list of field properties to return

        Returns:
            API response with custom field list
        """
        try:
            params = {}
            if fields:
                # Always include field(name) for table display when custom fields are specified
                # This ensures the name is available even when users specify their own fields
                fields_list = [f.strip() for f in fields.split(",")]

                # Check if field(name) is already included in some form. Asked of the whole
                # selector and answered by `_selector_names_a_field`, which reads each
                # `field(...)` clause's own top-level arguments and looks inside a clause
                # for a nested `field(name)`. Not per comma-separated fragment: a
                # `field(...)` clause routinely contains commas of its own, so
                # `field(fieldType(id,name,isMultiValue),name)` is one fragment that names a
                # field, and a fragment test reads it as "no field(name) here".
                has_field_name = _selector_names_a_field(fields)

                if not has_field_name:
                    # Add field(name) to ensure name is always available for display
                    fields_list.append("field(name)")

                params["fields"] = ",".join(fields_list)
            else:
                params["fields"] = "id,field(name,fieldType),canBeEmpty,isPublic,ordinal"

            response = await self._make_request("GET", f"admin/projects/{project_id}/customFields", params=params)
            return await self._handle_response(response)

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error getting project custom fields: {str(e)}")

    async def attach_custom_field(
        self, project_id: str, field_id: str, is_public: bool | None = None
    ) -> dict[str, Any]:
        """Attach a custom field to a project via API.

        Args:
            project_id: Project ID
            field_id: Custom field ID
            is_public: Whether field should be public

        Returns:
            API response
        """
        try:
            field_data: dict[str, Any] = {"field": {"id": field_id}}

            if is_public is not None:
                field_data["isPublic"] = is_public

            response = await self._make_request(
                "POST", f"admin/projects/{project_id}/customFields", json_data=field_data
            )
            return await self._handle_response(response, success_codes=[200, 201])

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error attaching custom field: {str(e)}")

    async def detach_custom_field(self, project_id: str, field_id: str) -> dict[str, Any]:
        """Detach a custom field from a project via API.

        Args:
            project_id: Project ID
            field_id: Custom field ID to detach

        Returns:
            API response
        """
        try:
            response = await self._make_request("DELETE", f"admin/projects/{project_id}/customFields/{field_id}")
            return await self._handle_response(response)

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error detaching custom field: {str(e)}")

    async def get_project_versions(self, project_id: str, fields: str | None = None) -> dict[str, Any]:
        """Get project versions via API.

        Args:
            project_id: Project ID
            fields: Comma-separated list of version fields to return

        Returns:
            API response with version list
        """
        try:
            params = {}
            if fields:
                params["fields"] = fields
            else:
                params["fields"] = "id,name,description,archived,released,releaseDate"

            response = await self._make_request("GET", f"admin/projects/{project_id}/versions", params=params)
            return await self._handle_response(response)

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error getting project versions: {str(e)}")

    async def create_project_version(
        self,
        project_id: str,
        name: str,
        description: str | None = None,
        released: bool | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        """Create a project version via API.

        Args:
            project_id: Project ID
            name: Version name
            description: Version description
            released: Whether version is released
            archived: Whether version is archived

        Returns:
            API response with created version data
        """
        try:
            version_data: dict[str, Any] = {"name": name}

            if description is not None:
                version_data["description"] = description
            if released is not None:
                version_data["released"] = released
            if archived is not None:
                version_data["archived"] = archived

            response = await self._make_request("POST", f"admin/projects/{project_id}/versions", json_data=version_data)
            return await self._handle_response(response, success_codes=[200, 201])

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error creating project version: {str(e)}")

    async def get_custom_field_details(
        self, project_id: str, field_id: str, include_bundle: bool = True
    ) -> dict[str, Any]:
        """Get detailed custom field information including bundle data.

        Args:
            project_id: Project ID
            field_id: Custom field ID
            include_bundle: Whether to include bundle values

        Returns:
            API response with detailed field information
        """
        try:
            # First get the field details. `isMultiValue` and the field type's `id` are
            # both asked for, on this read and on the list read: the attached field type
            # is where multiplicity lives, `id` spells it as an arity suffix, and neither
            # is returned unless the selector names it. A payload's value shape cannot
            # be built without them, and a selector that omits one is a silent refusal.
            field_response = await self._make_request(
                "GET",
                f"admin/projects/{project_id}/customFields/{field_id}",
                params={
                    "fields": (
                        "id,name,fieldType,localizedName,isPublic,ordinal,field(fieldType(id,name,isMultiValue),name)"
                    )
                },
            )
            field_result = await self._handle_response(field_response)

            if field_result["status"] != "success" or not include_bundle:
                return field_result

            # Try to get bundle information if available
            try:
                bundle_response = await self._make_request(
                    "GET",
                    f"admin/projects/{project_id}/customFields/{field_id}/bundle",
                    params={"fields": "id,values(id,name,description,$type)"},
                )
                bundle_result = await self._handle_response(bundle_response)

                if bundle_result["status"] == "success":
                    field_result["data"]["bundle"] = bundle_result["data"]
            except Exception:
                # Bundle might not exist for all field types, that's ok
                pass

            return field_result

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error getting custom field details: {str(e)}")

    async def discover_state_field(self, project_id: str) -> dict[str, Any]:
        """Discover the state field for a project by checking common field names.

        Args:
            project_id: Project ID

        Returns:
            Dict containing field discovery results with field name, type, and bundle info
        """
        try:
            # Check cache first
            cache = get_field_cache()
            cached_result = cache.get(project_id, "state")
            if cached_result is not None:
                return {"status": "success", "data": cached_result}
            # Get all custom fields for the project
            fields_response = await self.get_project_custom_fields(
                project_id,
                fields="id,name,fieldType,localizedName,isPublic,ordinal,field(fieldType(id,name,isMultiValue),name)",
            )

            if fields_response["status"] != "success":
                return fields_response

            custom_fields = fields_response["data"]
            if not isinstance(custom_fields, list):
                return self._create_error_response("Invalid custom fields response format")

            # Common state field names in order of priority
            state_field_names = [
                "State",
                "Status",
                "Kanban State",
                "Workflow State",
                "Stage",
                "Issue State",
                "Current State",
                "Work State",
            ]

            discovered_field = None
            for field_name in state_field_names:
                for field in custom_fields:
                    # Field name is in field.name, not directly in name
                    actual_field_name = field.get("field", {}).get("name", "")
                    if actual_field_name.lower() == field_name.lower():
                        discovered_field = field
                        break
                if discovered_field:
                    break

            if not discovered_field:
                # Look for any field containing "state" in the name
                for field in custom_fields:
                    actual_field_name = field.get("field", {}).get("name", "").lower()
                    if "state" in actual_field_name or "status" in actual_field_name:
                        discovered_field = field
                        break

            if not discovered_field:
                return {
                    "status": "error",
                    "message": "No state field found in project",
                    "available_fields": [f.get("field", {}).get("name", "") for f in custom_fields],
                }

            # Get detailed information about the discovered field
            field_details = await self.get_custom_field_details(project_id, discovered_field["id"], include_bundle=True)

            if field_details["status"] != "success":
                return field_details

            # Extract bundle type information for proper API formatting
            bundle_type = "EnumBundleElement"  # Default fallback
            field_data = field_details["data"]

            # Try to determine the bundle type from the field information
            if "bundle" in field_data and "values" in field_data["bundle"]:
                bundle_values = field_data["bundle"]["values"]
                if isinstance(bundle_values, list) and len(bundle_values) > 0:
                    first_value = bundle_values[0]
                    if "$type" in first_value:
                        bundle_type = first_value["$type"]

            # Alternative: Check field type information
            if "field" in field_data and "fieldType" in field_data["field"]:
                field_type = field_data["field"]["fieldType"]
                # field_type is a dict like {'$type': 'FieldType'}, get the $type value
                if isinstance(field_type, dict) and "$type" in field_type:
                    field_type_name = field_type["$type"]
                    if isinstance(field_type_name, str) and "state" in field_type_name.lower():
                        bundle_type = "StateBundleElement"

            result_data = {
                "field_name": discovered_field.get("field", {}).get("name", ""),
                "field_id": discovered_field["id"],
                "bundle_type": bundle_type,
                "field_details": field_data,
            }

            # Cache the result for future use
            cache.set(project_id, result_data, "state")

            return {"status": "success", "data": result_data}

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error discovering state field: {str(e)}")

    async def discover_custom_field(self, project_id: str, field_name: str) -> dict[str, Any]:
        """Discover custom field type information for a specific field.

        Args:
            project_id: Project ID or short name
            field_name: Name of the custom field to discover

        Returns:
            Dict with field information including type, bundle info, etc.
        """
        try:
            # Check cache first
            cache = get_field_cache()
            cache_key = f"custom_field:{field_name}"
            cached_result = cache.get(project_id, cache_key)
            if cached_result is not None:
                return {"status": "success", "data": cached_result}

            # Get all custom fields for the project
            fields_response = await self.get_project_custom_fields(
                project_id,
                fields=(
                    "id,name,fieldType,localizedName,isPublic,ordinal,"
                    # `isMultiValue` is requested here as well as on the detail read: the
                    # single/multi decision is the whole point of the mapping, and a field
                    # whose list entry omits it is indistinguishable from a single-valued
                    # one if the mapping ever has to fall back to the list.
                    "field(fieldType(id,name,$type,isMultiValue),name,$type)"
                ),
            )

            if fields_response["status"] != "success":
                return fields_response

            custom_fields = fields_response["data"]
            if not isinstance(custom_fields, list):
                return self._create_error_response("Invalid custom fields response format")

            # Find the field by name (case-insensitive)
            discovered_field = None
            for field in custom_fields:
                actual_field_name = field.get("field", {}).get("name", "")
                if actual_field_name.lower() == field_name.lower():
                    discovered_field = field
                    break

            if not discovered_field:
                return {
                    "status": "error",
                    "message": f"Custom field '{field_name}' not found in project '{project_id}'",
                    "available_fields": [
                        f.get("field", {}).get("name", "") for f in custom_fields if f.get("field", {}).get("name")
                    ],
                }

            # Get detailed information about the field
            field_details = await self.get_custom_field_details(project_id, discovered_field["id"], include_bundle=True)

            if field_details["status"] != "success":
                return field_details

            field_data = field_details["data"]

            # The project API names the kind of field and reports multiplicity separately, on
            # the attached field type. Both are needed, and neither can be inferred from the
            # other: `VersionProjectCustomField` backs a single-valued version field in one
            # project and a multi-valued one in another.
            project_field_type = field_data.get("$type", "")
            is_multi_value = self._is_multi_value(field_data, discovered_field)
            issue_field_type = self._project_to_issue_field_type(project_field_type, is_multi_value)

            # Why the issue type could not be resolved, when it could not be. The two causes
            # are reported apart because they are not the same problem: an unrecognised kind
            # is a CLI limitation, whereas an unreported multiplicity is a gap in the server's
            # response for a kind this CLI handles. Naming the wrong one sends the reader
            # looking in the wrong place.
            unresolved_reason = None
            if issue_field_type is None:
                unresolved_reason = (
                    CustomFieldUnresolvedReason.MULTIPLICITY
                    if is_multi_value is None and project_field_type in _BUNDLE_ISSUE_FIELD_TYPES
                    else CustomFieldUnresolvedReason.TYPE
                )

            # Determine bundle element type if applicable
            bundle_element_type = None
            if "bundle" in field_data and "values" in field_data["bundle"]:
                bundle_values = field_data["bundle"]["values"]
                if isinstance(bundle_values, list) and len(bundle_values) > 0:
                    bundle_element_type = bundle_values[0].get("$type")

            result_data = {
                "field_name": field_name,
                "field_id": discovered_field["id"],
                "project_field_type": project_field_type,
                "issue_field_type": issue_field_type,
                "bundle_element_type": bundle_element_type,
                "is_multi_value": is_multi_value,
                "unresolved_reason": unresolved_reason,
                "field_details": field_data,
            }

            # Cache the result
            cache.set(project_id, result_data, cache_key)

            return {"status": "success", "data": result_data}

        except ValueError as e:
            return self._create_error_response(str(e))
        except Exception as e:
            return self._create_error_response(f"Error discovering custom field '{field_name}': {str(e)}")

    def _is_multi_value(self, field_data: dict[str, Any], listed_field: dict[str, Any]) -> bool | None:
        """Whether a field holds one value or several, as the server reports it.

        Returns None when the server does not say, which is not the same as False: the
        value shape follows from this answer, so "unknown" has to stay distinguishable
        from "one value" or it becomes a guess (see ``CustomFieldMultiplicityUnknownError``).

        Two independent signals are consulted, and the boolean is preferred over the arity
        because it is the direct one: ``isMultiValue`` *is* the field's multiplicity,
        while ``id`` merely spells it. Within a signal the detail read is preferred over the
        list read, because it is the field being written. ``fieldType.id`` spells the same
        fact as its arity suffix -- ``enum[1]`` and ``user[1]`` hold one value,
        ``version[*]`` holds several -- and it answers in *both* directions, so a response
        carrying the id but not the boolean is still answerable rather than refusable. Both
        live on the attached field type (``field.fieldType``) and both are named in the
        selectors this module sends; neither is returned otherwise. None means neither was
        present.
        """
        for source in (field_data, listed_field):
            reported = (source.get("field") or {}).get("fieldType") or {}
            if reported.get("isMultiValue") is not None:
                return bool(reported["isMultiValue"])
        for source in (field_data, listed_field):
            field_type_id = ((source.get("field") or {}).get("fieldType") or {}).get("id")
            if isinstance(field_type_id, str):
                arity = _FIELD_TYPE_ARITY_SUFFIX.search(field_type_id)
                if arity:
                    return arity.group(1) == "*"
        return None

    def _project_to_issue_field_type(self, project_field_type: str, is_multi_value: bool | None) -> str | None:
        """Convert project field type to issue field type.

        Args:
            project_field_type: The project field type string
            is_multi_value: Whether the field holds several values, as the server reports
                it, or None when the server did not say. Deliberately has no default: a
                default of False would make "not asked" indistinguishable from "holds one
                value" for any caller that forgot the argument, which is the conflation
                this method exists to keep apart.

        Returns:
            The corresponding issue field type string, or None when the project type
            is not one this CLI knows how to write. Callers must treat None as
            "cannot type this field" rather than substituting a default: a wrong
            guess is rejected by the server as a type error, which is far harder to
            diagnose than an explicit refusal here.
        """
        # The project `$type` names the *kind* of field and carries no multiplicity, so a
        # bundle-backed kind maps to a (single, multi) pair chosen by what the field itself
        # reports. The two vocabularies are not parallel: a version field is
        # "VersionProjectCustomField" on the project side, and the issue side spells it
        # either way depending on the field — the same kind is single-valued in one project
        # and multi-valued in another, so nothing here can decide it.
        bundle_kinds = _BUNDLE_ISSUE_FIELD_TYPES
        if project_field_type in bundle_kinds:
            # Unreported multiplicity leaves the issue type genuinely undecidable, so the
            # refusal happens here rather than as a wrong single/multi pick downstream.
            if is_multi_value is None:
                return None
            single, multi = bundle_kinds[project_field_type]
            return multi if is_multi_value else single

        # Kinds that are always single-valued, or that have no single/multi distinction.
        mapping = {
            ProjectCustomFieldTypes.STATE: IssueCustomFieldTypes.STATE,
            ProjectCustomFieldTypes.TEXT: IssueCustomFieldTypes.TEXT,
            ProjectCustomFieldTypes.INTEGER: IssueCustomFieldTypes.INTEGER,
        }
        return mapping.get(project_field_type)
