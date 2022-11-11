import googleapiclient.discovery

compute = googleapiclient.discovery.build("compute", "v1")


class VMManager:
    def __init__(self, project, debug=False, silent=True):
        """
        Manages starting, stopping, creating and updating of VMs in GCP.
        """
        self.project = project

    def get_metadata(self, name, zone):
        """Returns metadata of VM instance in GCP."""
        return (
            compute.instances()
            .get(project=self.project, zone=zone, instance=name)
            .execute()
        )

    def start_vm(self, name, zone):
        """Starts a VM instance in GCP."""
        return (
            compute.instances()
            .start(project=self.project, zone=zone, instance=name)
            .execute()
        )

    def stop_vm(self, name, zone):
        """Stops a VM instance in GCP."""
        return (
            compute.instances()
            .stop(project=self.project, zone=zone, instance=name)
            .execute()
        )

    def create_vm(self, **config_dict):
        """
        Creates VM based on configuration data.
        Config data can have everything in it that create_metadata
        accepts as input.
        """
        config = self.create_metadata(**config_dict)

        return (
            compute.instances()
            .insert(project=self.project, zone=config_dict["zone"], body=config)
            .execute()
        )

    def update_vm(self, **config_dict):
        """
        Updates VM based on configuration data. The name and zone
        of the VM should be corresponding to an existing VM.
        Config data can have everything in it that create_metadata
        accepts as input.
        """
        config = self.create_metadata(**config_dict)

        currMetadata = (
            compute.instances()
            .get(
                project=self.project,
                zone=config_dict["zone"],
                instance=config_dict["name"],
            )
            .execute()
        )

        assert currMetadata["status"] == "TERMINATED", "Make sure the VM is shutdown"

        # Copy over some necessary configurations otherwise the update won't work
        config["fingerprint"] = currMetadata["fingerprint"]
        config["networkInterfaces"] = currMetadata["networkInterfaces"]
        config["shieldedInstanceIntegrityPolicy"] = currMetadata[
            "shieldedInstanceIntegrityPolicy"
        ]

        return (
            compute.instances()
            .update(
                project=self.project,
                zone=config_dict["zone"],
                instance=config_dict["name"],
                body=config,
            )
            .execute()
        )

    def create_metadata(
        self,
        name,
        zone,
        machinetype,
        source_disk_image,
        service_account_email,
        access_scopes,
        network,
        gpu_type=None,
        gpu_count=0,
        preemptible=False,
        labels=None,
        startup_script=None,
        **kwargs,
    ):
        """Returns all the metadata required to create VM in GCP based on a configuration dict."""
        machine_type = f"https://www.googleapis.com/compute/v1/projects/{self.project}/zones/{zone}/machineTypes/{machinetype}"

        config = {
            "name": name,
            "machineType": machine_type,
            # Specify the boot disk and the image to use as a source.
            "disks": [
                {
                    "boot": True,
                    "autoDelete": True,
                    "initializeParams": {
                        "sourceImage": source_disk_image,
                    },
                }
            ],
            "scheduling": {
                "automaticRestart": True,
                "onHostMaintenance": "TERMINATE",
                "preemptible": preemptible,
            },
            # Specify a network interface with NAT to access the public
            # internet.
            "networkInterfaces": [
                {
                    "network": network,
                    "accessConfigs": [
                        {
                            "type": "ONE_TO_ONE_NAT",
                            "networkTier": "STANDARD",
                            "name": "External NAT",
                        }
                    ],
                }
            ],
            # Allow the instance to access cloud storage, logging and compute.
            "serviceAccounts": [
                {"email": service_account_email, "scopes": access_scopes}
            ],
            # Metadata is readable from the instance and allows you to
            # pass configuration from deployment scripts to instances.
            "metadata": {
                "items": [
                    {
                        # Startup script is automatically executed by the
                        # instance upon startup.
                        "key": "startup-script",
                        "value": startup_script,
                    }
                ]
            },
            "labels": labels,
            # 'zone': f'https://www.googleapis.com/compute/v1/projects/{project}/zones/{zone}'
            "zone": zone,
        }

        if gpu_type is not None:
            valid_gpu_type = False
            if gpu_type.lower() == "k80":
                gpu_string = "nvidia-tesla-k80"
                valid_gpu_type = True
            elif gpu_type.lower() == "p100":
                gpu_string = "nvidia-tesla-p100"
                valid_gpu_type = True
            elif gpu_type.lower() == "t4":
                gpu_string = "nvidia-tesla-t4"
                valid_gpu_type = True

            assert (
                valid_gpu_type
            ), "no valid gpu_type selected, only k80 and p100 are currently supported."

            config["guestAccelerators"] = [
                {
                    "acceleratorCount": gpu_count,
                    "acceleratorType": f"https://www.googleapis.com/compute/v1/projects/{self.project}/zones/{zone}/acceleratorTypes/{gpu_string}",
                }
            ]

        return config


if __name__ == "__main__":
    from pprint import pprint
    import yaml

    vmm = VMManager(project="sobolt-plantfellow")
    # md = vmm.get_metadata(name='sc-dev-vm-mheijink', zone='europe-west1-b')
    # pprint(md)

    with open("./servers/vm-manager/src/vm_configurations.yml", "r") as c:
        vmspecs = yaml.safe_load(c)

    # pprint(vmspecs['DEFAULT'])
    md = vmm.create_vm(**vmspecs["DEFAULT"][0])
    pprint(md)
