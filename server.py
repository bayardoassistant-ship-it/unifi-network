#!/usr/bin/env python3
"""
UniFi Network Integration API v1 — MCP Server (stdio)
Supports both:
  1. Local Console API: https://192.168.1.1/proxy/network/integration/v1/... (curl -k / self-signed TLS)
  2. Ubiquiti Cloud Connector Proxy:
     - https://api.ui.com/v1/connector/consoles/{consoleId}/proxy/network/integration/v1/...
     - https://api.ui.com/v1/connector/consoles/{consoleId}/network/integration/v1/...
"""

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

DEFAULT_CONSOLE_ID = ""
DEFAULT_BASE_URL = "https://192.168.1.1"
ENV_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
_CACHED_CONSOLE_ID: Optional[str] = None


def _clean_env_val(val: Optional[str]) -> str:
    if not val:
        return ""
    v = val.strip()
    if v.startswith("${") and v.endswith("}"):
        return ""
    return v


def load_dotenv_if_present() -> None:
    for env_path in ("/home/box/.unifi.env", ENV_FILE_PATH):
        if not os.path.exists(env_path):
            continue
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    if k and _clean_env_val(v):
                        os.environ[k] = _clean_env_val(v)
        except Exception:
            pass


def get_config() -> Dict[str, Any]:
    load_dotenv_if_present()
    api_key = (
        _clean_env_val(os.environ.get("UNIFI_API_KEY"))
        or _clean_env_val(os.environ.get("X_API_KEY"))
    )
    base_url = (_clean_env_val(os.environ.get("UNIFI_BASE_URL")) or DEFAULT_BASE_URL).rstrip("/")
    console_id = _clean_env_val(os.environ.get("UNIFI_CONSOLE_ID")) or DEFAULT_CONSOLE_ID
    mode = (_clean_env_val(os.environ.get("UNIFI_MODE")) or "cloud").lower()
    verify_ssl_str = (_clean_env_val(os.environ.get("UNIFI_VERIFY_SSL")) or "false").lower()
    verify_ssl = verify_ssl_str in ("1", "true", "yes")
    timeout_str = _clean_env_val(os.environ.get("UNIFI_TIMEOUT")) or "25"
    try:
        timeout = float(timeout_str)
    except ValueError:
        timeout = 25.0
    return {
        "api_key": api_key,
        "base_url": base_url,
        "console_id": console_id,
        "mode": mode,
        "verify_ssl": verify_ssl,
        "timeout": timeout,
    }


def normalize_integration_base(base_url: str) -> str:
    """
    Ensure base_url ends with /proxy/network/integration (without trailing /v1),
    so appending /v1/... produces the exact UniFi Network Integration API path:
      https://192.168.1.1/proxy/network/integration/v1/sites
    """
    b = base_url.rstrip("/")
    if b.endswith("/proxy/network/integration/v1"):
        return b[:-3]
    if b.endswith("/network/integration/v1"):
        return b[:-3]
    if b.endswith("/proxy/network/integration") or b.endswith("/network/integration"):
        return b
    return f"{b}/proxy/network/integration"


def build_ssl_context(verify_ssl: bool) -> ssl.SSLContext:
    if verify_ssl:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def http_json_request(
    url: str,
    method: str,
    api_key: str,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    verify_ssl: bool = False,
    timeout: float = 8.0,
) -> Tuple[int, Any]:
    if params:
        clean_params = {k: v for k, v in params.items() if v is not None and v != ""}
        if clean_params:
            qs = urllib.parse.urlencode(clean_params)
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{qs}"

    headers = {
        "Accept": "application/json",
        "X-API-KEY": api_key,
        "User-Agent": "unifi-network-mcp/1.0",
    }
    data_bytes = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url=url, data=data_bytes, headers=headers, method=method.upper())
    ctx = build_ssl_context(verify_ssl)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.getcode()
            if not raw:
                return status, {"status": "ok", "httpStatusCode": status}
            try:
                return status, json.loads(raw)
            except Exception:
                return status, {"raw": raw, "httpStatusCode": status}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            parsed = json.loads(raw) if raw else {"message": str(e)}
        except Exception:
            parsed = {"message": raw or str(e)}
        return e.code, parsed


