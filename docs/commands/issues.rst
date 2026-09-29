Issues Command Group
====================

The ``yt issues`` command group provides comprehensive issue management capabilities for YouTrack. This is the core functionality for creating, updating, searching, and managing issues in your YouTrack projects.

.. contents:: Table of Contents
   :local:
   :depth: 2

Overview
--------

The issues command group offers complete issue lifecycle management including:

* Creating and updating issues with all custom fields
* Batch operations for creating and updating multiple issues from files
* Advanced searching and filtering with YouTrack query language
* Managing issue comments and attachments
* Handling issue relationships and links
* Assigning issues and managing workflow states
* Managing issue tags and project transitions

Base Command
------------

.. code-block:: bash

   yt issues [OPTIONS] COMMAND [ARGS]...

Issue Management Commands
-------------------------

Create Issues
~~~~~~~~~~~~~

Create new issues in YouTrack projects.

.. code-block:: bash

   yt issues create PROJECT_ID SUMMARY [OPTIONS]

**Arguments:**
  * ``PROJECT_ID`` - The ID of the project to create the issue in
  * ``SUMMARY`` - Brief description of the issue

**Options:**
  * ``-d, --description TEXT`` - Detailed issue description
  * ``-t, --type TEXT`` - Issue type (e.g., Bug, Feature, Task)
  * ``-p, --priority TEXT`` - Issue priority (e.g., Critical, High, Medium, Low)
  * ``-a, --assignee TEXT`` - Username of the assignee
  * ``-cf, --custom-field TEXT`` - Custom field in format "FieldName=value" (repeatable)
  * ``--tag TEXT`` - Tag name to apply (repeatable). The tag must already exist.

**Tags**

``--tag`` applies tags to the new issue in the same command. Tags live on a separate resource,
so they are applied immediately after the issue is created; if one cannot be applied, the
warning names both the issue and the tag, because the issue exists either way. A tag that does
not exist is refused **by name** rather than skipped — create it first with ``yt tags create``.

.. code-block:: bash

   yt issues create PROJ-1 "New task" -cf "State=Submitted" --tag lane-root --tag fleet

**Custom Fields**

The ``--custom-field`` option supports all YouTrack custom field types:

* **Enum fields**: Single and multi-value enum fields (e.g., Priority, Status)
* **Text fields**: Free-form text fields
* **Simple fields**: Integer and float numeric fields
* **User fields**: Single and multi-user fields (use login names)
* **Version fields**: Version bundle fields
* **Build fields**: Build bundle fields
* **Date/DateTime fields**: Date and date-time fields (use Unix timestamps in milliseconds)
* **Period fields**: Time period fields

The CLI automatically detects the field type from the project configuration. If type discovery fails, it falls back to enum type as a safe default.

**Examples:**

.. code-block:: bash

   yt issues create PROJ-1 "Fix login bug" -d "Users cannot login with special characters" -t Bug -p High -a john.doe

   # Using custom fields
   yt issues create PROJ-1 "New task" -cf "Team=Backend" -cf "Sprint=Sprint 1"

   # Text field
   yt issues create PROJ-1 "Task" -cf "Notes=Some implementation notes"

   # Integer field
   yt issues create PROJ-1 "Task" -cf "StoryPoints=5"

   # User field (use login name)
   yt issues create PROJ-1 "Task" -cf "Reviewer=john.doe"

   # Creating and tagging in one command
   yt issues create PROJ-1 "New task" -cf "State=Submitted" --tag lane-root

**Output**

A successful create reports the issue's readable id (``PROJ-1``), not its internal id
(``3-42``) — the two are different things and only the first is stable across projects. The id is
resolved with a follow-up read after the create, so when that read fails the internal id is
reported instead rather than nothing:

.. code-block:: text

   Success: Issue PROJ-1 created successfully
   Issue ID: PROJ-1
   Tagged: lane-root

List Issues
~~~~~~~~~~~

List and filter issues with advanced options.

.. code-block:: bash

   yt issues list [OPTIONS]

