#!/usr/bin/env python3

import logging
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from kubernetes_wrapper import Kubernetes

log = logging.getLogger()


class K8sKeystoneAuthCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.kubernetes = Kubernetes(self.model.name)
        self.framework.observe(self.on.install, self.install)
        self.framework.observe(self.on.config_changed, self.config_changed)
        self.framework.observe(self.on.keystone_credentials_relation_joined, self.keystone_credentials_relation_changed)
        self.framework.observe(self.on.keystone_credentials_relation_changed, self.keystone_credentials_relation_changed)
        self.framework.observe(self.on.keystone_credentials_relation_broken, self.keystone_credentials_relation_changed)
        self.framework.observe(self.on.keystone_credentials_relation_departed, self.keystone_credentials_relation_changed)
        self.framework.observe(self.on.tls_certificates_relation_joined, self.tls_certificates_relation_changed)
        self.framework.observe(self.on.tls_certificates_relation_changed, self.tls_certificates_relation_changed)
        self.framework.observe(self.on.tls_certificates_relation_broken, self.tls_certificates_relation_changed)
        self.framework.observe(self.on.tls_certificates_relation_departed, self.tls_certificates_relation_changed)

    def install(self, event):
        self.kubernetes.apply_object(self.service_object)

    def config_changed(self, event):
        self.update_container()

    def keystone_credentials_relation_changed(self, event):
        for relation in self.model.relations.get('keystone-credentials', []):
            relation.data[self.unit]["username"] = "k8s-keystone-auth"

        self.update_container()

    def tls_certificates_relation_changed(self, event):
        service_ip = self.get_service_ip()

        for relation in self.model.relations.get('tls-certificates', []):
            data = relation.data[self.unit]
            data["common_name"] = service_ip
            data["sans"] = f'["{service_ip}"]'
            data["unit_name"] = self.unit.name

        self.update_container()

    @property
    def service_object(self):
        app_name = self.model.app.name
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": app_name + "-webhook",
                "namespace": self.model.name,
            },
            "spec": {
                "selector": {
                    "app.kubernetes.io/name": app_name
                },
                "ports": [{
                    "port": 8443,
                    "protocol": "TCP"
                }]
            }
        }

    def get_service_ip(self):
        k8s_api = self.kubernetes.find_k8s_api(self.service_object, None)
        service = k8s_api.read_namespaced_service(
            namespace=self.service_object['metadata']['namespace'],
            name=self.service_object['metadata']['name']
        )
        service_ip = service.spec.cluster_ip
        log.info(service_ip)
        return service_ip

    def get_server_cert(self):
        server_key = self.config["tls-server-cert"]
        if server_key:
            return server_key

        relations = self.model.relations.get('tls-certificates', [])
        for relation in relations:
            for unit in relation.units:
                data = relation.data[unit]
                key = self.unit.name.replace('/', '_') + ".server.cert"
                if key in data:
                    return data[key]

        if relations:
            self.unit.status = WaitingStatus("Waiting for tls-certificates relation")
        else:
            self.unit.status = BlockedStatus("Missing tls-certificates relation and tls-server-cert config")
        return None

    def get_server_key(self):
        server_key = self.config["tls-server-key"]
        if server_key:
            return server_key

        relations = self.model.relations.get('tls-certificates', [])
        for relation in relations:
            for unit in relation.units:
                data = relation.data[unit]
                key = self.unit.name.replace('/', '_') + ".server.key"
                if key in data:
                    return data[key]

        if relations:
            self.unit.status = WaitingStatus("Waiting for tls-certificates relation")
        else:
            self.unit.status = BlockedStatus("Missing tls-certificates relation and tls-server-key config")
        return None

    def get_keystone_url(self):
        keystone_url = self.config["keystone-url"]
        if keystone_url:
            return keystone_url

        relations = self.model.relations.get('keystone-credentials', [])
        for relation in relations:
            for unit in relation.units:
                data = relation.data[unit]
                protocol = data.get("credentials_protocol")
                host = data.get("credentials_host")
                port = data.get("credentials_port")
                api_version = data.get("api_version")
                if protocol and host and port and api_version:
                    keystone_url = f"{protocol}://{host}:{port}/v{api_version}"
                    return keystone_url

        if relations:
            self.unit.status = WaitingStatus("Waiting for keystone credentials")
        else:
            self.unit.status = BlockedStatus("Missing keystone-credentials relation and keystone-url config")
        return None

    def update_container(self):
        server_cert = self.get_server_cert()
        if not server_cert:
            return

        server_key = self.get_server_key()
        if not server_key:
            return

        keystone_url = self.get_keystone_url()
        if not keystone_url:
            return

        self.unit.status = MaintenanceStatus("Rendering config files")
        container = self.unit.get_container("k8s-keystone-auth")
        server_cert_path = "/etc/k8s-keystone-auth/server.crt"
        server_key_path = "/etc/k8s-keystone-auth/server.key"
        keystone_ca_path = "/etc/k8s-keystone-auth/ca.crt"
        policy_path = "/etc/k8s-keystone-auth/authorization-policy.json"
        keystone_ca = self.config["keystone-ca"]
        policy = self.config["authorization-policy"]
        container.push(server_cert_path, server_cert, make_dirs=True)
        container.push(server_key_path, server_key, make_dirs=True)
        container.push(keystone_ca_path, keystone_ca, make_dirs=True)
        container.push(policy_path, policy, make_dirs=True)

        self.unit.status = MaintenanceStatus("Configuring container")
        command = "./bin/k8s-keystone-auth" \
            + " --keystone-url " + keystone_url \
            + " --tls-private-key-file " + server_key_path \
            + " --tls-cert-file " + server_cert_path \
            + " --keystone-policy-file " + policy_path
        if keystone_ca:
            command += " --keystone-ca-file" + keystone_ca_path
        layer = {
            "summary": "k8s-keystone-auth layer",
            "description": "k8s-keystone-auth layer",
            "services": {
                "k8s-keystone-auth": {
                    "override": "replace",
                    "summary": "k8s-keystone-auth",
                    "command": command,
                    "startup": "enabled",
                    "environment": {}
                }
            }
        }
        container.add_layer("k8s-keystone-auth", layer, combine=True)

        self.unit.status = MaintenanceStatus("Restarting container")
        if container.get_service("k8s-keystone-auth").is_running():
            container.stop("k8s-keystone-auth")
        container.start("k8s-keystone-auth")

        self.unit.status = ActiveStatus()


if __name__ == '__main__':
    main(K8sKeystoneAuthCharm)
