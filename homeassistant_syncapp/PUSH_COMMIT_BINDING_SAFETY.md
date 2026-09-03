# Immutable commit-to-push binding

SyncApp must publish the exact Git commit whose tree passed local candidate validation. A successful validation must not authorize whatever object a mutable `HEAD` happens to reference later.

Local publication therefore carries the verified commit object ID into `GitRepository.push()`. Failed-push recovery does the same with the single unpushed commit that was independently rebound to descriptor-validated live Home Assistant configuration and semantic validation. The push refspec names that exact commit object as its source and the configured managed branch as its destination.

`GitRepository.push()` resolves the supplied object as a commit and requires the resolution to equal the supplied object ID before network publication. This makes a later local `HEAD` advance irrelevant to the bytes sent by that push. Remote provenance checks remain mandatory before publication.

This boundary only hardens outbound publication. Remote updates remain **Detect → Fetch → Stage → Validate → Backup → Apply → Verify → Rollback if necessary**. No blind `git pull` touches `/homeassistant`, and secret/runtime exclusions remain unchanged.
