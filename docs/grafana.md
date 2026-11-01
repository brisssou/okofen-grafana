# Start Grafana

Grafana runs in a Podman pod defined by `okofen.yaml`. Start commands from the
repository root so the relative host-volume paths resolve correctly.

## Start

Import data first so `data/okofen.sqlite3` exists, then create and start the
Grafana pod:

```sh
podman play kube okofen.yaml
```

Open [http://localhost:3000](http://localhost:3000). The configured local
credentials are `admin` / `grafana`. The dashboard is provisioned from the
repository and uses the SQLite database at `data/okofen.sqlite3`.

## Restart and stop

To restart the pod using the current configuration:

```sh
bash pods.sh
```

This helper stops and removes the `okofen` pod, then recreates it from
`okofen.yaml`. It does not remove the host data directory or SQLite database.
To stop Grafana without recreating it:

```sh
podman pod stop okofen
```

To check pod status:

```sh
podman pod ps
```

If Grafana does not start, inspect the container with `podman ps --pod`, then
read its logs with `podman logs <container-id>`.

## Security note

The current configuration enables anonymous access and uses the default
`admin` / `grafana` credentials. Keep this setup on a trusted local machine.
Before exposing Grafana to other machines or an untrusted network, disable
anonymous access and change the administrator credentials in
`grafana/config/grafana.ini`; also review the port binding in `okofen.yaml`.
