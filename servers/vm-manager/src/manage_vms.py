import yaml, time, requests, json, os
from pprint import pprint
from classes.vm_manager import VMManager
from benedict import benedict
from celery import Celery
from typing import List, Tuple
from datetime import datetime

####################################
############# SETTINGS #############
####################################

project = os.getenv("GC_PROJECT")

# Metadata settings we check of VMs if they are considered the same
settings_to_be_the_same = ["metadata.items", "zone", "machineType"]
vm_config_filepath = "vm-config/vm_configurations.yml"

# Create the celery app and get the logger
app = Celery(
    "app", backend=os.getenv("CELERY_BACKEND_URL"), broker=os.getenv("CELERY_BROKER_URL")
)

startup_script_path = "startup_script_default.sh"

####################################
####################################
####################################
sleep = 2
print(f"sleeping for {sleep} seconds")
time.sleep(sleep)

virtual_machines_wait_time = {}

##########


def load_startup_script(startup_script_path, vmspecs):
    """This function reads in a startup script specified
    by its path and replaces any lines that starts with
    one of the keys in the vmspecs + "=". Hency overwriting
    that value/line.
    """
    with open(os.path.join(startup_script_path), "r") as file1:
        lines = []
        for ln in file1:
            for key in vmspecs.keys():
                if ln.startswith(key.upper() + "="):
                    ln = key.upper() + "=" + str(vmspecs[key]) + "\n"

            lines.append(ln)

    startup_script = "".join(lines)
    return startup_script


def replace_internal_docker_host_with_ip_address(host_url: str, ip_address: str) -> str:
    protocol = host_url.split(":")[0]
    port = host_url.split(":")[-1]
    return f"{protocol}://{ip_address}:{port}"


def load_vmspecs(vm_config_filepath):
    """
    load_vmspecs

    Parameters
    ----------
    vm_config_filepath : str
        VM configurations yml file path

    Returns
    -------
    queue_names, vmspecs

    """
    with open(vm_config_filepath, "r") as c:
        raw_vmspecs = yaml.safe_load(c)

    # Add sensitive data to vmspecs from environment
    host_ip = str(os.getenv("CELERY_HOST"))

    # Celery
    raw_vmspecs["DEFAULT"][0]["celery_broker_username"] = str(
        os.getenv("CELERY_BROKER_USERNAME")
    )
    raw_vmspecs["DEFAULT"][0]["celery_broker_password"] = str(
        os.getenv("CELERY_BROKER_PASSWORD")
    )
    raw_vmspecs["DEFAULT"][0][
        "celery_broker_url"
    ] = replace_internal_docker_host_with_ip_address(
        str(os.getenv("CELERY_BROKER_URL")), host_ip
    )
    raw_vmspecs["DEFAULT"][0][
        "celery_broker"
    ] = replace_internal_docker_host_with_ip_address(
        str(os.getenv("CELERY_BROKER")), host_ip
    )
    raw_vmspecs["DEFAULT"][0][
        "celery_backend_url"
    ] = replace_internal_docker_host_with_ip_address(
        str(os.getenv("CELERY_BACKEND_URL")), host_ip
    )
    raw_vmspecs["DEFAULT"][0][
        "celery_result_backend"
    ] = replace_internal_docker_host_with_ip_address(
        str(os.getenv("CELERY_RESULT_BACKEND")), host_ip
    )

    # output folder
    raw_vmspecs["DEFAULT"][0]["PIPELINE_OUTPUT_FOLDER"] = str(
        os.getenv("PIPELINE_OUTPUT_FOLDER")
    )

    raw_vmspecs["DEFAULT"][0]["HOST_ENVIRONMENT"] = str(os.getenv("HOST_ENVIRONMENT"))

    raw_vmspecs["DEFAULT"][0]["CELERY_HOST"] = host_ip

    # Get the queue names from the vm_configurations.yml
    raw_vmspecs["DEFAULT"][0]["VM_NAME_PREFIX"] = str(os.getenv("VM_NAME_PREFIX"))
    queue_names = list(raw_vmspecs.keys())

    queue_names.remove("DEFAULT")

    # Apply default values to other VM configurations
    vmspecs = {}
    for queue_name in queue_names:
        queue_list = []
        for vmspec in raw_vmspecs[queue_name]:
            # First copy the default specifications
            new_specs = raw_vmspecs["DEFAULT"][0].copy()

            # Now overwrite any option that has been specified
            for key, value in vmspec.items():
                new_specs[key] = value

            # Add VM name prefix
            new_specs["name"] = f"{str(os.getenv('VM_NAME_PREFIX'))}-{new_specs['name']}"

            queue_list.append(new_specs)

        vmspecs[queue_name] = queue_list

    return queue_names, vmspecs


