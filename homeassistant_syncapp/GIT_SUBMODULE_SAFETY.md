# Git submodule control safety boundary

SyncApp does not use Git submodules to manage Home Assistant configuration. Remote configuration trees are required to contain ordinary blobs with supported regular-file modes; gitlink entries are rejected during staging validation.

`.gitmodules` is nevertheless a Git control file: it can define submodule URLs and update behavior. Allowing it into the managed configuration data plane would create dormant Git instructions that could become active if repository commands are expanded later.

For defense in depth, `.gitmodules` is blocked at every path depth. It is neither published from the live Home Assistant configuration nor accepted as managed remote content. This tightens policy without relaxing any existing secret/runtime exclusions.

The live update sequence remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

SyncApp never performs a blind `git pull` into `/homeassistant`; Git remains confined to the isolated `/data` repository.
