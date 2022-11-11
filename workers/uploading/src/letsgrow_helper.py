import os
import requests, json


class LetsGrowHelper:
    """ "A class to connect, read and retrieve data from the LetsGrow.com api"""

    def __init__(self):
        self.token = ""
        self.connected = False

    def login(self):
        url = "https://api.letsgrow.com:443/token"

        credentials = {
            "grant_type": "password",
            "username": str(os.getenv("LETSGROW_API_USERNAME")),
            "password": str(os.getenv("LETSGROW_API_PASSWORD")),
        }
        r = requests.post(url, data=credentials)
        resp = r.json()
        if r.status_code == 200:
            print("Logged in")
            self.token = resp["access_token"]
            self.connected = True
        else:
            print(f"Not logged in, status code: {r.status_code}, message: {r}")

    # TODO add decorator which checks if token present, retrieves token when not present
    def get_module_definitions(self):
        """Retrrieves all module definitions"""

        if self.connected:

            url = "https://api.letsgrow.com:443/api/ModuleDefinitions"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            }

            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                resp = r.json()
                return resp

    def get_module_definitions_items(self):
        """Retrieves all module definition items."""
        url = "https://api.letsgrow.com:443/api/ModuleDefinitions/Items?onlyActiveModules=true&onlyWritableItems=true&hideModulesWithoutItems=true"
        headers = {
            "Authorization": f"Bearer {self.token}"
            # 'Accept':'application/json'
        }

        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            resp = r.json()
            return resp
        else:
            print(r)
            return None

    def put_value(
        self, moduleId, colId, instanceId, name, path, section, value, timestamp
    ):
        """
        Write a value to the LetsGrow API.

        name = {Greenhouse_name}-{path}-{plant_number}
        Path = pad
        Section = plant number
        """
        url = f"https://api.letsgrow.com/api/ModuleDefinitions/{moduleId}/InstanceValues"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        # data = '{\n  "TimeStamp": "2022-09-27T10:07:19.978Z",\n  "Value": "value",\n  "Offset": 0\n}'

        json_data = json.dumps(
            [
                {
                    "InstanceId": instanceId,
                    "ColId": colId,
                    "TimeStamp": timestamp,
                    "Value": value,
                    "Offset": 0,
                }
            ]
        )
        r = requests.put(url, headers=headers, data=json_data)

        if r.status_code == 200:
            print("status 200")
            return r
        else:
            print(r)
            return None

    def get_instance(self, moduleId, instanceId):
        """Retrieves an  instance from the LetsGrow API"""
        url = f"https://api.letsgrow.com/api/ModuleDefinitions/{moduleId}/Instance/{instanceId}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            resp = r.json()
            print(resp)
            return resp
        else:
            print(r)
            return None

    def get_instances(self, moduleId):
        """Retrieves all instances for the moduleId from the LetsGrow API"""
        url = f"https://api.letsgrow.com/api/ModuleDefinitions/{moduleId}/Instances"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            resp = r.json()
            return resp

    def get_instance_by_name(self, moduleId, name):
        """Retrieves an instance by its name from the moduleId from the LetsGrow API"""
        instances = self.get_instances(moduleId)
        print(moduleId)
        print(instances)
        for instance in instances:
            if instance["Name"] == name:
                return instance
        return None

    def create_instance(self, moduleId, instanceId, name, path, section):
        """
        Creates an instance on the LetsGrow API

        name = {rc_visard_serial}-{path_number}-{plant_number}
        Path = pad
        Section = plant number
        """
        url = f"https://api.letsgrow.com/api/ModuleDefinitions/{moduleId}/Instance/{instanceId}?name={name}&path={path}&section={section}"
        headers = {
            # "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        r = requests.put(
            url,
            headers=headers,
        )

        if r.status_code == 200:
            resp = r.json()
            print(resp)
            return resp
        else:
            print(r)
            print(r.content)
            return None


if __name__ == "__main__":
    lg = LetsGrowHelper()

    lg.login()
    resp = lg.get_module_definitions_items()
    resp = lg.get_instance(moduleId=45237, instanceId=1)