def compare_metadata(metadata1, metadata2):
    """
    Compares inputted metadatas and determines if
    they are different of not. Only checks the fields
    described by "settings_to_be_the_same".

    RETURNS:
    Bool | True if metadatas are the same, otherwise false
    """
    metadata1 = benedict(metadata1)
    metadata2 = benedict(metadata2)
    comparison = False
    for setting in settings_to_be_the_same:
        if setting == "zone":
            if not metadata2[setting].endswith(metadata1[setting]):
                comparison |= True
        elif metadata2[setting] != metadata1[setting]:
            pprint(
                f"For {metadata1['name']} the following settings has changed {setting}"
            )
            print(metadata2[setting])
            print(40 * "#")
            print(metadata1[setting])
            comparison |= True

    return not comparison


def get_message_count(app: Celery, queue_name: str) -> int:
    client = app.connection().channel().client
    return len(client.lrange(queue_name, 0, -1))


def get_vm_task_statistics(app: Celery, vm_name: str) -> Tuple[int, int, int, int]:
    """
    Gets information about total, scheduled, active and reserved
    tasks of a worker vm

    RETURNS:
    Tuple[int, int, int, int]:
    """
    print(f"\t\t{vm_name}:")

    i = app.control.inspect()

    total_accepted_tasks = 0
    stats = i.stats()
    if stats is not None:
        for vm_worker_name in stats:
            if vm_name in vm_worker_name:
                for registered_task in stats[vm_worker_name]["total"]:
                    total_accepted_tasks += stats[vm_worker_name]["total"][
                        registered_task
                    ]
                print(f"\t\t\tTotal accepted:{total_accepted_tasks}")

    scheduled = i.scheduled()
    scheduled_tasks = 0
    if scheduled is not None:
        for vm in scheduled:
            if vm_name in vm:
                # if len(scheduled[vm]) > 0:
                #     for elem in scheduled[vm]:
                #         print(f"\t\t\t{elem['args'][0]}")
                scheduled_tasks += len(scheduled[vm])
                print(f"\t\t\tScheduled:{scheduled_tasks}")

    active = i.active()
    active_tasks = 0
    if active is not None:
        for vm in active:
            if vm_name in vm:
                # if len(active[vm]) > 0:
                #     for elem in active[vm]:
                #         print(f"\t\t\t{elem['args'][0]}")
                active_tasks += len(active[vm])
                print(f"\t\t\tActive:{active_tasks}")

    reserved = i.reserved()
    reserved_tasks = 0
    if reserved is not None:
        for vm in reserved:
            if vm_name in vm:
                # if len(reserved[vm]) > 0:
                #     for elem in reserved[vm]:
                #         print(f"\t\t\t{elem['args'][0]}")
                reserved_tasks += len(reserved[vm])
                print(f"\t\t\tReserved:{reserved_tasks}")

    return (total_accepted_tasks, scheduled_tasks, active_tasks, reserved_tasks)


