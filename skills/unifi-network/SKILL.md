---
name: unifi-network
description: >-
  Manage and monitor Ubiquiti UniFi Network consoles, sites, adopted devices,
  connected clients, VLAN networks, WiFi broadcasts, hotspot vouchers, firewall
  zones/policies, ACL rules, and DNS policies using the official UniFi Network
  Integration API v1 MCP tools.
---

# UniFi Network Integration API v1 Skill

Use the `unifi-network` MCP tools whenever the user asks to inspect, monitor, or manage their Ubiquiti UniFi Network infrastructure (Gateways, Dream Machines, Cloud Keys, Switches, Access Points, WiFi SSIDs, VLANs, clients, guest vouchers, or firewall rules).

## Connection & Reachability Modes

The `unifi-network` MCP server wraps the official **UniFi Network Integration API v1** (`/proxy/network/integration/v1/...`) and supports two official base URLs:

1. **Ubiquiti Cloud Connector Mode (`UNIFI_MODE=cloud`, default)**
   - Proxies the official UniFi Network Integration API v1 endpoints through Ubiquiti's Cloud Site Manager (`https://api.ui.com/v1/connector/consoles/{consoleId}/proxy/network/integration/v1/...`) using `X-API-KEY`.
   - If `UNIFI_CONSOLE_ID` is not set, the server automatically discovers the first console's `id` via `GET https://api.ui.com/v1/hosts` and caches it in memory—so users only need to supply `UNIFI_API_KEY`.

2. **Local Gateway Mode (`UNIFI_MODE=local` or `auto`, `https://192.168.1.1/proxy/network/integration/v1/...`)**
   - Authenticates with `X-API-KEY` generated in **UniFi OS → Settings → Control Plane → Integrations**.
   - Automatically skips self-signed certificate verification (`UNIFI_VERIFY_SSL=false`, equivalent to `curl -k`).
   - When running in a cloud environment where `192.168.1.1` is on a private home LAN, use Cloud Connector mode (`UNIFI_MODE=cloud`) or set `UNIFI_BASE_URL` to a tunnel endpoint (Tailscale / Cloudflare Tunnel).

## Workflow & Core Tools

1. **Discover Application Info & Site ID First**
   - Call `unifi_list_sites` first to retrieve the `siteId` (UUID) required by all site-scoped endpoints.
   - Call `unifi_get_info` to check the UniFi Network application version.
   - Call `unifi_cloud_list_hosts` to list all consoles registered under the user's Ubiquiti Site Manager account (`GET https://api.ui.com/v1/hosts`).

2. **Inspect & Manage UniFi Devices (Gateways, Switches, APs)**
   - `unifi_list_devices` (`siteId`): List all adopted UniFi devices on the site.
   - `unifi_get_device` (`siteId`, `deviceId`): Get full hardware, firmware, radio, port, and uplink details for a device.
   - `unifi_get_device_statistics` (`siteId`, `deviceId`): Fetch latest real-time CPU, memory, uptime, and throughput telemetry.
   - `unifi_list_pending_devices`: List un-adopted devices discovered on the network.
   - `unifi_device_action` (`siteId`, `deviceId`, `action="RESTART"`): Reboot an adopted device (confirm with the user before restarting production network hardware).
   - `unifi_port_action` (`siteId`, `deviceId`, `portIdx`, `action="POWER_CYCLE"`): Power-cycle PoE on a specific switch port.

3. **Monitor & Authorize Clients**
   - `unifi_list_clients` (`siteId`, optional `filter`, `limit`, `offset`): List wired and wireless clients connected to the site.
   - `unifi_get_client` (`siteId`, `clientId`): Inspect a specific client's IP, MAC, connection type, and signal/uptime.
   - `unifi_client_action` (`siteId`, `clientId`, `action="AUTHORIZE_GUEST_ACCESS"` or `"UNAUTHORIZE_GUEST_ACCESS"`): Grant or revoke guest portal access.

4. **Networks (VLANs), WiFi Broadcasts (SSIDs) & Hotspot Vouchers**
   - `unifi_list_networks` / `unifi_get_network`: Inspect configured VLANs, subnets, and DHCP settings.
   - `unifi_list_wifi_broadcasts` / `unifi_get_wifi_broadcast`: Inspect WiFi SSIDs, security modes, and band configuration.
   - `unifi_list_vouchers` / `unifi_create_vouchers` / `unifi_delete_voucher`: List, generate, or revoke guest hotspot vouchers.

5. **Security, Firewall, ACLs & DNS**
   - `unifi_list_firewall_zones` / `unifi_list_firewall_policies`: Audit zone-based firewall rules and ordering.
   - `unifi_list_acl_rules`: Inspect switch/network ACL rules.
   - `unifi_list_dns_policies`: Inspect custom local DNS records and policies.
   - `unifi_list_traffic_matching_lists`: Inspect port and IP group lists.
   - `unifi_list_wans`: List WAN uplink interfaces.

6. **Full API Escape Hatch (`unifi_raw_request`)**
   - Use `unifi_raw_request` (`path`, `method`, `params`, `body`) for any additional endpoint in the UniFi Network Integration API v1 OpenAPI specification (such as `/v1/sites/{siteId}/switching/lags`, `/v1/sites/{siteId}/switching/switch-stacks`, `/v1/dpi/applications`, `/v1/sites/{siteId}/vpn/site-to-site-tunnels`, or creating/updating networks, WiFi broadcasts, and firewall policies).