**Options:**
  * ``-p, --project-id TEXT`` - Filter by project ID
  * ``-s, --state TEXT`` - Filter by issue state
  * ``-a, --assignee TEXT`` - Filter by assignee
  * ``-f, --fields TEXT`` - Comma-separated list of fields to return
  * ``--profile [minimal|standard|full]`` - Field selection profile (default: standard)
  * ``-t, --top INTEGER`` - Maximum number of issues to return (legacy, use ``--page-size``)
  * ``--page-size INTEGER`` - Number of issues per page (default: 100)
  * ``--max-results INTEGER`` - Maximum total number of results to fetch
  * ``--after-cursor TEXT`` - Start listing after this cursor position
  * ``--before-cursor TEXT`` - Start listing before this cursor position
  * ``--all`` - Fetch all results automatically (respects max-results limit)
  * ``--paginated`` - Display results with interactive pagination
  * ``--display-page-size INTEGER`` - Items per page for interactive display (default: 50)
  * ``--show-all`` - Show all results without interactive pagination
  * ``--start-page INTEGER`` - Page number to start displaying from
  * ``-q, --query TEXT`` - Advanced query filter using YouTrack syntax
  * ``--format [table|json]`` - Output format (default: table)

.. note::
   The assignee column in table output displays both the user's full name and username
   in the format "Full Name (username)" when both are available. This helps with user
   identification when multiple users may share similar names.

**Examples:**

.. code-block:: bash

   # List all issues in a project with interactive pagination
   yt issues list -p PROJ-1 --paginated

   # List high priority bugs assigned to a user
   yt issues list -p PROJ-1 -a john.doe --query "priority:High type:Bug"

   # List issues in JSON format with cursor pagination
   yt issues list --format json --max-results 50

   # Limit the number of issues returned
   yt issues list -p PROJ-1 --page-size 100

   # Navigate through pages using cursors
   yt issues list -p PROJ-1 --after-cursor "cursor_token_here"

   # Fetch all issues automatically (up to 10,000)
   yt issues list -p PROJ-1 --all

Update Issues
~~~~~~~~~~~~~

Update existing issues with new field values.

.. code-block:: bash

   yt issues update ISSUE_ID [OPTIONS]

**Arguments:**
  * ``ISSUE_ID`` - The ID of the issue to update

**Options:**
  * ``-s, --summary TEXT`` - New issue summary
  * ``-d, --description TEXT`` - New issue description
  * ``--state TEXT`` - New issue state
  * ``-p, --priority TEXT`` - New issue priority
  * ``-a, --assignee TEXT`` - New assignee username
  * ``-t, --type TEXT`` - New issue type
  * ``-cf, --custom-field TEXT`` - Custom field in format "FieldName=value" (repeatable)
  * ``--show-details`` - Show current issue details instead of updating

**Custom Fields**

The ``--custom-field`` option is repeatable and supports all YouTrack custom field types, consistent with the create command. See the Create Issues section for field type details.

**Examples:**

.. code-block:: bash

   # Update issue priority and assignee
   yt issues update PROJ-123 -p Critical -a jane.smith

   # Update with custom fields
   yt issues update PROJ-123 -cf "Team=Frontend" -cf "StoryPoints=8"

   # View current issue details
   yt issues update PROJ-123 --show-details

Delete Issues
~~~~~~~~~~~~~

Delete issues from YouTrack.

.. code-block:: bash

   yt issues delete ISSUE_ID [OPTIONS]

**Arguments:**
  * ``ISSUE_ID`` - The ID of the issue to delete

**Options:**
  * ``--force`` - Skip confirmation prompt

**Examples:**

.. code-block:: bash

   # Interactive deletion (will prompt for confirmation)
   yt issues delete PROJ-123

   # Non-interactive deletion for automation
   yt issues delete PROJ-123 --force

.. note::
   Use the ``--force`` flag for automation scripts and CI/CD pipelines to skip
   the interactive confirmation prompt.

Search Issues
~~~~~~~~~~~~~

Advanced issue search with YouTrack query language.

.. code-block:: bash

   yt issues search QUERY [OPTIONS]

**Arguments:**
  * ``QUERY`` - Search query using YouTrack syntax

