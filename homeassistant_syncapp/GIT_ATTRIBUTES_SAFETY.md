# Git attributes safety boundary

SyncApp treats Home Assistant configuration content as data to validate and mirror, not as instructions that may change how Git interprets that data.

Git attributes can select configured clean/smudge filters and other Git drivers. If a managed repository were allowed to supply `.gitattributes`, repository content could influence Git behavior during operations such as staging, checkout, or reset. That would cross the boundary between remotely supplied Home Assistant configuration and the isolated Git control plane under `/data`.

For that reason, `.gitattributes` is a policy-blocked filename at every depth. It is excluded from local publication, rejected as managed remote content, and covered by the workflow safety regression guard. This is an additional exclusion; existing secret and runtime exclusions remain unchanged.

This change does not claim that all persistent Git configuration is immutable. Repository-local Git metadata remains a separate control-state boundary and should continue to be hardened independently. In particular, future work should constrain security-relevant local configuration without freezing ordinary Git bookkeeping.

The live Home Assistant update sequence remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

Git never performs a blind pull into `/homeassistant`; the live configuration remains outside the Git working tree.
