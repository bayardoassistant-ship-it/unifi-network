# UniFi Network Plugin (`unifi-network`)

Manage and monitor **Ubiquiti UniFi Network** consoles, sites, adopted devices (Gateways, Switches, Access Points), connected clients, VLAN networks, WiFi broadcasts (SSIDs), hotspot vouchers, firewall zones/policies, ACL rules, and DNS policies via the official **UniFi Network Integration API v1**.

## Features

- **26 Purpose-Built MCP Tools** covering the official UniFi Network Integration API v1 (`/proxy/network/integration/v1/...`), plus a generic `unifi_raw_request` tool for every endpoint in the OpenAPI 3.1 specification.
- **Zero-Config Cloud Connector by Default (`UNIFI_MODE=cloud`)**:
  - **Ubiquiti Cloud Connector (`api.ui.com`)**: Connects via `https://api.ui.com/v1/connector/consoles/{consoleId}/proxy/network/integration/v1/...`. If `UNIFI_CONSOLE_ID` is omitted, the server automatically discovers your Console ID via `GET https://api.ui.com/v1/hosts` using your `UNIFI_API_KEY` and caches it in memory—so you only need `UNIFI_API_KEY` from [unifi.ui.com](https://unifi.ui.com)!
  - **Local Console Gateway (`UNIFI_MODE=local` or `auto`)**: Connects directly to `https://192.168.1.1/proxy/network/integration/v1/...` (or any custom local IP / Tailscale / Cloudflare Tunnel URL in `UNIFI_BASE_URL`) with self-signed TLS verification disabled (`-k` / `UNIFI_VERIFY_SSL=false`).
- **Zero External Python Dependencies**: Uses Python 3's standard library (`urllib.request`, `ssl`, `json`) for instant startup (<100ms) and zero virtual-environment fragility.

## Setup & Configuration Variables

1. **Generate an API Key**:
   - **Ubiquiti Site Manager Cloud API Key (Recommended for Cloud/Grok Bot)**: Open [unifi.ui.com](https://unifi.ui.com) → **API Keys** to create a cloud key for `https://api.ui.com`.
   - **Local Console Integration API Key**: Open your UniFi Console (`https://192.168.1.1` or `https://unifi.ui.com`) and navigate to **Settings → Control Plane → Integrations**, then create a local API key.
2. **Configure Plugin Variables**:
   - `UNIFI_API_KEY` *(required)*: Your `X-API-KEY` token.
   - `UNIFI_CONSOLE_ID` *(optional)*: Your console ID from `https://unifi.ui.com/consoles/<CONSOLE_ID>/...`. If omitted, it is automatically discovered from `GET https://api.ui.com/v1/hosts`.
   - `UNIFI_BASE_URL` *(optional, default `https://192.168.1.1`)*: Your local UniFi console URL or tunnel URL (used when `UNIFI_MODE=local` or `auto`).

### Equivalent `curl` Tests

**Cloud Connector (`api.ui.com`):**
```bash
curl -X GET 'https://api.ui.com/v1/connector/consoles/YOUR_CONSOLE_ID/proxy/network/integration/v1/sites' \
  -H 'X-API-KEY: YOUR_API_KEY' \
  -H 'Accept: application/json'
```

**Local Console (`192.168.1.1`):**
```bash
curl -k -X GET 'https://192.168.1.1/proxy/network/integration/v1/sites' \
  -H 'X-API-KEY: YOUR_API_KEY' \
  -H 'Accept: application/json'
```

## Available MCP Tools

| Tool | Endpoint | Description |
|---|---|---|
| `unifi_get_info` | `GET /v1/info` | Get UniFi Network application version and runtime info |
| `unifi_list_sites` | `GET /v1/sites` | List sites configured on the UniFi console |
| `unifi_list_devices` | `GET /v1/sites/{siteId}/devices` | List adopted devices (APs, switches, gateways) |
| `unifi_get_device` | `GET /v1/sites/{siteId}/devices/{deviceId}` | Get detailed device configuration, ports, radios, and uplink |
| `unifi_get_device_statistics` | `GET /v1/sites/{siteId}/devices/{deviceId}/statistics/latest` | Get real-time CPU, RAM, uptime, and tx/rx telemetry |
| `unifi_list_pending_devices` | `GET /v1/pending-devices` | List discovered devices pending adoption |
| `unifi_device_action` | `POST /v1/sites/{siteId}/devices/{deviceId}/actions` | Restart an adopted UniFi device (`RESTART`) |
| `unifi_port_action` | `POST .../interfaces/ports/{portIdx}/actions` | Power-cycle PoE on a switch port (`POWER_CYCLE`) |
| `unifi_list_clients` | `GET /v1/sites/{siteId}/clients` | List connected wired and wireless clients |
| `unifi_get_client` | `GET /v1/sites/{siteId}/clients/{clientId}` | Get detailed information for a connected client |
| `unifi_client_action` | `POST /v1/sites/{siteId}/clients/{clientId}/actions` | Authorize or unauthorize guest portal access |
| `unifi_list_networks` | `GET /v1/sites/{siteId}/networks` | List networks and VLANs on a site |
| `unifi_get_network` | `GET /v1/sites/{siteId}/networks/{networkId}` | Get details for a specific network/VLAN |
| `unifi_list_wifi_broadcasts` | `GET /v1/sites/{siteId}/wifi/broadcasts` | List WiFi SSIDs/broadcasts |
| `unifi_get_wifi_broadcast` | `GET /v1/sites/{siteId}/wifi/broadcasts/{wifiBroadcastId}` | Get details for a specific WiFi SSID |
| `unifi_list_vouchers` | `GET /v1/sites/{siteId}/hotspot/vouchers` | List guest hotspot vouchers |
| `unifi_create_vouchers` | `POST /v1/sites/{siteId}/hotspot/vouchers` | Create new guest hotspot vouchers |
| `unifi_delete_voucher` | `DELETE /v1/sites/{siteId}/hotspot/vouchers/{voucherId}` | Delete a guest hotspot voucher |
| `unifi_list_firewall_zones` | `GET /v1/sites/{siteId}/firewall/zones` | List firewall zones |
| `unifi_list_firewall_policies` | `GET /v1/sites/{siteId}/firewall/policies` | List firewall policies |
| `unifi_list_acl_rules` | `GET /v1/sites/{siteId}/acl-rules` | List ACL rules |
| `unifi_list_dns_policies` | `GET /v1/sites/{siteId}/dns/policies` | List DNS policies |
| `unifi_list_traffic_matching_lists` | `GET /v1/sites/{siteId}/traffic-matching-lists` | List port and IP traffic matching lists |
| `unifi_list_wans` | `GET /v1/sites/{siteId}/wans` | List WAN interfaces |
| `unifi_cloud_list_hosts` | `GET https://api.ui.com/v1/hosts` | List all UniFi consoles via Ubiquiti Site Manager API |
| `unifi_raw_request` | `ANY /v1/...` | Call any UniFi Network Integration API v1 endpoint directly |

## License

MIT
