# Deployment templates

The Windows services were the bridge, TMoIP, and the log exporter. Each
becomes one Linux process. The desktop twins are not separate units. The web
app is a fourth process: it replaces the configurator and test manager, which
were VCL programs rather than services.

| Unit | Process | Role now |
| --- | --- | --- |
| `astra-bridge.service` | `astra-bridge` | UDP bridge, `.DAT` logging, test poll, and the in-process OPC UA server. Idle until the bridge is ported. |
| `astra-tmoip.service` | `astra-tmoip` | Minor-frame reassembly. Idle until phase 4. |
| `astra-exporter.service` | `astra-exporter` | `Jobs` poll and `testlog` load. Idle until phase 5. |
| `astra-web.service` | `astra-web` | FastAPI. Serves `GET /health` only. |

`astra.codec`, `astra.binlog`, `astra.db`, and `astra.opcua` are libraries.
`astra.cli` is three commands (`generate`, `device`, `tm_encoder`), not units.
The bridge does not bind its UDP port or the OPC UA endpoint yet.
`ASTRA_BRIDGE_PORT` (default 2357) and `ASTRA_STAGE_COUNT` (default 2) are
read from the environment file when those processes are ported.

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
sudo cp deploy/systemd/astra-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now astra-bridge.service astra-tmoip.service astra-exporter.service astra-web.service
```

`After=postgresql.service` orders startup when PostgreSQL is installed. It
does not pull the database in by itself.
