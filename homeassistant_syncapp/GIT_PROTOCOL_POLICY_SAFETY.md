# Git transport protocol safety

SyncApp's production configuration accepts a managed Home Assistant repository only as an HTTPS GitHub repository. Git itself supports additional transport protocols and external remote helpers, so repository-local or ambient Git configuration must not be able to broaden that production trust boundary.

For GitHub-backed managed repositories, every SyncApp Git subprocess now receives command-scope protocol policy that sets `protocol.allow=never` and then explicitly permits only `protocol.https.allow=always`. As a result, transports such as `file`, `git`, SSH, `ext`, and unknown helper-backed protocols are denied by default even if lower-precedence repository configuration attempts to enable them.

This policy composes with the existing authoritative transport alias, URL-rewrite protections, TLS verification, proxy restrictions, disabled credential/helper execution, and descriptor-pinned repository metadata. The exact configured GitHub HTTPS URL remains the only intended network authority for Fetch and publication.

The Git abstraction still permits literal filesystem remotes in its test harness so integration tests can use disposable local bare repositories without network access. Production settings reject those URLs before a `GitRepository` is constructed, so that test-only compatibility path does not broaden the deployed configuration contract.

This milestone does not claim to neutralize `$GIT_DIR/info/attributes`. Git treats that file as a separate high-precedence attribute source, and safely isolating it requires a race-safe metadata-local design rather than a check-then-run pathname test.

The live update workflow remains unchanged:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

No Git checkout, reset, or pull is performed in `/homeassistant`, and no secret/runtime-file exclusion is weakened.