**Options:**
  * ``-p, --project-id TEXT`` - Filter by project ID
  * ``-t, --top INTEGER`` - Maximum number of results (legacy, use ``--page-size``)
  * ``--page-size INTEGER`` - Number of results per page (default: 100)
  * ``--max-results INTEGER`` - Maximum total number of results to fetch
  * ``--after-cursor TEXT`` - Start searching after this cursor position
  * ``--before-cursor TEXT`` - Start searching before this cursor position
  * ``--all`` - Fetch all results automatically (respects max-results limit)
  * ``-f, --fields TEXT`` - Comma-separated list of fields to return
  * ``--profile [minimal|standard|full]`` - Field selection profile (default: standard)
  * ``--format [table|json]`` - Output format

**Examples:**

.. code-block:: bash

   # Search for bugs with specific text
   yt issues search "login error" -p PROJ-1

   # Complex query with multiple conditions and pagination
   yt issues search "priority:Critical state:Open assignee:me" --paginated

   # Search with cursor navigation
   yt issues search "bug" --after-cursor "search_cursor_token"

   # Get all search results automatically
   yt issues search "type:Bug state:Open" --all

Assign Issues
~~~~~~~~~~~~~

Assign issues to users.

.. code-block:: bash

   yt issues assign ISSUE_ID ASSIGNEE

**Arguments:**
  * ``ISSUE_ID`` - The ID of the issue
  * ``ASSIGNEE`` - Username of the new assignee

**Example:**

.. code-block:: bash

   yt issues assign PROJ-123 john.doe

Move Issues
~~~~~~~~~~~

Move issues between states within the same project, or transfer issues to different projects entirely.

.. code-block:: bash

   yt issues move ISSUE_ID [OPTIONS]

**Arguments:**
  * ``ISSUE_ID`` - The ID of the issue to move

**Options:**
  * ``-s, --state TEXT`` - New state for the issue
  * ``-p, --project-id TEXT`` - Move to different project (short name or ID)

**State Moves (Within Project):**

.. code-block:: bash

   # Move issue to different state
   yt issues move PROJ-123 -s "In Progress"
   yt issues move PROJ-123 --state "Done"

**Project Moves (Between Projects):**

.. code-block:: bash

   # Move issue to different project
   yt issues move PROJ-123 -p WEB
   yt issues move DEMO-456 --project-id TEST

**Advanced Examples:**

.. code-block:: bash

   # Check available projects first
   yt projects list

   # Move issue with validation
   yt issues show PROJ-123  # Verify source issue
   yt issues move PROJ-123 -p TARGET-PROJ
   yt issues list -p TARGET-PROJ  # Verify move

.. warning::
   **Project Move Considerations:**

   * Ensure you have appropriate permissions in both source and target projects
   * Custom fields that exist in the source project but not in the target may be lost
   * Issue numbering will change to match the target project's scheme
   * All issue data (description, comments, attachments) will be preserved
   * Verify the move completed successfully by checking the target project

.. note::
   **State Changes:**

   State changes use YouTrack's custom field format to ensure reliable transitions.
   The CLI will report success only when the state change is actually applied.
   Use exact state names as they appear in your YouTrack workflow.

Tag Management
~~~~~~~~~~~~~~

Manage issue tags.

**Add Tags:**

.. code-block:: bash

   yt issues tag add ISSUE_ID TAG_NAME [--create-if-missing]

Use ``--create-if-missing`` to create the tag automatically if it does not already exist.

**Remove Tags:**

.. code-block:: bash

   yt issues tag remove ISSUE_ID TAG_NAME

**List Tags:**

.. code-block:: bash

   yt issues tag list ISSUE_ID

**Examples:**

.. code-block:: bash

   # Add a tag
   yt issues tag add PROJ-123 urgent

   # Remove a tag
   yt issues tag remove PROJ-123 outdated

   # List all tags on an issue
   yt issues tag list PROJ-123

Benchmark Performance
~~~~~~~~~~~~~~~~~~~~~

Benchmark field selection performance improvements to measure API optimization benefits.

