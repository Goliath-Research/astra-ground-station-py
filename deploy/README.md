# Deployment templates

Three long-running services, all idle placeholders until the port fills them
in:

| Unit | Process | Role |
| --- | --- | --- |
| `astra-bridge.service` | `astra-bridge` | OPC UA server (asyncua) that replaces OPC DA and NI shared variables. LabVIEW subscribes to the tags it will publish. |
| `astra-telemetry.service` | `astra-telemetry` | Telemetry decoder and encoder. |
| `astra-web.service` | `astra-web` | Operator web UI. No HTTP framework is selected yet. |

The codec, exporter, and database access layer are libraries used by those
processes, not separate units. The bridge placeholder does not bind
`ASTRA_OPCUA_ENDPOINT`. Telemetry does not decode. The web process does not
listen.

## Host layout

- Checkout or install tree: `/opt/astra-ground-station`
- Virtualenv with this package installed: `/opt/astra-ground-station/.venv`
- Environment file: `/etc/astra/astra.env` (see `astra.env.example`)
- State directory: `/var/lib/astra`
- System user: `astra`, created from `sysusers.d/astra.conf`

```bash
sudo systemd-sysusers deploy/sysusers.d/astra.conf
sudo install -d -o astra -g astra /var/lib/astra /etc/astra
sudo install -m 0640 -o root -g astra deploy/astra.env.example /etc/astra/astra.env
sudoedit /etc/astra/astra.env
sudo cp deploy/systemd/astra-bridge.service /etc/systemd/system/
sudo cp deploy/systemd/astra-telemetry.service /etc/systemd/system/
sudo cp deploy/systemd/astra-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now astra-bridge.service astra-telemetry.service astra-web.service
```

`ExecStart` expects an editable or regular install in the virtualenv so the
console scripts exist. `After=postgresql.service` orders startup when
PostgreSQL is installed; it does not pull the database in by itself.
