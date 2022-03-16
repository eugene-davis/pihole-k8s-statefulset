# Pihole StatefulSet with Pod Syncing

This configuration will deploy Pihole as a StatefulSet on Kubernetes, and provide sychronization using the code found in `pihole-sync-image`.

## What it Does

1. Multiple load-balanced Pihole instances
2. Automatic synchronization of stateful set pods `gravity.db` database while keeping the database on local storage for performance reasons.
3. Web interface only accessible on the primary pod (pihole-0) - no bi-directional syncing
4. Web interface accessible over Ingress, DNS services by LoadBalancer

## What it Doesn't Do

1. Synchronize statistics between pods - that database can grow to much larger sizes than gravity.db
2. Synchronize local DNS records - current that is provided via a read-only ConfigMap, so must be edited in the `vaules.yaml` file and then redeployed. Most likely this will be changed to enable dynamic creation of local DNS without restarting the Pihole.
3. External backup of gravity.db. This can be handled with a custom CronJob on the backup PVC, or via the teleporter utility in Pihole.

## Usage

### Requirements and Assumptions

| Requirement | Explaination |
| -- | -- |
| LoadBalancer | [Metallb](https://metallb.org/) is required for exposing the DNS services. If you are interested in adding support for more LoadBalancers, PRs are welcome - a good starting point to look at is `pihole-synchronized/templates/services` |
| IngressController | Tested with [nginx-ingress](https://docs.nginx.com/nginx-ingress-controller/), should work fine with other Ingress Controllers. |
| Local StorageClass | Tested with [Local Path Provisioner](https://github.com/rancher/local-path-provisioner), should work with other StorageClasses. Used for pod configuration volumes. |
| Remote StorageClass | Tested with [NFS Subdir External Provisioner](https://github.com/kubernetes-sigs/nfs-subdir-external-provisioner), should work with other storage classes. Used for `gravity.db` backup to be accesible across nodes. |

### Configuration

See `pihole-synchronized/values.yaml` for all values, the following table lists a subset of what is most likely to need updating:

| Variable | Default | Explaination |
| -- | -- | -- |
| piholeAdminPass | password | Change this before deploying to be the password you want used with the web interface. |
| replicaCount | 2 | Number of pihole pods to deploy |
| image | multi-value | Details for the pihole image to deploy. |
| initSecurityContext | multi-value | user and group to execute the init and sync containers under, change with caution as it may block startup of non-primary pods |
| volumeClaimTemplates | multi-value | Configure your local StorageClass for local Pihole config here. Avoid using remote storage. |
| backupVolumeClaim | multi-value | Configure your remote StorageClass for the backup directory used in syncing. |
| loadBalancer.ip | 192.168.0.2 | Set to your desired DNS IP |
| loadBalancer.addressPool | default | Set to the appropriate IP pool for Metallb |
| environmentalVariables | multi-value | See [Pihole Environmental Values](https://github.com/pi-hole/docker-pi-hole#environment-variables) |
| customDomains | Empty | Provide contents of `/etc/pihole/custom.list` to configure local domains |
| ingress.host | pihole.example.com | Configure host for Ingress to configure |
| ingress.useTls | true | Enable TLS - strongly encouraged even for local networks |
| ingress.tlsSecret | Empty | Conf be configured with an existing TLS certificate for the Ingress to use, leave blank to create a new one (cert and key must be provided) |
| ingress.key | Empty | Private key to create a TLS secret with. Manage key material with care! |
| ingress.cert | Empty | Certificate to create a TLS secret with. |
| syncJob.schedule |  "00 */3 * * *" | Cron configuration for synchronization job, default runs every three hours. |
| syncJob.ttlSecondsAfterFinished | 10800 | Time to leave individual sync jobs around before cleaning them up. |

### Installing

Add the repository:

```bash
helm repo add pihole-synchronized https://eugene-davis.github.io/pihole-k8s-statefulset/
```

Install the chart:

```bash
helm install pihole pihole-synchronized --values values.yaml
```

### Initial Sync

Prior to the initial synchronization, replicas will be unable to start as the init container will be unable to retrieve a copy of `gravity.db`.

To solve this, you can immedialely execute an instance of the `pihole-sync` cronjob with `kubectl create job --from=cronjob/pihole-test-pihole-synchronized-sync initial-sync`.

Check its completion with `kubectl get job initial-sync`.

Clean up with `kubectl delete job initial-sync`.