.. code-block:: bash

   yt issues benchmark [OPTIONS]

**Options:**
  * ``-p, --project-id TEXT`` - Project ID to benchmark with
  * ``--sample-size INTEGER`` - Number of issues to fetch for benchmarking (default: 50)

**Examples:**

.. code-block:: bash

   # Run benchmark with default settings
   yt issues benchmark

   # Benchmark specific project with custom sample size
   yt issues benchmark -p FPU --sample-size 100

   # Benchmark with minimal sample for quick testing
   yt issues benchmark --sample-size 10

.. note::
   This command runs performance tests comparing minimal, standard, and full
   field selection profiles to demonstrate the optimization benefits. It helps
   understand the performance impact of different field selection strategies
   when working with large datasets.

Reading Issues Reliably
~~~~~~~~~~~~~~~~~~~~~~~

Two things can make a read look complete when it is not. Both are reported rather
than passed off as an answer.

A field name YouTrack does not know
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The API treats an unknown field name as *absent* rather than as an error: the
request succeeds, the unknown term is simply left out of the response, and the
exit status is 0. So a single mistyped character produces a short payload that
looks like a successful read::

   $ yt issues list -p PROJ --format json --fields 'idReadble,summary'
   ❌ The API did not return these fields you asked for: idReadble
      The request succeeded — YouTrack drops an unknown field name instead of
      failing it — so the result would have been silently incomplete.
      Check the spelling, or run `yt projects fields <PROJECT>` to see a field's
      real name.
   $ echo $?
   1

A requested name is reported only when the response gives **positive evidence**
against it, from one of two signals:

* **Nothing requested came back at all.** A request whose every name is absent is
  not a request that happened to be empty; the whole expression is wrong.
* **It is a near-miss for a name that did come back** — within two characters.
  ``idReadble`` beside a returned ``idReadable`` is a typo whatever the schema
  says, so it is reported without needing to know what the entity has::

     $ yt issues list -p PROJ --format json --fields 'idReadble,idReadable,summary'
     ❌ You asked for idReadble and the API returned no such field.
        The request succeeded — YouTrack drops a field name it does not recognise
        instead of failing it — so the result would have been silently incomplete.
        These are misspelled or are not fields of this entity. A name that is merely
        *empty* is not reported, because an absent value and an unknown name look
        identical in a response.

**What this does not catch, and why.** A misspelled name whose correct spelling
was *not* also requested has no neighbour in the response to be compared against:
``--fields 'idReadble,summary'`` returns a payload with no issue id in it, and the
check stays silent. There is no way round that without a list of valid field names,
and a hand-maintained list is a copy that goes stale — an earlier version of this
check used one, and it failed in the opposite direction, accepting names the server
rejects. A copy of the schema is a second thing to keep correct, and a false
refusal breaks a command that was working.

So **check the keys you asked for are in the first record** rather than relying on
this to have caught it. The check earns its keep on the two cases above, not as a
general schema validator.

Nested subfields are never reported, and that is a hard limit. The API answers by
returning *only what it was asked for*, so a nested subfield that does not apply
to a field's type is byte-for-byte identical to one that was misspelled: a text
custom field asked for ``value(name)`` returns ``{"$type": "TextFieldValue"}`` and
a value asked for ``value(bogus)`` returns ``{"$type": ...}``. Nothing separates
them.

``--profile`` is checked on the same path, which matters because the profiles are
field lists like any other. They used to name ``state``, ``priority`` and ``type``,
which are not top-level issue fields at all — verified on a project where every
issue carries all three inside ``customFields``, so their absence proves the point
rather than suggesting it. Those values remain available through ``customFields``,
which ``standard`` and ``full`` expand.

One issue as JSON
^^^^^^^^^^^^^^^^^

``yt issues show`` takes ``--format json``, so the command that names an issue
can also return one as data:

.. code-block:: bash

   yt issues show PROJ-123 --format json

The payload carries ``idReadable`` — the only stable public name for an issue —
along with the summary, description, project, timestamps, tags and links, and each
link carries its ``linkType`` **name**. Workflow state, priority and type are
*not* top-level fields: they appear inside ``customFields``, because the API drops
them when asked for directly. Progress output goes to standard error, so the
payload on standard output is safe to pipe straight into a parser.

