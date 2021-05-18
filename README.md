# k8s-keystone-auth-operator

This operator deploys k8s-keystone-auth, a service that makes it possible to
integrate Kubernetes with Keystone for authentication and authorization.

## Getting started

Start by deploying k8s-keystone-auth into a Kubernetes model:

```
juju deploy ch:k8s-keystone-auth --trust
```

Relate k8s-keystone-auth to a Certificate Authority (e.g. easyrsa, vault):

```
juju offer -m my-ca-model easyrsa:client
juju relate k8s-keystone-auth admin/my-ca-model.easyrsa
```

Relate k8s-keystone-auth to Keystone:

```
juju offer -m my-keystone-model keystone:identity-credentials
juju relate k8s-keystone-auth admin/my-keystone-model.keystone
```

Obtain the k8s-keystone-auth-webhook service IP:
```
kubectl get svc -n my-k8s-keystone-auth-model k8s-keystone-auth-webhook
```

Create a kubeconfig that points to the k8s-keystone-auth-webhook service IP:
```
apiVersion: v1
kind: Config
preferences: {}
clusters:
  - cluster:
      server: https://$SERVICE_IP:8443/webhook
      insecure-skip-tls-verify: true
    name: webhook
users:
  - name: webhook
contexts:
  - context:
      cluster: webhook
      user: webhook
    name: webhook
current-context: webhook
```

Then configure kube-apiserver to use it, with:
```
--authentication-token-webhook-config-file /path/to/auth/kubeconfig
--authorization-mode Node,RBAC,Webhook
--authorization-webhook-config-file /path/to/auth/kubeconfig
```

## Config options

### authorization-policy
Authorization policy for Keystone.

Optional.

Example configuration:
```
[
  {
   "resource": {
      "verbs": ["get", "list", "watch"],
      "resources": ["*"],
      "version": "*",
      "namespace": "*"
    },
    "match": [
      {
        "type": "role",
        "values": ["k8s-viewers"]
      },
      {
        "type": "project",
        "values": ["k8s"]
      }
    ]
  },
  {
   "resource": {
      "verbs": ["*"],
      "resources": ["*"],
      "version": "*",
      "namespace": "default"
    },
    "match": [
      {
        "type": "role",
        "values": ["k8s-users"]
      },
      {
        "type": "project",
        "values": ["k8s"]
      }
    ]
  },
  {
   "resource": {
      "verbs": ["*"],
      "resources": ["*"],
      "version": "*",
      "namespace": "*"
    },
    "match": [
      {
        "type": "role",
        "values": ["k8s-admins"]
      },
      {
        "type": "project",
        "values": ["k8s"]
      }
    ]
  }
]
```


### keystone-ca
TLS certificate for Keystone's Certificate Authority, used to verify the
connection to Keystone.

Optional.

### keystone-url
URL for Keystone.

Required. If related to Keystone, this becomes optional.

### tls-server-cert
TLS server certificate to use for the webhook endpoint.

Required. If related to a certificate authority, this becomes optional.

### tls-server-key
TLS server key to use for the webhook endpoint.

Required. If related to a certificate authority, this becomes optional.

## Supported relations

### keystone-credentials
Interface: keystone-credentials

For relating to Keystone. Used to obtain the Keystone URL and CA.

### tls-certificates
Interface: tls-certificates

For relating to EasyRSA or Vault, to obtain a TLS server key/cert pair.

## Roadmap to charm completion

Here's what is needed before this charm could be considered feature-complete
and production ready:

1. Add a k8s-keystone-auth-webhook relation to kubernetes-master, to simplify
the configuration of kube-apiserver.
2. Add charm config: sync-config, used to configure k8s-keystone-auth to sync
data between Keystone and Kubernetes.
3. Add integration tests with pytest-operator for maintainability.