def discover_console_id(api_key: str, timeout: float = 15.0) -> str:
    global _CACHED_CONSOLE_ID
    if _CACHED_CONSOLE_ID:
        return _CACHED_CONSOLE_ID
    status, data = http_json_request(
        "https://api.ui.com/v1/hosts", "GET", api_key, verify_ssl=True, timeout=timeout
    )
    if status == 200 and isinstance(data, dict):
        hosts = data.get("data") or []
        if isinstance(hosts, list):
            for h in hosts:
                if isinstance(h, dict) and h.get("id") and h.get("type") == "console":
                    _CACHED_CONSOLE_ID = str(h["id"]).strip()
                    return _CACHED_CONSOLE_ID
            for h in hosts:
                if isinstance(h, dict) and h.get("id"):
                    _CACHED_CONSOLE_ID = str(h["id"]).strip()
                    return _CACHED_CONSOLE_ID
    return ""


def call_cloud_connector(
    console_id: str,
    path: str,
    method: str,
    api_key: str,
    params: Optional[Dict[str, Any]],
    body: Optional[Dict[str, Any]],
    timeout: float,
) -> Tuple[str, int, Any]:
    resolved_id = (console_id or "").strip() or discover_console_id(api_key, timeout=timeout)
    if not resolved_id:
        return (
            "https://api.ui.com/v1/hosts",
            404,
            {"error": "Could not auto-discover UniFi Console ID from https://api.ui.com/v1/hosts. Set UNIFI_CONSOLE_ID or verify UNIFI_API_KEY."},
        )
    url_proxy = f"https://api.ui.com/v1/connector/consoles/{resolved_id}/proxy/network/integration{path}"
    status, data = http_json_request(
        url_proxy, method, api_key, params=params, body=body, verify_ssl=True, timeout=timeout
    )
    if status == 404:
        url_direct = f"https://api.ui.com/v1/connector/consoles/{resolved_id}/network/integration{path}"
        status2, data2 = http_json_request(
            url_direct, method, api_key, params=params, body=body, verify_ssl=True, timeout=timeout
        )
        if status2 != 404:
            return url_direct, status2, data2
    return url_proxy, status, data