``--format ndjson`` skips the check, because a stream that has already emitted
lines cannot un-emit them — failing part-way would hand back a truncated file
that looks complete. Use ``json`` or ``csv`` when the expression needs verifying.

A cap is not a total
^^^^^^^^^^^^^^^^^^^^

``--top``, ``--max-results`` and ``yt ls --limit`` stop the fetch where they say
they do. When that happens the command says so instead of printing the cap as the
size of the result set::

   $ yt issues list -p PROJ --top 50
   ⚠️  Truncated: showing 50 issues, but more match — the fetch stopped at a cap of 50.
      Raise or drop the limit (`--limit N`, or use `yt issues list`, which pages to
      exhaustion) before counting these results.
   Showing 50 issues (not the whole set)

A page that **fails** part-way is reported the same way, and for the same reason:
the issues already read are kept rather than discarded, which means ``count`` is a
count of what survived rather than of what matched::

   ⚠️  Incomplete: showing 100 issues, but the fetch failed part-way (page at
      skip=100 did not return). Issues beyond that page were not read.

The warnings go to standard error for ``json`` and ``csv``, so a piped payload
stays parseable. A read that ran to completion prints the unqualified
``Total: N issues`` / ``Found: N issues`` line; either warning replaces it with a
``Showing N issues (not the whole set)`` line instead, so the number is never
presented as the size of the result set.

``--format ndjson`` gets a differently-worded note, because a stream *cannot* tell
whether a cap hid anything — it stops at the cap whether or not more matched::

   ⚠️  Reached the cap of 100 issues (100 streamed). If that cap was reached
      rather than exhausted, more match and were not fetched.

It is worded as a possibility rather than a claim because at the boundary the two
cases are indistinguishable, and asserting "more match" would be wrong whenever the
count happened to equal the cap exactly. The ``--fields`` check is skipped for
``ndjson`` altogether: a stream that has already emitted lines cannot un-emit them.

Comment Management
------------------

Manage comments on issues.

Add Comments
~~~~~~~~~~~~

.. code-block:: bash

   yt issues comments add ISSUE_ID TEXT

**Example:**

.. code-block:: bash

   yt issues comments add PROJ-123 "Fixed in latest build"

List Comments
~~~~~~~~~~~~~

.. code-block:: bash

   yt issues comments list [ISSUE_ID ...] [OPTIONS]

Accepts one or more issue IDs. When no IDs are passed as arguments, the command
reads them from standard input, one per line (blank lines are ignored):

.. code-block:: bash

   # A single issue
   yt issues comments list PROJ-123

   # Several issues at once
   yt issues comments list PROJ-123 PROJ-456

   # Issue IDs piped from another command or a file
   cat issues.txt | yt issues comments list

When multiple issues are given, the table output is grouped under a heading per
issue, and ``--format json`` returns an object keyed by issue ID. A single issue
keeps the original output shape (a bare table / JSON list).

Filtering with ``--query``
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use ``--query`` to filter comments by an **@mention** in the comment text and/or
the comment **create date**. Terms are combined with ``and`` (the only supported
connector):

* ``@name`` – matches comments whose text mentions ``@name`` (exact login, so
  ``@ryan`` does not match ``@ryanc``).
* ``created OP DATE`` – compares the comment's create date against an ISO
  ``YYYY-MM-DD`` date (interpreted as local start-of-day), where ``OP`` is one of
  ``>``, ``<``, ``>=``, ``<=``. Use two bounds for a range.

.. code-block:: bash

   # Comments that mention @ryan
   yt issues comments list PROJ-123 --query "@ryan"

   # Comments created on or after a date
   yt issues comments list PROJ-123 --query "created >= 2026-01-01"

   # Comments mentioning @ryan created within a date range
   yt issues comments list PROJ-123 --query "@ryan and created >= 2026-01-01 and created < 2026-06-01"

An unrecognized term (for example ``author: bob``) produces a clear error.

