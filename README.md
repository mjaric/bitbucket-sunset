bitbucket-sunset - migrate Bitbucket DC repo permissions to GitHub Enterprise

Overview
- This repository contains small, testable scripts to extract the authorization matrix (permissions) from Bitbucket Data Center and to apply equivalent permissions on GitHub Enterprise.
- Identity is matched by email address (NOT by username), per your requirement.
- GitHub repositories are assumed to be named using the convention: ${PROJECT_KEY}-${REPOSITORY_SLUG} inside a single target organization.
- The workflow is split into phases with CSV hand-offs and a dry-run mode for each phase.

Requirements
- Python 3.11+
- uv (for dependency management and running scripts)
- Bitbucket DC credentials (token, or username/password) with permission to read repo permissions and group members
- GitHub token with admin rights on the target organization and repo scope

Install dependencies with uv
- uv sync

Console entry
- uv run python -m bitbucket_sunset --help
- Note: If you install this package (e.g., `uv pip install -e .`), you can also use the console script `bitbucket-sunset --help` outside of `uv run`. Depending on your uv version, `uv run bitbucket-sunset` may not be available.

Phases
1) Extract (Bitbucket → CSV)
   - Produces:
     - out/repo_user_permissions.csv
       columns: project_key,repo_slug,principal_type,principal,email,permission
     - out/repo_group_permissions.csv
       columns: project_key,repo_slug,principal_type,principal,permission
     - out/group_members.csv
       columns: group,user,email
   - Example:
     uv run python -m bitbucket_sunset extract \
       --base-url https://bitbucket.example.com \
       --token $BB_TOKEN \
       --output-dir out \
       --project PROJKEY \
       --dry-run
   - Notes:
     - You can use --username and --password instead of --token.
     - Use --project and --repo multiple times to limit the extraction.
     - Email is the key identifier. If email is not present in the permission listing, we try to fetch it via user lookup.

2) Expand (CSV → effective per-user CSV)
   - Joins group-based permissions with group membership and merges with direct user permissions to compute an effective per-user per-repo permission.
   - Strongest permission wins (REPO_ADMIN > REPO_WRITE > REPO_READ).
   - Produces: out/effective_repo_user_permissions.csv
     columns: project_key,repo_slug,email,permission,source,source_principal
   - Example:
     uv run python -m bitbucket_sunset expand \
       --user-permissions out/repo_user_permissions.csv \
       --group-permissions out/repo_group_permissions.csv \
       --group-members out/group_members.csv \
       --output out/effective_repo_user_permissions.csv \
       --dry-run

3) Apply (effective CSV → GitHub)
   - Applies per-user permissions on GitHub repositories using the convention ORG/${PROJECT_KEY}-${REPOSITORY_SLUG}.
   - Permission mapping:
     Bitbucket REPO_READ → GitHub pull
     Bitbucket REPO_WRITE → GitHub push
     Bitbucket REPO_ADMIN → GitHub admin
   - Requires a mapping from user email to GitHub login. Provide a CSV with columns email,github_login.
   - Example:
     uv run python -m bitbucket_sunset apply \
       --token $GH_TOKEN \
       --org target-org \
       --effective-csv out/effective_repo_user_permissions.csv \
       --mapping-csv email_github_login.csv \
       --dry-run
   - Options:
     - --default-missing <login>: If an email is not found in the mapping, use this default login (otherwise the entry is skipped with a warning).

Environment and security
- Pass tokens via environment variables when possible (e.g., BB_TOKEN, GH_TOKEN) and reference them on the command line.
- All scripts support a --dry-run flag that makes no changes and logs intended actions.

Notes and limitations
- This implementation focuses on repository-level permissions. If you also have project-level default permissions, you may extend the extraction to include them similarly.
- Group membership export uses admin endpoints; ensure your Bitbucket token has enough rights to read members and emails.
- GitHub user resolution is based on a mapping CSV email→github_login to avoid reliance on username differences. If you have an internal identity service, you can generate this mapping separately.

Troubleshooting
- Increase verbosity by running with the environment variable: PYTHONWARNINGS=default
- Use --rate-limit-sleep with extract if your Bitbucket DC throttles requests.
- If you see errors about missing modules, run `uv sync` again.

Quick start
- Install uv: follow https://docs.astral.sh/uv/ or e.g. on macOS: brew install uv
- In this repo: uv sync
- Show CLI help: uv run python -m bitbucket_sunset --help
- Show subcommand help: uv run python -m bitbucket_sunset extract --help

Typical workflow
1) Extract from Bitbucket to CSVs (dry-run first)
   uv run python -m bitbucket_sunset extract \
     --base-url https://bitbucket.example.com \
     --token $BB_TOKEN \
     --output-dir out \
     --project PROJKEY \
     --dry-run

   Execute and write CSVs by removing --dry-run.

2) Expand group permissions into per-user effective permissions
   uv run python -m bitbucket_sunset expand \
     --user-permissions out/repo_user_permissions.csv \
     --group-permissions out/repo_group_permissions.csv \
     --group-members out/group_members.csv \
     --output out/effective_repo_user_permissions.csv

3) Apply to GitHub (dry-run first)
   # Prepare a mapping CSV with columns: email,github_login
   # Example (email_github_login.csv):
   # email,github_login
   # alice@example.com,alice-gh
   # bob@example.com,bob-gh

   uv run bitbucket-sunset apply \
     --token $GH_TOKEN \
     --org your-org \
     --effective-csv out/effective_repo_user_permissions.csv \
     --mapping-csv email_github_login.csv \
     --dry-run

   Execute for real by removing --dry-run. Optionally supply --default-missing some-login to use a fallback for unmapped emails.

Alternative invocation
- You can also invoke via the module entrypoint:
  uv run python -m bitbucket_sunset --help

Environment variables
- Export tokens in your shell and reference them:
  export BB_TOKEN=...   # Bitbucket personal access token with rights to read repo perms and group members
  export GH_TOKEN=...   # GitHub token with admin:org and repo scopes for the target org

Verification tips
- After sync: uv run python -m bitbucket_sunset --help should print top-level help.
- For detailed flags of a subcommand: uv run python -m bitbucket_sunset <subcommand> --help

CSV outputs and formats
- out/repo_user_permissions.csv: project_key,repo_slug,principal_type,principal,email,permission
- out/repo_group_permissions.csv: project_key,repo_slug,principal_type,principal,permission
- out/group_members.csv: group,user,email
- out/effective_repo_user_permissions.csv: project_key,repo_slug,email,permission,source,source_principal

Notes
- SSL verification is on by default; disable with --no-verify-ssl on extract if needed.
- If Bitbucket throttles you, add --rate-limit-sleep 0.2 (or similar) on extract.
- If you encounter missing modules/errors, run uv sync again.
