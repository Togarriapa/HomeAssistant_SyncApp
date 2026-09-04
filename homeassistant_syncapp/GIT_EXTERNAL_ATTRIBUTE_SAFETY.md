# External Git attribute safety

Git attributes can select clean, smudge, and long-running process filters. SyncApp therefore treats attribute configuration as Git control state rather than Home Assistant configuration data.

Managed `.gitattributes` files are already excluded from the Home Assistant data plane. Every SyncApp Git subprocess now also removes inherited `GIT_ATTR_SOURCE`, forces `GIT_ATTR_NOSYSTEM=1`, and sets command-scope `core.attributesFile=/dev/null`.

Together these controls prevent ambient treeish selection, system attribute files, global/user attribute files, and repository-local attempts to redirect `core.attributesFile` from supplying filter-driving attributes to SyncApp Git commands.

This slice deliberately does **not** claim to neutralize `$GIT_DIR/info/attributes`, which Git treats as a separate repository-local attribute source with high precedence. That metadata-local file is the next safety boundary and must be handled without relying on a check-then-run pathname test.

The live Home Assistant workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and secret/runtime exclusions are unchanged.