**Options:**
  * ``--query TEXT`` - Filter comments by @mention and/or create date (see above)
  * ``--format [table|json]`` - Output format (default: ``table``)
  * ``-h, --help`` - Show help and exit

Update Comments
~~~~~~~~~~~~~~~

.. code-block:: bash

   yt issues comments update ISSUE_ID COMMENT_ID TEXT

Delete Comments
~~~~~~~~~~~~~~~

.. code-block:: bash

   yt issues comments delete ISSUE_ID COMMENT_ID [OPTIONS]

**Options:**
  * ``--force`` - Skip confirmation prompt

Attachment Management
---------------------

Manage file attachments on issues.

Upload Attachments
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   yt issues attach upload ISSUE_ID FILE_PATH

**Example:**

.. code-block:: bash

   yt issues attach upload PROJ-123 /path/to/screenshot.png

Download Attachments
~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   yt issues attach download ISSUE_ID ATTACHMENT_ID [OPTIONS]

**Options:**
  * ``-o, --output PATH`` - Output file path

List Attachments
~~~~~~~~~~~~~~~~

List all attachments for an issue, displaying attachment IDs needed for download and delete operations.

.. code-block:: bash

   yt issues attach list ISSUE_ID [OPTIONS]

**Options:**
  * ``-h, --help`` - Show help and exit (this command takes no other options)

**Output:** Displays attachment ID, name, size, author, and creation date. The attachment ID can be used with the ``download`` and ``delete`` commands.

Delete Attachments
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   yt issues attach delete ISSUE_ID ATTACHMENT_ID [OPTIONS]

**Options:**
  * ``--force`` - Skip confirmation prompt

Issue Relationships
-------------------

Manage links and relationships between issues.

Create Links
~~~~~~~~~~~~

.. code-block:: bash

   yt issues links create SOURCE_ISSUE_ID TARGET_ISSUE_ID LINK_TYPE

**Arguments:**
  * ``SOURCE_ISSUE_ID`` - The ID of the source issue
  * ``TARGET_ISSUE_ID`` - The ID of the target issue
  * ``LINK_TYPE`` - Type of link (e.g., "relates", "depends on", "duplicates", "subtask of")

**Examples:**

.. code-block:: bash

   # Create a dependency link
   yt issues links create PROJ-123 PROJ-124 "depends on"

   # Create a relation link
   yt issues links create PROJ-123 PROJ-125 relates

   # Create a duplicate link
   yt issues links create PROJ-123 PROJ-126 duplicates

.. note::
   The CLI automatically resolves link type names to their internal IDs and handles
   directed vs undirected link types. Use ``yt issues links types`` to see all
   available link types in your YouTrack instance.

List Links
~~~~~~~~~~

.. code-block:: bash

   yt issues links list ISSUE_ID [OPTIONS]

**Options:**
  * ``-h, --help`` - Show help and exit (this command takes no other options)

Delete Links
~~~~~~~~~~~~

.. code-block:: bash

   yt issues links delete SOURCE_ISSUE_ID LINK_ID [OPTIONS]

**Options:**
  * ``--force`` - Skip confirmation prompt

List Link Types
~~~~~~~~~~~~~~~

Display available link types in your YouTrack instance.

.. code-block:: bash

   yt issues links types [OPTIONS]

**Options:**
  * ``-h, --help`` - Show help and exit (this command takes no other options)

Show Related Issues
~~~~~~~~~~~~~~~~~~~

Display all issue relationships dynamically based on YouTrack instance configuration.

.. code-block:: bash

   yt issues related ISSUE_ID [OPTIONS]

**Arguments:**
  * ``ISSUE_ID`` - The ID of the issue to show relationships for

**Options:**
  * ``--format [tree|table]`` - Output format for related issues display (default: tree)
  * ``--show-status`` - Show status indicators in tree view (default: true)

**Examples:**

.. code-block:: bash

   # Show all relationships in tree format (default)
   yt issues related DEMO-123

   # Show relationships in table format
   yt issues related DEMO-123 --format table

   # Hide status indicators in tree view
   yt issues related DEMO-123 --show-status false

   # Show relationships for complex issues with many links
   yt issues related PROJ-456 --format tree

