"""Account-independent, in-memory demonstration. All addresses use reserved ranges."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import threading

from .cloud import CloudClient, CloudError, _iso, instance_actions


def demo_snapshot(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stamp = _iso(now - timedelta(minutes=7))
    home, edge = "ap-tokyo-1", "us-ashburn-1"
    compartment = "演示应用"

    def resource(rid: str, name: str, kind: str, region: str = home, state: str = "AVAILABLE", **fields) -> dict:
        return {"id": "demo-" + rid, "name": name, "kind": kind, "region": region,
                "compartment": compartment, "state": state, "createdAt": _iso(now - timedelta(days=40)),
                "freeEligible": None, "actions": [], "details": {}, **fields}

    resources = [
        resource("instance-home", "星港 · 应用节点", "instance", state="RUNNING", shape="VM.Standard.A1.Flex",
                 ocpus=2, memoryGb=12, publicIps=["192.0.2.20"], privateIps=["10.20.0.10"],
                 cpuPercent=24.6, memoryPercent=47.2, networkBytesOut=3.7 * 1024 ** 3,
                 actions=instance_actions("RUNNING"), details={"availabilityDomain": "DEMO:AD-1",
                     "metricsAsOf": stamp, "cpuPercentAsOf": stamp, "memoryPercentAsOf": stamp, "networkAsOf": stamp,
                     "networkPeriodStart": _iso(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)),
                     "vnics": [{"id": "demo-vnic-home", "name": "主网卡", "isPrimary": True,
                                "publicIps": ["192.0.2.20"], "privateIps": ["10.20.0.10"]}]}),
        resource("instance-batch", "月背 · 批处理节点", "instance", state="STOPPED", shape="VM.Standard.E4.Flex",
                 ocpus=1, memoryGb=8, publicIps=[], privateIps=["10.20.1.8"], cpuPercent=None, memoryPercent=None,
                 networkBytesOut=None, actions=instance_actions("STOPPED"), details={"metricsAsOf": None, "vnics": []}),
        resource("nlb-edge", "远航 · 跨区入口", "nlb", region=edge, state="ACTIVE", publicIps=["198.51.100.15"], privateIps=[],
                 actions=["nlb.backend.enable", "nlb.backend.disable"], details={"health": "OK", "isPrivate": False,
                     "subnetIds": ["demo-subnet-edge"], "topologyNote": "演示跨区域转发：后端地址位于主区域。",
                     "listeners": [{"name": "tls-entry", "protocol": "TCP", "port": 443, "defaultBackendSetName": "home-app"}],
                     "backendSets": [{"name": "home-app", "policy": "FIVE_TUPLE", "health": "OK",
                         "healthChecker": {"protocol": "TCP", "port": 443, "urlPath": None},
                         "backends": [{"name": "192.0.2.20:443", "ipAddress": "192.0.2.20", "port": 443,
                                       "isOffline": False, "isDrain": False, "isBackup": False, "weight": 1,
                                       "health": "OK", "targetId": None}]}]}),
        resource("lb-app", "星环 · 应用均衡", "lb", state="ACTIVE", publicIps=[], privateIps=["10.20.2.5"],
                 details={"health": "WARNING", "isPrivate": True, "subnetIds": ["demo-subnet-home"],
                     "listeners": [{"name": "web", "protocol": "HTTP", "port": 80, "defaultBackendSetName": "app"}],
                     "backendSets": [{"name": "app", "policy": "ROUND_ROBIN", "health": "WARNING",
                         "healthChecker": {"protocol": "HTTP", "port": 8080, "urlPath": "/health"},
                         "backends": [{"name": "10.20.0.10:8080", "ipAddress": "10.20.0.10", "port": 8080,
                                       "isOffline": False, "isDrain": False, "isBackup": False, "weight": 1, "health": "WARNING"}]}]}),
        resource("boot-home", "应用启动卷", "bootVolume", sizeGb=50, details={"vpusPerGb": 10, "availabilityDomain": "DEMO:AD-1"}),
        resource("block-data", "数据归档卷", "blockVolume", sizeGb=100, details={"vpusPerGb": 10}),
        resource("bucket", "星尘 · 对象归档", "bucket", sizeGb=1.4,
                 details={"approximateObjectCount": 128, "approximateSizeBytes": 1503238554,
                          "publicAccessType": "NoPublicAccess", "storageTier": "Standard", "versioning": "Enabled"}),
        resource("vcn-home", "主区域网络", "vcn", details={"cidrBlocks": ["10.20.0.0/16"], "dnsLabel": "demo"}),
        resource("vcn-edge", "边缘区域网络", "vcn", region=edge, details={"cidrBlocks": ["10.30.0.0/16"], "dnsLabel": "demoedge"}),
    ]
    daily = []
    for offset in range(now.day):
        day = (now - timedelta(days=offset)).date().isoformat()
        daily.append({"date": day, "amount": round(0.9 + offset * 0.12, 2)})
    daily.sort(key=lambda d: d["date"])
    traffic_daily = [{"date": d["date"], "bytes": (300 + idx * 22) * 1024 ** 2} for idx, d in enumerate(daily)]
    traffic_month = sum(day["bytes"] for day in traffic_daily)
    resources[0]["networkBytesOut"] = traffic_month
    return {"schemaVersion": 1, "mode": "demo", "generatedAt": stamp,
            "tenancy": {"name": "云境演示舱 · 合成数据", "homeRegion": home},
            "regions": [{"id": region, "name": region, "isHome": region == home, "status": "ready",
                         "resourceCount": sum(r["region"] == region for r in resources)} for region in (home, edge)],
            "resources": resources,
            "cost": {"currency": "USD", "monthToDate": round(sum(d["amount"] for d in daily), 2),
                     "previousMonth": 28.4, "asOf": _iso(now - timedelta(days=1)), "forecast": None, "daily": daily,
                     "byService": [{"name": "Compute", "amount": round(sum(d["amount"] for d in daily) * .65, 2)},
                                   {"name": "Block Storage", "amount": round(sum(d["amount"] for d in daily) * .35, 2)}],
                     "note": "合成演示金额，不是实际账单。真实 Usage API 存在延迟；预测不可用时保留为空。"},
            "traffic": {"todayBytes": traffic_daily[-1]["bytes"], "monthBytes": traffic_month, "officialMonthBytes": None,
                        "freeAllowanceBytes": None, "asOf": stamp, "source": "monitoring",
                        "daily": traffic_daily,
                        "note": "合成 VNIC 出站估计，含内网与跨区流量；没有叠加 NLB 字节，不代表公网计费流量或免费额度。"},
            "alerts": [{"id": "demo-mode", "level": "info", "title": "当前为演示舱", "message": "所有资源、地址与金额均为合成数据；操作只改变本次服务进程的演示状态。"},
                       {"id": "demo-lb-health", "level": "warning", "title": "应用均衡健康检查告警", "message": "演示后端健康检查返回警告。", "resourceId": "demo-lb-app"}],
            "errors": []}


class DemoCloudClient:
    def __init__(self):
        self._snapshot = demo_snapshot()
        self._lock = threading.RLock()

    def collect(self) -> dict:
        with self._lock:
            return deepcopy(self._snapshot)

    def _target(self, action: str, region: str, resource_id: str, params: dict) -> tuple[dict, dict | None]:
        CloudClient._validate_params(self, action, region, resource_id, params)
        resource = next((r for r in self._snapshot["resources"] if r["id"] == resource_id and r["region"] == region), None)
        if resource is None:
            raise CloudError("演示资源不存在。", "cloud_not_found")
        if action not in resource["actions"]:
            raise CloudError("当前演示资源状态不允许此操作。", "invalid_state")
        backend = None
        if action.startswith("nlb."):
            backend_set = next((s for s in resource["details"]["backendSets"] if s["name"] == params["backendSetName"]), None)
            backend = next((b for b in backend_set["backends"] if b["name"] == params["backendName"]), None) if backend_set else None
            if backend is None:
                raise CloudError("演示后端不存在。", "cloud_not_found")
        return resource, backend

    def prepare_action(self, action: str, region: str, resource_id: str, params: dict) -> dict:
        with self._lock:
            resource, _ = self._target(action, region, resource_id, params)
            etag = hashlib.sha256(json.dumps(resource, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            return {"resourceName": resource["name"], "summary": "演示操作：只更新合成数据，不调用 OCI。",
                    "requiresText": resource["name"] if action in {"instance.stop", "instance.reboot", "nlb.backend.enable", "nlb.backend.disable"} else None,
                    "etag": etag, "context": {"action": action, "region": region, "resourceId": resource_id, "params": dict(params)}}

    def execute_action(self, action: str, region: str, resource_id: str, params: dict,
                       etag: str | None = None, context: dict | None = None) -> dict:
        with self._lock:
            if not isinstance(etag, str) or not etag or not isinstance(context, dict):
                raise CloudError("请先确认演示操作。", "confirmation_required")
            fresh = self.prepare_action(action, region, resource_id, params)
            if not hmac.compare_digest(etag, fresh["etag"]) or context != fresh["context"]:
                raise CloudError("演示资源已变化，请重新确认。", "stale_resource")
            resource, backend = self._target(action, region, resource_id, params)
            if action == "instance.rename":
                resource["name"] = params["displayName"]
            elif action == "instance.start":
                resource["state"] = "RUNNING"
            elif action == "instance.stop":
                resource["state"] = "STOPPED"
                resource["cpuPercent"] = resource["memoryPercent"] = None
            elif action == "instance.reboot":
                resource["details"]["lastDemoRebootAt"] = _iso(datetime.now(timezone.utc))
            elif backend is not None:
                backend["isDrain"] = action.endswith("disable")
                if action.endswith("enable"):
                    backend["isOffline"] = False
            if resource["kind"] == "instance":
                resource["actions"] = instance_actions(resource["state"])
            self._snapshot["generatedAt"] = _iso(datetime.now(timezone.utc))
            return {"status": "succeeded", "message": "演示操作已完成，未调用真实云资源。"}
