import argparse
import logging
import sqlite3
import shutil
import time
from os import path, environ
import  kubernetes

def main():
    parser = argparse.ArgumentParser(description='Sync Pihole Statefulset')
    parser.add_argument('name', type=str, help='Name of Pihole Statefulset')
    parser.add_argument("--init", action="store_true", help="Pass flag to initialize the pod rather than sync all replicas.")
    parser.add_argument('--namespace', type=str, default=None, help="Namespace for Pihole Statefulset, defaults to reading from /run/secrets/kubernetes.io/serviceaccount/namespace")
    parser.add_argument("--backup-mount", type=dir_path, default="/mnt/backup", help="Mount directory for backup PVC")
    parser.add_argument("--pihole-pvc-mount", type=dir_path, default="/mnt/pihole-pvc", help="Directory containing the mount for the PiHole PVC of the pod")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Sets the logging level to use.")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level)

    pod_name = environ['POD_NAME']
    if args.namespace:
        namespace = args.namespace
    else:
        with open('/run/secrets/kubernetes.io/serviceaccount/namespace', 'r') as namespace_file:
            namespace = namespace_file.readline()

    if args.init:
        initialize_sync(args.name, namespace, pod_name, args.pihole_pvc_mount, args.backup_mount)
    else:
        scheduled_sync(args.name, namespace, args.pihole_pvc_mount, args.backup_mount)

def dir_path(string: str):
    """
    Normalize path
    """
    return path.normpath(string)

def initialize_sync(name: str, namespace: str, pod_name: str, pihole_pvc_mount: str, backup_mount: str,) -> None:
    """
    Perform initial sychronization
    """
    if pod_name == f"{name}-0":
        logging.info("Not syncing first pod (%s) on initalization.",pod_name)
        if not path.join(pihole_pvc_mount, "gravity.db"):
            logging.warning("Pihole has not yet been initialized, subsequent pods will be unable to start up until gravity.db exists and has been copied to the backup PVC by the synchronization job.")
        return
    # Check if DB needs updating
    if not check_gravity_db_changed(backup_mount, pihole_pvc_mount):
        logging.info("Database has not changed, not performing sync.")
        return

    api_instance = get_api_instance(type="core")
    # Don't synchronize if first pod isn't running
    if not is_first_pod_running(name, namespace, api_instance):
        logging.error("Primary pod %s not running, aborting synchronization!", pod_name)
        raise RuntimeError("Sychronization blocked while primary pod is offline.")

    logging.info("Syncing %s gravity.db", pod_name)
    update_gravity_db(backup_mount, pihole_pvc_mount, pod_name)

    
def scheduled_sync(name: str, namespace: str, pihole_pvc_mount: str, backup_mount: str) -> None:
    """
    Regularly scheduled sync, copies the database onto NFS and then scales down to one and back to the original size to distribute to the replicas
    """
    # Check if database has changed, exit if it hasn't
    if not check_gravity_db_changed(pihole_pvc_mount, backup_mount):
        logging.info("Database has not changed, not performing sync.")
        return

    api_instance = get_api_instance(type="app")
    original_replica_count = get_current_replica_count(name, namespace, api_instance)
    logging.info("Got %s replicas from StatefulSet/%s", original_replica_count, name)

    # Backup databases, then scale down and backup up so init containers run
    backup_gravity_db(pihole_pvc_mount, backup_mount)
    # Scale down replicas to 1
    set_new_replica_amount(name, namespace, api_instance, 1)   
    # Scale backup to original count
    set_new_replica_amount(name, namespace, api_instance, original_replica_count)

def get_api_instance(type: str):
    """
    Get API instance from pod's config
    """
    config = kubernetes.config.load_incluster_config()

    with kubernetes.client.ApiClient(config) as api_client:
        if type == "app":
            return kubernetes.client.AppsV1Api(api_client)
        if type == "core":
            return kubernetes.client.CoreV1Api(api_client)
        else:
            logging.error("Unsupported API client type requested %s, must be app or core.", type)
            raise RuntimeError("Unsupported type requested")

def is_first_pod_running(sts_name, namespace, api_instance) -> bool:
    primary_name = f"{sts_name}-0"
    try:
        primary_pod_response = api_instance.read_namespaced_pod(primary_name, namespace)
    except kubernetes.client.rest.ApiException as api_error:
        logging.error("Unable to get current pod status.")
        raise api_error
    # Look for Ready and return its condition
    for condition in primary_pod_response.status.conditions:
        if condition.type == "Ready":
            # If false or unknown, return false
            return True if condition.status == "True" else False
    logging.warning("Unable to find Ready condition for pod %s", primary_name)
    return False

def get_current_replica_count(name: str, namespace: str, api_instance) -> int:
    """
    Get the current number of replicas
    """
    try:
        statefulset_response = api_instance.read_namespaced_stateful_set_scale(name, namespace)
    except kubernetes.client.rest.ApiException as api_error:
        logging.error("Unable to get current replica count.")
        raise api_error
    return statefulset_response.spec.replicas

def set_new_replica_amount(name: str, namespace: str, api_instance, replica_count: int) -> None:
    """
    Set a new number of replicas for the StatefulSet
    """
    try:
        logging.info("Scaling %s to %s replicas", name, replica_count)
        scale_spec = kubernetes.client.V1ScaleSpec(replicas=replica_count)
        scale_changes = kubernetes.client.V1Scale(spec=scale_spec)
        api_instance.patch_namespaced_stateful_set_scale(name, namespace, scale_changes,field_validation="Strict")
        count = 0
        while api_instance.read_namespaced_stateful_set_scale(name, namespace).status.replicas != replica_count:
            count += 1
            time.sleep(1)

    except kubernetes.client.rest.ApiException as api_error:
        logging.error("Unable to update replica count.")
        raise api_error

def check_gravity_db_changed(source_pvc: str, dest_pvc: str) -> bool:
    """
    Return True if the database on source_pvc is newer than dest_pvc
    """
    source_db = path.join(source_pvc, "gravity.db")
    if path.exists(source_db):
        source_db_time = path.getmtime(source_db)
        logging.debug("Timestamp for %s is %s", source_db, source_db_time)
    else:
        logging.error("%s does not exist", source_db)
        raise RuntimeError(f"Missing {source_db}, cannot continue.")

    dest_db = path.join(dest_pvc, "gravity.db")
    if path.exists(dest_db):
        dest_db_time = path.getmtime(dest_db)
        logging.debug("Timestamp for %s is %s", dest_db, dest_db_time)
    else:
        logging.warning("%s does not exist, therefore %s is being treated as changed", dest_db, source_db)
        return True

    return source_db_time > dest_db_time

def backup_gravity_db(source_pvc: str, dest_pvc: str) -> None:
    """
    Backup database from primary node to backup pvc
    """
    logging.info("Backing up database from primary pod")
    source_db = sqlite3.connect(path.join(source_pvc, "gravity.db"))
    backup_db = sqlite3.connect(path.join(dest_pvc, "gravity.db"))
    with backup_db:
        source_db.backup(backup_db)
    backup_db.close()
    source_db.close()

def update_gravity_db(backup_pvc: str, dest_pvc: str, pod_name: str):
    """
    Sync database from backup pvc to replica
    """
    logging.info("Copying database to %s", pod_name)
    shutil.copy2(path.join(backup_pvc, "gravity.db"), path.join(dest_pvc, "gravity.db"))

if __name__ == '__main__':
    main()