.. note::
   This command shows all relationship types for an issue, not just dependencies.
   Relationship types are fetched dynamically from the YouTrack instance, so it
   adapts to custom relationship types in different YouTrack configurations.
   This provides a comprehensive view of how issues are connected in your project.

Batch Operations
----------------

The ``yt issues batch`` command group provides efficient bulk operations for creating and updating multiple issues from CSV or JSON files. This is ideal for migrating issues, bulk updates, or data imports.

Batch Create Issues
~~~~~~~~~~~~~~~~~~~

Create multiple issues from a CSV or JSON file.

.. code-block:: bash

   yt issues batch create --file INPUT_FILE [OPTIONS]

**Options:**
  * ``-f, --file PATH`` - Path to CSV or JSON file containing issue data (required)
  * ``--dry-run`` - Validate and preview operations without executing them
  * ``--continue-on-error`` - Continue processing after errors (default: true)
  * ``--save-failed PATH`` - Save failed operations to specified file for retry
  * ``--rollback-on-error`` - Rollback (delete) created issues if any operation fails

**CSV File Format:**
The CSV file should have the following columns:

.. code-block:: text

   project_id,summary,description,type,priority,assignee
   FPU,Fix login bug,Login fails on mobile devices,Bug,High,john.doe
   FPU,Add user dashboard,Create dashboard with user metrics,Feature,Medium,jane.smith

**JSON File Format:**
The JSON file should contain an array of issue objects:

.. code-block:: json

   [
     {
       "project_id": "FPU",
       "summary": "Fix login bug",
       "description": "Login fails on mobile devices",
       "type": "Bug",
       "priority": "High",
       "assignee": "john.doe"
     },
     {
       "project_id": "FPU",
       "summary": "Add user dashboard",
       "description": "Create dashboard with user metrics",
       "type": "Feature",
       "priority": "Medium",
       "assignee": "jane.smith"
     }
   ]

**Examples:**

.. code-block:: bash

   # Create issues from CSV file
   yt issues batch create --file issues.csv

   # Dry run to preview operations
   yt issues batch create --file issues.csv --dry-run

   # Create with error handling and save failed operations
   yt issues batch create --file issues.csv --save-failed failed.csv

   # Create with automatic rollback on errors
   yt issues batch create --file issues.csv --rollback-on-error

Batch Update Issues
~~~~~~~~~~~~~~~~~~~

Update multiple issues from a CSV or JSON file.

.. code-block:: bash

   yt issues batch update --file INPUT_FILE [OPTIONS]

**Options:**
  * ``-f, --file PATH`` - Path to CSV or JSON file containing update data (required)
  * ``--dry-run`` - Validate and preview operations without executing them
  * ``--continue-on-error`` - Continue processing after errors (default: true)
  * ``--save-failed PATH`` - Save failed operations to specified file for retry

**CSV File Format:**
The CSV file should include ``issue_id`` and any fields to update:

.. code-block:: text

   issue_id,summary,description,state,type,priority,assignee
   FPU-1,Updated summary,,In Progress,,High,
   FPU-2,,Updated description text,Done,,,john.doe

**JSON File Format:**
The JSON file should contain an array of update objects:

.. code-block:: json

   [
     {
       "issue_id": "FPU-1",
       "summary": "Updated summary",
       "state": "In Progress",
       "priority": "High"
     },
     {
       "issue_id": "FPU-2",
       "description": "Updated description text",
       "state": "Done",
       "assignee": "john.doe"
     }
   ]

**Examples:**

.. code-block:: bash

   # Update issues from CSV file
   yt issues batch update --file updates.csv

   # Dry run to preview updates
   yt issues batch update --file updates.csv --dry-run

   # Update with error handling
   yt issues batch update --file updates.csv --save-failed failed.csv

Validate Batch Files
~~~~~~~~~~~~~~~~~~~~~

Validate a batch operation file without executing operations.

.. code-block:: bash

   yt issues batch validate --file INPUT_FILE --operation OPERATION

