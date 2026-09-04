# Git trace confidentiality safety

SyncApp supplies GitHub authentication to Git subprocesses through command-scoped configuration. Inherited Git tracing must not be able to dump transport data or disable Git's normal credential redaction around those subprocesses.

Before every SyncApp Git command, the environment builder removes the entire `GIT_TRACE*` family. This covers the legacy trace controls, curl tracing, packet/pack traces, Trace2 outputs, and `GIT_TRACE_REDACT`.

Git documents `GIT_TRACE_CURL` as a full trace of incoming and outgoing transport data. Git also documents `GIT_TRACE_REDACT=false` as disabling the default redaction of cookies and Authorization headers. Scrubbing the whole trace namespace prevents inherited runtime state from turning ordinary SyncApp Fetch/Push operations into an authentication-data logging channel.

This is additive to the existing protections for Git HTTP headers/cookies, TLS verification, redirect policy, proxy/helper execution, authoritative transport URL locking, and descriptor-pinned Git metadata.

The live Home Assistant workflow remains:

**Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**

`/homeassistant` remains outside Git. No blind `git pull` is introduced, and managed secret/runtime exclusions are unchanged.
