# pihole-sync

## Mounts

Expects the Statefulset PVC for the instance in question to be mounted in `/mnt/pihole-pvc` and the backup PVC to be mount at `mnt/backup`.

## Environmental Variables

Requires `POD_NAME` to be included with the value from `metadata.name`