**Arguments:**
  * ``--file PATH`` - Path to CSV or JSON file to validate (required)
  * ``--operation [create|update]`` - Type of operation to validate for (required)

**Examples:**

.. code-block:: bash

   # Validate a file for batch create
   yt issues batch validate --file issues.csv --operation create

   # Validate a file for batch update
   yt issues batch validate --file updates.json --operation update

Generate Template Files
~~~~~~~~~~~~~~~~~~~~~~~~

Generate template files for batch operations.

.. code-block:: bash

   yt issues batch templates [OPTIONS]

**Options:**
  * ``--format [csv|json]`` - Template format to generate (default: csv)
  * ``-o, --output-dir PATH`` - Directory to save template files (default: current directory)

**Examples:**

.. code-block:: bash

   # Generate CSV templates in current directory
   yt issues batch templates

   # Generate JSON templates in specific directory
   yt issues batch templates --format json --output-dir ./templates

Batch Operations Best Practices
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**File Preparation:**
  * Always validate your files before running batch operations
  * Use dry-run mode to preview operations and catch potential issues
  * Keep backup copies of your data files

**Error Handling:**
  * Use ``--save-failed`` to capture failed operations for retry
  * Review error messages to understand why operations failed
  * Consider using ``--rollback-on-error`` for create operations when consistency is critical

**Performance:**
  * Batch operations are faster than individual commands for large datasets
  * Progress bars show real-time status and estimated completion time
  * Operations are logged for audit trail and troubleshooting

**Data Quality:**
  * Ensure project IDs, usernames, and field values are valid before processing
  * Use consistent formatting for dates, priorities, and other field values
  * Remove empty rows and columns from CSV files to avoid validation errors

**Workflow Integration:**
  * Generate templates to ensure consistent field mapping
  * Use validation commands in CI/CD pipelines for automated quality checks
  * Combine with scripts for complex data transformations before import

Authentication
--------------

All issue commands require authentication. Make sure you're logged in:

.. code-block:: bash

   yt auth login

Error Handling
--------------

The CLI provides detailed error messages for common issues:

* **Authentication errors** - Check your login status with ``yt auth token --show``
* **Permission errors** - Verify you have access to the project and required permissions
* **Invalid issue IDs** - Ensure the issue exists and you have access to view it
* **API errors** - Network issues or YouTrack server problems

Best Practices
--------------

**Issue Creation:**
  * Use descriptive summaries that clearly identify the problem or request
  * Include detailed descriptions with steps to reproduce for bugs
  * Set appropriate priority and type to help with organization

**Searching:**
  * Use YouTrack's query language for complex searches
  * Combine multiple filters for precise results
  * Save frequently used queries as project saved searches in the web interface

**Comments:**
  * Use comments to track progress and communicate with team members
  * Include relevant context and links to related information
  * Update issue status when commenting on resolution

**Attachments:**
  * Upload screenshots, logs, and relevant files to provide context
  * Use descriptive filenames for easier identification
  * Consider file size limits and compress large files when necessary

Advanced Usage
--------------

**Bulk Operations:**
For bulk operations, combine CLI commands with shell scripting:

.. code-block:: bash

   # Update multiple issues
   for issue in PROJ-123 PROJ-124 PROJ-125; do
       yt issues update $issue -s "Resolved"
   done

**Integration with Scripts:**
Use JSON output for integration with other tools:

.. code-block:: bash

   # Get issue data for processing
   yt issues list -p PROJ-1 --format json | jq '.[] | select(.priority.name == "High")'

**Automation:**
Combine with CI/CD pipelines for automated issue management:

.. code-block:: bash

   # Create issue from build failure
   yt issues create PROJ-1 "Build failed in $BRANCH" -d "Build log: $BUILD_LOG" -t Bug -p High

See Also
--------

* :doc:`projects` - Project management and organization
* :doc:`users` - User management for issue assignment
* :doc:`time` - Time tracking on issues
* :doc:`boards` - Agile board workflow with issues
* :doc:`reports` - Issue-based reporting and analytics
* YouTrack Query Language documentation for advanced search syntax