def unifi_request(
    path: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = get_config()
    api_key = cfg["api_key"]
    if not api_key:
        return {
            "error": "Missing UNIFI_API_KEY. Set UNIFI_API_KEY in the MCP server environment or in /home/box/mcp/unifi-network/.env."
        }

    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith("/v1/"):
        path = "/v1" + path

    mode = cfg["mode"]
    local_base = normalize_integration_base(cfg["base_url"])
    local_url = f"{local_base}{path}"

    if mode == "cloud":
        c_url, status, data = call_cloud_connector(
            cfg["console_id"], path, method, api_key, params, body, cfg["timeout"]
        )
        return {"endpoint": c_url, "httpStatusCode": status, "response": data}

    if mode == "local":
        status, data = http_json_request(
            local_url, method, api_key, params=params, body=body, verify_ssl=cfg["verify_ssl"], timeout=cfg["timeout"]
        )
        return {"endpoint": local_url, "httpStatusCode": status, "response": data}

    # mode == "auto": try configured UNIFI_BASE_URL first; if unreachable from cloud box, try Cloud Connector
    try:
        status, data = http_json_request(
            local_url,
            method,
            api_key,
            params=params,
            body=body,
            verify_ssl=cfg["verify_ssl"],
            timeout=min(cfg["timeout"], 3.5),
        )
        return {"endpoint": local_url, "httpStatusCode": status, "response": data}
    except Exception as local_err:
        try:
            c_url, status, data = call_cloud_connector(
                cfg["console_id"], path, method, api_key, params, body, cfg["timeout"]
            )
            if status == 401:
                return {
                    "error": "Local console URL was unreachable from the cloud box, and Ubiquiti Cloud Connector returned 401 Unauthorized.",
                    "localUrlTried": local_url,
                    "localError": str(local_err),
                    "cloudConnectorUrlTried": c_url,
                    "cloudResponse": data,
                    "hint": (
                        "192.168.1.1 is a private LAN IP not directly routable from the cloud box unless bridged via a tunnel "
                        "(Tailscale / Cloudflare Tunnel) or queried via Ubiquiti's Cloud Connector (api.ui.com) with a Site Manager API key."
                    ),
                }
            return {"endpoint": c_url, "httpStatusCode": status, "response": data}
        except Exception as cloud_err:
            return {
                "error": "Both local console URL and Cloud Connector URL failed.",
                "localUrlTried": local_url,
                "localError": str(local_err),
                "cloudError": str(cloud_err),
            }


TOOLS = [
    {
        "name": "unifi_get_info",
        "description": "Get UniFi Network application version and runtime details (GET /proxy/network/integration/v1/info).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "unifi_list_sites",
        "description": "List local sites configured on the UniFi Network console (GET /proxy/network/integration/v1/sites).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "offset": {"type": "integer", "description": "Pagination offset (default 0)"},
                "limit": {"type": "integer", "description": "Max items to return (default 25, max 200)"},
                "filter": {"type": "string", "description": "Optional UniFi filter expression"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_devices",
        "description": "List adopted UniFi devices (APs, switches, gateways) on a site (GET /v1/sites/{siteId}/devices).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string", "description": "Site UUID from unifi_list_sites"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "filter": {"type": "string"},
            },
            "required": ["siteId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_get_device",
        "description": "Get full details of a specific adopted UniFi device (GET /v1/sites/{siteId}/devices/{deviceId}).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "deviceId": {"type": "string"},
            },
            "required": ["siteId", "deviceId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_get_device_statistics",
        "description": "Get latest real-time telemetry (CPU, memory, uptime, tx/rx rates) for a UniFi device (GET /v1/sites/{siteId}/devices/{deviceId}/statistics/latest).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "deviceId": {"type": "string"},
            },
            "required": ["siteId", "deviceId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_pending_devices",
        "description": "List devices discovered on the network pending adoption (GET /v1/pending-devices).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "filter": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_device_action",
        "description": "Execute an action on an adopted device, such as RESTART (POST /v1/sites/{siteId}/devices/{deviceId}/actions).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "deviceId": {"type": "string"},
                "action": {"type": "string", "enum": ["RESTART"], "default": "RESTART"},
            },
            "required": ["siteId", "deviceId", "action"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_port_action",
        "description": "Execute an action on a switch port, such as POWER_CYCLE PoE (POST /v1/sites/{siteId}/devices/{deviceId}/interfaces/ports/{portIdx}/actions).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "deviceId": {"type": "string"},
                "portIdx": {"type": "integer"},
                "action": {"type": "string", "enum": ["POWER_CYCLE"], "default": "POWER_CYCLE"},
            },
            "required": ["siteId", "deviceId", "portIdx", "action"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_clients",
        "description": "List connected wired and wireless network clients on a site (GET /v1/sites/{siteId}/clients).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "filter": {"type": "string"},
            },
            "required": ["siteId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_get_client",
        "description": "Get details of a specific connected client (GET /v1/sites/{siteId}/clients/{clientId}).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "clientId": {"type": "string"},
            },
            "required": ["siteId", "clientId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_client_action",
        "description": "Authorize or unauthorize guest access for a client (POST /v1/sites/{siteId}/clients/{clientId}/actions).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "clientId": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["AUTHORIZE_GUEST_ACCESS", "UNAUTHORIZE_GUEST_ACCESS"],
                },
                "timeLimitMinutes": {"type": "integer"},
                "dataUsageLimitMBytes": {"type": "integer"},
                "rxRateLimitKbps": {"type": "integer"},
                "txRateLimitKbps": {"type": "integer"},
            },
            "required": ["siteId", "clientId", "action"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_networks",
        "description": "List networks/VLANs on a site (GET /v1/sites/{siteId}/networks).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "filter": {"type": "string"},
            },
            "required": ["siteId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_get_network",
        "description": "Get details of a specific network/VLAN (GET /v1/sites/{siteId}/networks/{networkId}).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "networkId": {"type": "string"},
            },
            "required": ["siteId", "networkId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_wifi_broadcasts",
        "description": "List WiFi SSIDs/broadcasts on a site (GET /v1/sites/{siteId}/wifi/broadcasts).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "filter": {"type": "string"},
            },
            "required": ["siteId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_get_wifi_broadcast",
        "description": "Get details of a specific WiFi broadcast/SSID (GET /v1/sites/{siteId}/wifi/broadcasts/{wifiBroadcastId}).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "wifiBroadcastId": {"type": "string"},
            },
            "required": ["siteId", "wifiBroadcastId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_vouchers",
        "description": "List hotspot guest vouchers on a site (GET /v1/sites/{siteId}/hotspot/vouchers).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "filter": {"type": "string"},
            },
            "required": ["siteId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_create_vouchers",
        "description": "Generate hotspot guest vouchers (POST /v1/sites/{siteId}/hotspot/vouchers).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "name": {"type": "string"},
                "timeLimitMinutes": {"type": "integer"},
                "count": {"type": "integer", "default": 1},
                "authorizedGuestLimit": {"type": "integer"},
                "dataUsageLimitMBytes": {"type": "integer"},
                "rxRateLimitKbps": {"type": "integer"},
                "txRateLimitKbps": {"type": "integer"},
            },
            "required": ["siteId", "name", "timeLimitMinutes"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_delete_voucher",
        "description": "Delete a specific hotspot voucher (DELETE /v1/sites/{siteId}/hotspot/vouchers/{voucherId}).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "voucherId": {"type": "string"},
            },
            "required": ["siteId", "voucherId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_firewall_zones",
        "description": "List firewall zones on a site (GET /v1/sites/{siteId}/firewall/zones).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "filter": {"type": "string"},
            },
            "required": ["siteId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_firewall_policies",
        "description": "List firewall policies on a site (GET /v1/sites/{siteId}/firewall/policies).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "filter": {"type": "string"},
            },
            "required": ["siteId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_acl_rules",
        "description": "List ACL rules on a site (GET /v1/sites/{siteId}/acl-rules).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "filter": {"type": "string"},
            },
            "required": ["siteId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_dns_policies",
        "description": "List DNS policies on a site (GET /v1/sites/{siteId}/dns/policies).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "filter": {"type": "string"},
            },
            "required": ["siteId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_traffic_matching_lists",
        "description": "List port and IP traffic matching lists on a site (GET /v1/sites/{siteId}/traffic-matching-lists).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "filter": {"type": "string"},
            },
            "required": ["siteId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_list_wans",
        "description": "List WAN interfaces on a site (GET /v1/sites/{siteId}/wans).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "siteId": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "required": ["siteId"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unifi_cloud_list_hosts",
        "description": "List all UniFi consoles/hosts via Ubiquiti Cloud Site Manager API (GET https://api.ui.com/v1/hosts).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "unifi_raw_request",
        "description": "Call any UniFi Network Integration API v1 endpoint directly (e.g. path='/v1/sites/{siteId}/switching/lags', method='GET').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "API path starting with /v1/... (e.g. /v1/sites)"},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "default": "GET",
                },
                "params": {"type": "object", "description": "Optional query parameters"},
                "body": {"type": "object", "description": "Optional JSON request body"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
]


def dispatch_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    p = lambda keys: {k: args.get(k) for k in keys if k in args}
    if name == "unifi_get_info":
        return unifi_request("/v1/info")
    if name == "unifi_list_sites":
        return unifi_request("/v1/sites", params=p(["offset", "limit", "filter"]))
    if name == "unifi_list_devices":
        return unifi_request(f"/v1/sites/{args['siteId']}/devices", params=p(["offset", "limit", "filter"]))
    if name == "unifi_get_device":
        return unifi_request(f"/v1/sites/{args['siteId']}/devices/{args['deviceId']}")
    if name == "unifi_get_device_statistics":
        return unifi_request(f"/v1/sites/{args['siteId']}/devices/{args['deviceId']}/statistics/latest")
    if name == "unifi_list_pending_devices":
        return unifi_request("/v1/pending-devices", params=p(["offset", "limit", "filter"]))
    if name == "unifi_device_action":
        return unifi_request(
            f"/v1/sites/{args['siteId']}/devices/{args['deviceId']}/actions",
            method="POST",
            body={"action": args.get("action", "RESTART")},
        )
    if name == "unifi_port_action":
        return unifi_request(
            f"/v1/sites/{args['siteId']}/devices/{args['deviceId']}/interfaces/ports/{args['portIdx']}/actions",
            method="POST",
            body={"action": args.get("action", "POWER_CYCLE")},
        )
    if name == "unifi_list_clients":
        return unifi_request(f"/v1/sites/{args['siteId']}/clients", params=p(["offset", "limit", "filter"]))
    if name == "unifi_get_client":
        return unifi_request(f"/v1/sites/{args['siteId']}/clients/{args['clientId']}")
    if name == "unifi_client_action":
        body = {"action": args["action"]}
        for k in ("timeLimitMinutes", "dataUsageLimitMBytes", "rxRateLimitKbps", "txRateLimitKbps"):
            if args.get(k) is not None:
                body[k] = args[k]
        return unifi_request(
            f"/v1/sites/{args['siteId']}/clients/{args['clientId']}/actions",
            method="POST",
            body=body,
        )
    if name == "unifi_list_networks":
        return unifi_request(f"/v1/sites/{args['siteId']}/networks", params=p(["offset", "limit", "filter"]))
    if name == "unifi_get_network":
        return unifi_request(f"/v1/sites/{args['siteId']}/networks/{args['networkId']}")
    if name == "unifi_list_wifi_broadcasts":
        return unifi_request(f"/v1/sites/{args['siteId']}/wifi/broadcasts", params=p(["offset", "limit", "filter"]))
    if name == "unifi_get_wifi_broadcast":
        return unifi_request(f"/v1/sites/{args['siteId']}/wifi/broadcasts/{args['wifiBroadcastId']}")
    if name == "unifi_list_vouchers":
        return unifi_request(f"/v1/sites/{args['siteId']}/hotspot/vouchers", params=p(["offset", "limit", "filter"]))
    if name == "unifi_create_vouchers":
        body = {
            "name": args["name"],
            "timeLimitMinutes": args["timeLimitMinutes"],
        }
        for k in ("count", "authorizedGuestLimit", "dataUsageLimitMBytes", "rxRateLimitKbps", "txRateLimitKbps"):
            if args.get(k) is not None:
                body[k] = args[k]
        return unifi_request(f"/v1/sites/{args['siteId']}/hotspot/vouchers", method="POST", body=body)
    if name == "unifi_delete_voucher":
        return unifi_request(
            f"/v1/sites/{args['siteId']}/hotspot/vouchers/{args['voucherId']}",
            method="DELETE",
        )
    if name == "unifi_list_firewall_zones":
        return unifi_request(f"/v1/sites/{args['siteId']}/firewall/zones", params=p(["offset", "limit", "filter"]))
    if name == "unifi_list_firewall_policies":
        return unifi_request(f"/v1/sites/{args['siteId']}/firewall/policies", params=p(["offset", "limit", "filter"]))
    if name == "unifi_list_acl_rules":
        return unifi_request(f"/v1/sites/{args['siteId']}/acl-rules", params=p(["offset", "limit", "filter"]))
    if name == "unifi_list_dns_policies":
        return unifi_request(f"/v1/sites/{args['siteId']}/dns/policies", params=p(["offset", "limit", "filter"]))
    if name == "unifi_list_traffic_matching_lists":
        return unifi_request(
            f"/v1/sites/{args['siteId']}/traffic-matching-lists", params=p(["offset", "limit", "filter"])
        )
    if name == "unifi_list_wans":
        return unifi_request(f"/v1/sites/{args['siteId']}/wans", params=p(["offset", "limit"]))
    if name == "unifi_cloud_list_hosts":
        cfg = get_config()
        if not cfg["api_key"]:
            return {"error": "Missing UNIFI_API_KEY."}
        status, data = http_json_request(
            "https://api.ui.com/v1/hosts", "GET", cfg["api_key"], verify_ssl=True, timeout=cfg["timeout"]
        )
        return {"endpoint": "https://api.ui.com/v1/hosts", "httpStatusCode": status, "response": data}
    if name == "unifi_raw_request":
        return unifi_request(
            args["path"],
            method=args.get("method", "GET"),
            params=args.get("params"),
            body=args.get("body"),
        )
    raise ValueError(f"Unknown tool: {name}")


def handle_rpc(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        client_proto = (msg.get("params") or {}).get("protocolVersion") or "2024-11-05"
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": client_proto,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "unifi-network", "version": "1.0.0"},
            },
        }
    if method and method.startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        tool_name = params.get("name", "")
        tool_args = params.get("arguments") or {}
        try:
            res = dispatch_tool(tool_name, tool_args)
            is_err = bool(res.get("error")) or (res.get("httpStatusCode", 200) >= 400)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                    "isError": is_err,
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(e)}, indent=2)}],
                    "isError": True,
                },
            }
    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def main() -> None:
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("content-length:"):
            length = int(stripped.split(":", 1)[1].strip())
            while True:
                hdr = sys.stdin.readline()
                if not hdr or hdr.strip() == "":
                    break
            body = sys.stdin.read(length)
            msg = json.loads(body)
            resp = handle_rpc(msg)
            if resp is not None:
                out = json.dumps(resp)
                sys.stdout.write(f"Content-Length: {len(out.encode('utf-8'))}\r\n\r\n{out}")
                sys.stdout.flush()
        else:
            msg = json.loads(stripped)
            resp = handle_rpc(msg)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    main()