vmmanager = VMManager(project=project)
while True:
    print("Managing VMs for each queue:")
    queue_names, vmspecs = load_vmspecs(vm_config_filepath)

    for queue_name in queue_names:
        message_count = get_message_count(app, queue_name)
        print(f"\tat queue:{queue_name}, message_count:{message_count}")

        for vmspec in vmspecs[queue_name]:
            # Set the startup-script properly:
            vmspec["queue"] = queue_name
            vmspec["startup_script"] = load_startup_script(
                vmspec["startup_script_file"], vmspec
            )

            # Get the current status of the VM in question
            try:
                metadata = vmmanager.get_metadata(vmspec["name"], vmspec["zone"])
                status = metadata["status"]

                # Also check if the settings have changed
                wanted_metadata = vmmanager.create_metadata(**vmspec)
                changed_metadata = not compare_metadata(wanted_metadata, metadata)
            # If that didn't work it probably doesn't exists
            except:
                status = None
                changed_metadata = None  # type:ignore

            (
                total_accepted_tasks,
                scheduled_tasks,
                active_tasks,
                reserved_tasks,
            ) = get_vm_task_statistics(app, vmspec["name"])

            if vmspec["name"] not in virtual_machines_wait_time:
                virtual_machines_wait_time[vmspec["name"]] = [None, total_accepted_tasks]

            # If this VM is supposed te be running
            if vmspec["min_nr_jobs"] == 0:
                should_be_running = (
                    message_count + scheduled_tasks + active_tasks + reserved_tasks
                    > vmspec["min_nr_jobs"]
                )
            else:
                should_be_running = message_count > vmspec["min_nr_jobs"]

            if not should_be_running and (
                virtual_machines_wait_time[vmspec["name"]][0] is None
                or virtual_machines_wait_time[vmspec["name"]][1] != total_accepted_tasks
            ):
                virtual_machines_wait_time[vmspec["name"]] = [
                    datetime.now(),  # type:ignore
                    total_accepted_tasks,
                ]
            elif should_be_running:
                virtual_machines_wait_time[vmspec["name"]] = [None, total_accepted_tasks]

            # Now we do some logic based on these statussen according to the following schema
            # | status | should_be_running | changed  |          |
            # |        |                   | metadata |          |
            # |--------|-------------------|----------|----------|
            # | False  | True              | False    | start    |
            # | None   | True              | None     | create   |
            # | False  | True              | True     | update   |
            # | False  | False             | True     | update   |
            # | True   | True              | True     | stop     |
            # | True   | False             | True     | stop     |
            # | True   | False             | False    | stop     |
            # | True   | True              | False    | pass     |
            # | False  | False             | False    | pass     |
            # | None   | False             | None     | pass     |

            # print(f"status = {status}, should be running = {should_be_running}, changed_metadata = {changed_metadata}")

            # Start VM
            if (status == "TERMINATED") and should_be_running and (not changed_metadata):
                vmmanager.start_vm(vmspec["name"], vmspec["zone"])
                print(f"\t\tStarting VM {vmspec['name']}")
            # Create VM
            if (status is None) and should_be_running and (changed_metadata is None):
                vmmanager.create_vm(**vmspec)
                print(f"\t\tCreated VM {vmspec['name']}")
            # Update VM
            if (status == "TERMINATED") and changed_metadata:
                vmmanager.update_vm(**vmspec)
                print(f"\t\tUpdating VM {vmspec['name']}")
            # Stop VM
            if ((status == "RUNNING") and not should_be_running) or (
                (status == "RUNNING") and changed_metadata
            ):
                # First we stop the celery worker
                # app.control.broadcast('shutdown', destination='worker1@example.com')
                # We only want to stop the VM, if it is actually done
                # with its current tasks.
                # vmmanager.stop_vm(vmspec['name'], vmspec['zone'])
                # print(f"Stopping VM {vmspec['name']}")

                alive_workers = app.control.inspect().active()
                if alive_workers is not None:
                    for alive_worker in alive_workers:
                        if alive_worker.endswith(vmspec["name"]):
                            waited_time = (
                                datetime.now()  # type:ignore
                                - virtual_machines_wait_time[vmspec["name"]][0]
                            ).seconds / 60  # in minutes
                            if waited_time < vmspec["wait_time_before_shutdown"]:
                                waiting_for = int(
                                    vmspec["wait_time_before_shutdown"] - waited_time
                                )
                                print(
                                    f"\t\tNot yet stopping worker: {alive_worker} (waiting {waiting_for} minutes...)"
                                )
                                continue

                            print(f"\t\tStopping worker: {alive_worker}")
                            app.control.cancel_consumer(
                                queue=vmspec["queue"], destination=[alive_worker]
                            )
                            time.sleep(10)
                            app.control.broadcast("shutdown", destination=[alive_worker])
    print()
    time.sleep(1)
