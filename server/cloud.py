"""Bounded OCI SDK access. Only explicit, conditional mutations are exposed.

Provider errors are deliberately translated without including SDK exception text:
request URLs, signing data and account configuration must never reach the UI/logs.
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hmac
import ipaddress
import math
import threading
import time
from typing import Any, Callable


ACTIONS = frozenset({"instance.start", "instance.stop", "instance.reboot", "instance.rename",
                     "nlb.backend.enable", "nlb.backend.disable"})
UTC = timezone.utc

# Oracle's public product catalog (2026-10-08): these are VCN outbound
# transfer SKUs, each containing BOTH the free and paid price tiers.
# Do not infer outbound use from a service name, cost, or a generic GB unit.
OUTBOUND_SKUS = frozenset({"B88327", "B93455", "B93456"})
VCN_USAGE_SERVICES = frozenset({"virtual cloud network", "virtual cloud networks",
                                "networking - virtual cloud networks"})
BYTE_UNITS = {"bytes": 1, "byte": 1, "kb": 10**3, "mb": 10**6, "gb": 10**9, "tb": 10**12,
              "kib": 2**10, "mib": 2**20, "gib": 2**30, "tib": 2**40}


def _usage_classification(row: Any) -> str:
    """Return outbound / unrelated / uncertain, never guess a new SKU."""
    sku = str(_get(row, "sku_part_number") or "").upper()
    name = " ".join(str(_get(row, "sku_name") or "").casefold().split())
    service = " ".join(str(_get(row, "service") or "").casefold().split())
    if sku in OUTBOUND_SKUS:
        return "outbound" if service in VCN_USAGE_SERVICES and name.startswith("outbound data transfer") else "uncertain"
    # NLB/LB/firewall processed bytes and ingress never represent VCN outbound.
    if any(word in name for word in ("inbound", "ingress", "processed", "processing")):
        return "unrelated"
    if service in VCN_USAGE_SERVICES and any(word in name for word in ("transfer", "outbound", "egress", "bandwidth")):
        return "uncertain"
    if not service and any(word in name for word in ("outbound", "egress")):
        return "uncertain"
    return "unrelated"


class CloudError(Exception):
    def __init__(self, message: str = "OCI 请求失败，请稍后刷新。", code: str = "cloud_error"):
        super().__init__(message)
        self.message = message
        self.code = code


def _safe_error(exc: Exception) -> CloudError:
    if isinstance(exc, CloudError):
        return exc
    status = getattr(exc, "status", None)
    if status in (401, 403):
        return CloudError("OCI 身份验证失败或无权读取此范围。", "cloud_forbidden")
    if status == 404:
        return CloudError("资源不存在或当前 OCI 身份没有访问权限。", "cloud_not_found")
    if status == 412:
        return CloudError("资源已变化，请刷新并重新确认。", "stale_resource")
    if status in (409, 429):
        return CloudError("OCI 资源忙或请求受限，请稍后重试。", "cloud_busy")
    if isinstance(exc, (TimeoutError, ConnectionError)) or "timeout" in type(exc).__name__.lower():
        return CloudError("OCI 请求超时，已保留可用数据。", "cloud_timeout")
    return CloudError()


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _items(data: Any) -> list:
    if isinstance(data, (list, tuple)):
        return list(data)
    return list(_get(data, "items", []) or [])


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value)


def _date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except (ValueError, TypeError):
        return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def _header(response: Any, name: str) -> str | None:
    for key, value in (getattr(response, "headers", None) or {}).items():
        if key.lower() == name.lower():
            return str(value)
    return None


def instance_actions(state: str) -> list[str]:
    if state == "STOPPED":
        return ["instance.start", "instance.rename"]
    if state == "RUNNING":
        return ["instance.stop", "instance.reboot", "instance.rename"]
    return []


class CloudClient:
    """One client per server account; config and signing material remain server-side.

    Extra keyword-only knobs are useful for synthetic tests and deployment tuning.
    The semaphore applies to refreshes and actions together; SDK retries are off.
    """
    def __init__(self, config_path: str, profile: str = "DEFAULT", *, max_workers: int = 4,
                 collection_timeout: float = 180, timeout: tuple[float, float] = (5, 20)):
        try:
            import oci
            self._sdk = oci
            self._config = oci.config.from_file(file_location=config_path, profile_name=profile)
            oci.config.validate_config(self._config)
        except Exception:
            raise CloudError("OCI 配置不可用，请在服务器检查配置文件、配置段和签名密钥。", "cloud_config") from None
        self._workers = max(1, min(int(max_workers), 8))
        self._collection_timeout = max(1, float(collection_timeout))
        self._timeout = timeout
        self._slots = threading.BoundedSemaphore(self._workers)
        self._client_lock = threading.Lock()
        self._clients: dict[tuple[str, str], Any] = {}
        self._retry = oci.retry.NoneRetryStrategy()

    def _client(self, service: str, region: str) -> Any:
        with self._client_lock:
            key = (service, region)
            if key not in self._clients:
                sdk = self._sdk
                classes = {"identity": sdk.identity.IdentityClient, "compute": sdk.core.ComputeClient,
                           "network": sdk.core.VirtualNetworkClient, "block": sdk.core.BlockstorageClient,
                           "nlb": sdk.network_load_balancer.NetworkLoadBalancerClient,
                           "lb": sdk.load_balancer.LoadBalancerClient, "object": sdk.object_storage.ObjectStorageClient,
                           "monitoring": sdk.monitoring.MonitoringClient, "usage": sdk.usage_api.UsageapiClient}
                config = dict(self._config, region=region)
                self._clients[key] = classes[service](config, timeout=self._timeout, retry_strategy=self._retry)
            return self._clients[key]

    def _call(self, fn: Callable, *args: Any, deadline: float | None = None, **kwargs: Any) -> Any:
        remaining = max(0, deadline - time.monotonic()) if deadline is not None else 30
        if not self._slots.acquire(timeout=remaining):
            raise CloudError("采集时限已到，已保留部分结果。", "cloud_timeout")
        try:
            if deadline is not None and time.monotonic() >= deadline:
                raise CloudError("采集时限已到，已保留部分结果。", "cloud_timeout")
            return fn(*args, retry_strategy=self._retry, **kwargs)
        except Exception as exc:
            raise _safe_error(exc) from None
        finally:
            self._slots.release()

    def collect(self) -> dict:
        return _Collector(self).collect()

    def _validate_params(self, action: str, region: str, resource_id: str, params: dict) -> None:
        if action not in ACTIONS:
            raise CloudError("不支持此操作。", "action_not_allowed")
        if not isinstance(region, str) or not region or len(region) > 100:
            raise CloudError("区域参数无效。", "invalid_action")
        if not isinstance(resource_id, str) or not resource_id or len(resource_id) > 512:
            raise CloudError("资源参数无效。", "invalid_action")
        keys = {"displayName"} if action == "instance.rename" else (
            {"backendSetName", "backendName"} if action.startswith("nlb.") else set())
        if not isinstance(params, dict) or set(params) != keys:
            raise CloudError("操作参数无效。", "invalid_action")
        for key in keys:
            value = params[key]
            if not isinstance(value, str) or not value.strip() or len(value) > 255 or any(ord(c) < 32 for c in value):
                raise CloudError("名称必须为 1–255 个字符，且不能包含控制字符。", "invalid_action")
        if "displayName" in params and params["displayName"] != params["displayName"].strip():
            raise CloudError("资源名称首尾不能包含空白。", "invalid_action")

    def _check_region(self, region: str) -> None:
        identity = self._client("identity", self._config["region"])
        page = None
        seen = set()
        while True:
            kw = {"page": page} if page else {}
            response = self._call(identity.list_region_subscriptions, self._config["tenancy"], **kw)
            if any(_get(r, "region_name") == region and _get(r, "status") == "READY" for r in _items(response.data)):
                return
            page = _header(response, "opc-next-page")
            if not page:
                break
            if page in seen:
                raise CloudError("OCI 分页响应异常，请稍后重试。", "cloud_error")
            seen.add(page)
        raise CloudError("目标区域未订阅或尚未就绪。", "invalid_region")

    def prepare_action(self, action: str, region: str, resource_id: str, params: dict) -> dict:
        self._validate_params(action, region, resource_id, params)
        self._check_region(region)
        context: dict[str, Any] = {"action": action, "region": region, "resourceId": resource_id,
                                  "params": dict(params)}
        if action.startswith("instance."):
            response = self._call(self._client("compute", region).get_instance, resource_id)
            target = response.data
            if _get(target, "id") != resource_id:
                raise CloudError("OCI 返回的目标不匹配。", "invalid_action")
            state = _get(target, "lifecycle_state", "UNKNOWN")
            if action not in instance_actions(state):
                raise CloudError("实例当前状态不允许此操作，请刷新。", "invalid_state")
            name = _get(target, "display_name") or resource_id
            context.update(state=state, displayName=name)
            summaries = {"instance.start": "启动实例；启动后可能产生计算费用。",
                         "instance.stop": "请求正常关机；启动卷、存储和其他资源仍可能计费。",
                         "instance.reboot": "请求正常重启；现有连接可能中断。",
                         "instance.rename": f"将显示名称改为「{params.get('displayName', '')}」。"}
            summary = summaries[action]
            requires_text = name if action in {"instance.stop", "instance.reboot"} else None
        else:
            client = self._client("nlb", region)
            parent = self._call(client.get_network_load_balancer, resource_id)
            if _get(parent.data, "id") != resource_id:
                raise CloudError("OCI 返回的目标不匹配。", "invalid_action")
            if _get(parent.data, "lifecycle_state") != "ACTIVE":
                raise CloudError("负载均衡器当前状态不允许修改。", "invalid_state")
            response = self._call(client.get_backend, resource_id, params["backendSetName"], params["backendName"])
            backend = response.data
            if _get(backend, "name") != params["backendName"]:
                raise CloudError("后端目标已变化，请重新确认。", "stale_resource")
            parent_etag = _header(parent, "etag")
            if not parent_etag:
                raise CloudError("OCI 未提供资源版本，无法安全确认操作。", "etag_unavailable")
            name = _get(parent.data, "display_name") or resource_id
            context.update(state="ACTIVE", parentEtag=parent_etag, backend=_backend_config(backend))
            summary = (f"启用后端「{params['backendName']}」，恢复接收新连接。" if action.endswith("enable")
                       else f"排空后端「{params['backendName']}」，停止分配新连接；现有连接不会立即强制关闭。")
            requires_text = name
        etag = _header(response, "etag")
        if not etag:
            raise CloudError("OCI 未提供资源版本，无法安全确认操作。", "etag_unavailable")
        return {"resourceName": name, "summary": summary, "requiresText": requires_text,
                "etag": etag, "context": context}

    def execute_action(self, action: str, region: str, resource_id: str, params: dict,
                       etag: str | None = None, context: dict | None = None) -> dict:
        self._validate_params(action, region, resource_id, params)
        if not isinstance(etag, str) or not etag or not isinstance(context, dict):
            raise CloudError("缺少已确认的资源版本，请重新确认。", "confirmation_required")
        fresh = self.prepare_action(action, region, resource_id, params)
        if not hmac.compare_digest(etag, fresh["etag"]) or context != fresh["context"]:
            raise CloudError("资源或操作目标已变化，请重新确认。", "stale_resource")
        if action.startswith("instance."):
            client = self._client("compute", region)
            if action == "instance.rename":
                if context["displayName"] == params["displayName"]:
                    return {"status": "succeeded", "message": "实例已使用此名称，无需修改。"}
                details = self._sdk.core.models.UpdateInstanceDetails(display_name=params["displayName"])
                response = self._call(client.update_instance, resource_id, details, if_match=etag)
            else:
                provider_action = {"instance.start": "START", "instance.stop": "SOFTSTOP", "instance.reboot": "SOFTRESET"}[action]
                response = self._call(client.instance_action, resource_id, provider_action, if_match=etag)
        else:
            config = dict(context["backend"])
            target_drain = action == "nlb.backend.disable"
            if config["is_drain"] == target_drain and (target_drain or not config["is_offline"]):
                return {"status": "succeeded", "message": "后端已处于目标状态，无需修改。"}
            config["is_drain"] = target_drain
            if not target_drain:
                config["is_offline"] = False
            details = self._sdk.network_load_balancer.models.UpdateBackendDetails(**config)
            response = self._call(self._client("nlb", region).update_backend, resource_id, details,
                                  params["backendSetName"], params["backendName"], if_match=etag)
        result = {"status": "submitted", "message": "OCI 已接受操作请求，最终状态请刷新查看。"}
        work_id = _header(response, "opc-work-request-id")
        if work_id:
            result["workRequestId"] = work_id
        return result


def _backend_config(backend: Any) -> dict:
    # UpdateBackendDetails requires these fields. Do not replace address/port/target.
    return {"weight": _get(backend, "weight", 1), "is_backup": bool(_get(backend, "is_backup", False)),
            "is_drain": bool(_get(backend, "is_drain", False)), "is_offline": bool(_get(backend, "is_offline", False))}


class _Collector:
    def __init__(self, cloud: CloudClient):
        self.cloud = cloud
        self.now = datetime.now(UTC)
        self.month = self.now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        self.deadline = time.monotonic() + cloud._collection_timeout
        self.errors: list[dict] = []
        self._error_lock = threading.Lock()
        self.tenancy_id = cloud._config["tenancy"]

    def error(self, scope: str, exc: Exception) -> None:
        entry = {"scope": scope, "message": str(_safe_error(exc))}
        with self._error_lock:
            if entry not in self.errors:
                self.errors.append(entry)

    def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        return self.cloud._call(fn, *args, deadline=self.deadline, **kwargs)

    def optional(self, scope: str, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        try:
            return self.call(fn, *args, **kwargs).data
        except Exception as exc:
            self.error(scope, exc)
            return None

    def pages(self, scope: str, fn: Callable, *args: Any, **kwargs: Any) -> list:
        result = []
        seen = set()
        try:
            while True:
                response = self.call(fn, *args, **kwargs)
                result.extend(_items(response.data))
                page = _header(response, "opc-next-page")
                if not page:
                    return result
                if page in seen:
                    raise CloudError("OCI 分页响应异常，已保留前页数据。")
                seen.add(page)
                kwargs["page"] = page
        except Exception as exc:
            self.error(scope, exc)
        return result

    def collect(self) -> dict:
        region = self.cloud._config["region"]
        identity = self.cloud._client("identity", region)
        tenancy = self.optional("tenancy", identity.get_tenancy, self.tenancy_id)
        subscriptions = self.pages("regions", identity.list_region_subscriptions, self.tenancy_id)
        if not subscriptions:
            subscriptions = [{"region_name": region, "is_home_region": True, "status": "READY"}]
            self.error("regions", CloudError("无法确认区域订阅，暂时仅采集配置区域。"))
        home = next((_get(r, "region_name") for r in subscriptions if _get(r, "is_home_region")), region)
        identity = self.cloud._client("identity", home)
        compartments = self.pages("compartments", identity.list_compartments, self.tenancy_id,
                                  compartment_id_in_subtree=True, access_level="ACCESSIBLE")
        compartments = [{"id": self.tenancy_id, "name": "根区间", "lifecycle_state": "ACTIVE"}] + compartments
        compartments = list({_get(c, "id"): c for c in compartments
                             if _get(c, "id") and _get(c, "lifecycle_state", "ACTIVE") == "ACTIVE"}.values())
        namespace_data = self.optional("object/namespace", self.cloud._client("object", home).get_namespace,
                                       compartment_id=self.tenancy_id)
        namespace = namespace_data if isinstance(namespace_data, str) else None
        # Each region has one worker. Futures are consumed in subscription order for stable snapshots.
        with ThreadPoolExecutor(max_workers=self.cloud._workers, thread_name_prefix="oci-read") as pool:
            cost_future = pool.submit(self.cost, home)
            usage_future = pool.submit(self.outbound_usage, home)
            jobs = [(r, pool.submit(self.region, r, compartments, namespace)) for r in subscriptions]
            regions, resources, traffic_days, metric_dates = [], [], defaultdict(float), []
            for subscription, future in jobs:
                region_name = _get(subscription, "region_name")
                try:
                    row, items, days, dates = future.result()
                    regions.append(row)
                    resources.extend(items)
                    for day, amount in days.items():
                        traffic_days[day] += amount
                    metric_dates.extend(dates)
                except Exception as exc:
                    self.error(f"{region_name}/inventory", exc)
                    regions.append({"id": region_name, "name": region_name, "isHome": bool(_get(subscription, "is_home_region")),
                                    "status": "error", "resourceCount": 0})
            try:
                cost = cost_future.result()
            except Exception as exc:
                self.error("usage", exc)
                cost = empty_cost()
            try:
                official = usage_future.result()
            except Exception as exc:
                self.error("usage/outbound", exc)
                official = empty_outbound_usage()
        today = self.now.date().isoformat()
        traffic = {"todayBytes": traffic_days.get(today), "monthBytes": sum(traffic_days.values()) if traffic_days else None,
                   "freeAllowanceBytes": None, "asOf": max(metric_dates) if metric_dates else official["officialAsOf"],
                   "source": "monitoring" if metric_dates else "billing" if official["officialAsOf"] else "unavailable",
                   "daily": [{"date": day, "bytes": value} for day, value in sorted(traffic_days.items())],
                   "note": "实例关联 VNIC 出站字节估计（UTC）；包含内网、跨区域及丢包前流量，不等于公网计费出站或免费额度消耗。未叠加 NLB/LB 字节；缺失采样和无权限范围未计入。"}
        traffic.update(official)
        traffic["note"] += " " + official["officialNote"]
        alerts = []
        if self.errors:
            alerts.append({"id": "partial-data", "level": "warning", "title": "部分数据暂不可用",
                           "message": "部分区域、区间或服务读取失败。已保留成功结果；空值不代表零用量。"})
        for resource in resources:
            if (resource.get("cpuPercent") or 0) >= 85:
                alerts.append({"id": "cpu-" + resource["id"], "level": "warning", "title": "CPU 使用率较高",
                               "message": "最近可用采样超过 85%，请结合业务和监控时间判断。", "resourceId": resource["id"]})
        return {"schemaVersion": 1, "generatedAt": _iso(self.now), "mode": "live",
                "tenancy": {"name": _get(tenancy, "name") or "已连接租户", "homeRegion": home},
                "regions": regions, "resources": sorted(resources, key=lambda r: (r["region"], r["kind"], r["name"], r["id"])),
                "cost": cost, "traffic": traffic, "alerts": alerts, "errors": sorted(self.errors, key=lambda e: (e["scope"], e["message"]))}

    def resource(self, obj: Any, kind: str, region: str, compartment: str) -> dict:
        result = {"id": _get(obj, "id") or _get(obj, "name"), "name": _get(obj, "display_name") or _get(obj, "name") or "未命名资源",
                "kind": kind, "region": region, "compartment": compartment,
                "state": _get(obj, "lifecycle_state") or "AVAILABLE",
                "freeEligible": None, "actions": [], "details": {}}
        if _get(obj, "time_created") is not None:
            result["createdAt"] = _iso(_get(obj, "time_created"))
        return result

    def region(self, subscription: Any, compartments: list, namespace: str | None) -> tuple:
        region = _get(subscription, "region_name")
        row = {"id": region, "name": region, "isHome": bool(_get(subscription, "is_home_region")),
               "status": "ready", "resourceCount": 0}
        if _get(subscription, "status") != "READY":
            row["status"] = "error"
            self.error(f"{region}/subscription", CloudError("区域订阅尚未就绪。"))
            return row, [], {}, []
        clients = {name: self.cloud._client(name, region) for name in
                   ("compute", "network", "block", "nlb", "lb", "object", "identity", "monitoring")}
        ads = self.pages(f"{region}/availabilityDomains", clients["identity"].list_availability_domains, self.tenancy_id)
        resources, traffic_days, metric_dates = [], defaultdict(float), []
        for comp in compartments:
            if time.monotonic() >= self.deadline:
                self.error(f"{region}/deadline", CloudError("采集时限已到，后续区间未采集。", "cloud_timeout"))
                break
            comp_id, comp_name = _get(comp, "id"), _get(comp, "name")
            # Use ids in scopes to distinguish identically named compartments. Runtime only.
            scope = f"{region}/{comp_id}"
            instances = self.pages(scope + "/instances", clients["compute"].list_instances, compartment_id=comp_id)
            current = []
            for obj in instances:
                r = self.resource(obj, "instance", region, comp_name)
                shape_config = _get(obj, "shape_config")
                r.update(shape=_get(obj, "shape"), ocpus=_number(_get(shape_config, "ocpus")),
                         memoryGb=_number(_get(shape_config, "memory_in_gbs")), cpuPercent=None,
                         memoryPercent=None, networkBytesOut=None, publicIps=[], privateIps=[],
                         actions=instance_actions(r["state"]))
                for optional_field in ("shape", "ocpus", "memoryGb"):
                    if r[optional_field] is None:
                        del r[optional_field]
                r["details"] = {"availabilityDomain": _get(obj, "availability_domain"), "vnics": [],
                                "compartmentId": comp_id, "metricsAsOf": None, "networkPeriodStart": _iso(self.month)}
                current.append(r)
            self.vnics(scope, clients, comp_id, current)
            days, dates = self.metrics(scope, clients["monitoring"], comp_id, current)
            for day, value in days.items():
                traffic_days[day] += value
            metric_dates.extend(dates)
            resources.extend(current)
            for kind, service, method in [("nlb", "nlb", "list_network_load_balancers"), ("lb", "lb", "list_load_balancers")]:
                for obj in self.pages(scope + "/" + kind, getattr(clients[service], method), compartment_id=comp_id):
                    resources.append(self.load_balancer(scope, clients[service], obj, kind, region, comp_name))
            volumes = [("blockVolume", obj) for obj in self.pages(scope + "/blockVolumes", clients["block"].list_volumes, compartment_id=comp_id)]
            for ad in ads:
                volumes.extend(("bootVolume", obj) for obj in self.pages(scope + "/bootVolumes", clients["block"].list_boot_volumes,
                                                                       availability_domain=_get(ad, "name"), compartment_id=comp_id))
            for kind, obj in volumes:
                r = self.resource(obj, kind, region, comp_name)
                size = _number(_get(obj, "size_in_gbs"))
                if size is not None:
                    r["sizeGb"] = size
                r["details"] = {"availabilityDomain": _get(obj, "availability_domain"), "vpusPerGb": _get(obj, "vpus_per_gb"),
                                "isAutoTuneEnabled": _get(obj, "is_auto_tune_enabled"), "compartmentId": comp_id}
                resources.append(r)
            if namespace:
                for obj in self.pages(scope + "/buckets", clients["object"].list_buckets, namespace_name=namespace, compartment_id=comp_id):
                    r = self.resource(obj, "bucket", region, comp_name)
                    r["id"] = f"bucket:{region}:{namespace}:{_get(obj, 'name')}"
                    detail = self.optional(scope + "/bucketDetails", clients["object"].get_bucket, namespace, _get(obj, "name"),
                                           fields=["approximateCount", "approximateSize"])
                    size = _number(_get(detail, "approximate_size"))
                    if size is not None:
                        r["sizeGb"] = size / (1024 ** 3)
                    r["details"] = {"approximateObjectCount": _get(detail, "approximate_count"), "approximateSizeBytes": size,
                                    "publicAccessType": _get(detail, "public_access_type"), "storageTier": _get(detail, "storage_tier"),
                                    "versioning": _get(detail, "versioning"), "compartmentId": comp_id}
                    resources.append(r)
            for obj in self.pages(scope + "/vcns", clients["network"].list_vcns, compartment_id=comp_id):
                r = self.resource(obj, "vcn", region, comp_name)
                r["details"] = {"cidrBlocks": _get(obj, "cidr_blocks") or [_get(obj, "cidr_block")],
                                "ipv6CidrBlocks": _get(obj, "ipv6_cidr_blocks") or [], "dnsLabel": _get(obj, "dns_label"), "compartmentId": comp_id}
                resources.append(r)
        row["resourceCount"] = len(resources)
        if any(e["scope"].startswith(region + "/") for e in self.errors):
            row["status"] = "error"
        return row, resources, traffic_days, metric_dates

    def vnics(self, scope: str, clients: dict, comp_id: str, instances: list[dict]) -> None:
        by_id = {i["id"]: i for i in instances}
        if not by_id:
            return
        attachments = self.pages(scope + "/vnicAttachments", clients["compute"].list_vnic_attachments, compartment_id=comp_id)
        for attachment in attachments:
            instance = by_id.get(_get(attachment, "instance_id"))
            vnic_id = _get(attachment, "vnic_id")
            if not instance or not vnic_id or _get(attachment, "lifecycle_state") != "ATTACHED":
                continue
            vnic = self.optional(scope + "/vnics", clients["network"].get_vnic, vnic_id)
            detail = {"id": vnic_id, "name": _get(vnic, "display_name"), "subnetId": _get(vnic, "subnet_id"),
                      "compartmentId": _get(vnic, "compartment_id") or comp_id,
                      "isPrimary": _get(vnic, "is_primary"), "publicIps": [], "privateIps": []}
            if _get(vnic, "public_ip"):
                detail["publicIps"].append(_get(vnic, "public_ip"))
            if _get(vnic, "private_ip"):
                detail["privateIps"].append(_get(vnic, "private_ip"))
            for private in self.pages(scope + "/privateIps", clients["network"].list_private_ips, vnic_id=vnic_id):
                ip = _get(private, "ip_address")
                if ip and ip not in detail["privateIps"]:
                    detail["privateIps"].append(ip)
                if not _get(private, "is_primary", False):
                    model = self.cloud._sdk.core.models.GetPublicIpByPrivateIpIdDetails(private_ip_id=_get(private, "id"))
                    try:
                        public = self.call(clients["network"].get_public_ip_by_private_ip_id, model).data
                        if _get(public, "ip_address"):
                            detail["publicIps"].append(_get(public, "ip_address"))
                    except CloudError as exc:
                        if exc.code != "cloud_not_found":
                            self.error(scope + "/secondaryPublicIps", exc)
            # IPv6 may also be a private/ULA address; do not imply public reachability.
            for ipv6 in self.pages(scope + "/ipv6", clients["network"].list_ipv6s, vnic_id=vnic_id):
                address = _get(ipv6, "ip_address")
                if address:
                    try:
                        field = "publicIps" if ipaddress.ip_address(address).is_global else "privateIps"
                        detail[field].append(address)
                    except ValueError:
                        self.error(scope + "/ipv6", CloudError("OCI 返回了无法识别的 IPv6 地址。"))
            instance["details"]["vnics"].append(detail)
            instance["publicIps"] = sorted(set(instance["publicIps"] + detail["publicIps"]))
            instance["privateIps"] = sorted(set(instance["privateIps"] + detail["privateIps"]))

    def load_balancer(self, scope: str, client: Any, obj: Any, kind: str, region: str, compartment: str) -> dict:
        r = self.resource(obj, kind, region, compartment)
        nlb = kind == "nlb"
        get_method = client.get_network_load_balancer if nlb else client.get_load_balancer
        full = self.optional(scope + "/" + kind + "Details", get_method, r["id"]) or obj
        addresses = _get(full, "ip_addresses", []) or []
        r["publicIps"] = [_get(ip, "ip_address") for ip in addresses if _get(ip, "ip_address") and _get(ip, "is_public", not _get(full, "is_private", False))]
        r["privateIps"] = [_get(ip, "ip_address") for ip in addresses if _get(ip, "ip_address") and not _get(ip, "is_public", not _get(full, "is_private", False))]
        health_method = client.get_network_load_balancer_health if nlb else client.get_load_balancer_health
        health = self.optional(scope + "/" + kind + "Health", health_method, r["id"])
        sets = _get(full, "backend_sets", {}) or {}
        if nlb:
            sets = {_get(s, "name"): s for s in self.pages(scope + "/nlbBackendSets", client.list_backend_sets, r["id"])}
        result_sets = []
        for name, backend_set in sets.items():
            set_health = self.optional(scope + "/" + kind + "BackendHealth", client.get_backend_set_health, r["id"], name)
            backends = _get(backend_set, "backends", []) or []
            if nlb:
                backends = self.pages(scope + "/nlbBackends", client.list_backends, r["id"], name)
            critical = set(_get(set_health, "critical_state_backend_names", []) or [])
            warning = set(_get(set_health, "warning_state_backend_names", []) or [])
            unknown = set(_get(set_health, "unknown_state_backend_names", []) or [])
            rows = []
            for backend in backends:
                bname = _get(backend, "name")
                backend_health = ("CRITICAL" if bname in critical else "WARNING" if bname in warning else "UNKNOWN" if bname in unknown else None)
                # Absence from problem lists only establishes OK if the set reports OK.
                if backend_health is None and _get(set_health, "status") == "OK":
                    backend_health = "OK"
                rows.append({"name": bname, "ipAddress": _get(backend, "ip_address"), "port": _get(backend, "port"),
                             "isOffline": bool(_get(backend, "is_offline", False)), "isDrain": bool(_get(backend, "is_drain", False)),
                             "isBackup": bool(_get(backend, "is_backup", False)), "weight": _get(backend, "weight"),
                             "health": backend_health, "targetId": _get(backend, "target_id")})
            checker = _get(backend_set, "health_checker")
            result_sets.append({"name": name, "policy": _get(backend_set, "policy"), "health": _get(set_health, "status"), "backends": rows,
                                "healthChecker": {"protocol": _get(checker, "protocol"), "port": _get(checker, "port"), "urlPath": _get(checker, "url_path")}})
        listeners = _get(full, "listeners", {}) or {}
        r["details"] = {"health": _get(health, "status"), "backendSets": result_sets,
                        "listeners": [{"name": name, "port": _get(listener, "port"), "protocol": _get(listener, "protocol"),
                                       "defaultBackendSetName": _get(listener, "default_backend_set_name")} for name, listener in listeners.items()],
                        "subnetIds": _get(full, "subnet_ids") or ([_get(full, "subnet_id")] if _get(full, "subnet_id") else []),
                        "isPrivate": _get(full, "is_private"), "compartmentId": _get(full, "compartment_id"),
                        "topologyNote": "后端可能跨区域或位于外部网络；仅按 OCI 返回的地址展示，不推断计费路径。"}
        if nlb and r["state"] == "ACTIVE":
            r["actions"] = ["nlb.backend.enable", "nlb.backend.disable"]
        return r

    def metrics(self, scope: str, client: Any, comp_id: str, instances: list[dict]) -> tuple:
        if not instances:
            return {}, []
        by_id = {r["id"]: r for r in instances}
        for metric, field in [("CpuUtilization", "cpuPercent"), ("MemoryUtilization", "memoryPercent")]:
            details = self.cloud._sdk.monitoring.models.SummarizeMetricsDataDetails(
                namespace="oci_computeagent", query=f"{metric}[5m].mean()", resolution="5m",
                start_time=self.now - timedelta(hours=1), end_time=self.now)
            streams = self.pages(scope + "/metrics/" + metric, client.summarize_metrics_data, comp_id, details)
            samples: dict[str, tuple[datetime, float]] = {}
            for stream in streams:
                rid = (_get(stream, "dimensions", {}) or {}).get("resourceId")
                for point in _get(stream, "aggregated_datapoints", []) or []:
                    stamp, value = _date(_get(point, "timestamp")), _number(_get(point, "value"))
                    if rid in by_id and stamp and self.now - timedelta(hours=1) <= stamp <= self.now and value is not None and 0 <= value <= 100:
                        if rid not in samples or stamp > samples[rid][0]:
                            samples[rid] = (stamp, value)
            for rid, (stamp, value) in samples.items():
                by_id[rid][field] = value
                by_id[rid]["details"][field + "AsOf"] = _iso(stamp)
                current = by_id[rid]["details"]["metricsAsOf"]
                by_id[rid]["details"]["metricsAsOf"] = max(current or "", _iso(stamp))
        vnic_owner = {v["id"]: r for r in instances for v in r["details"]["vnics"]}
        if not vnic_owner:
            return {}, []
        details = self.cloud._sdk.monitoring.models.SummarizeMetricsDataDetails(
            namespace="oci_vcn", query="VnicToNetworkBytes[1h].sum()", resolution="1h", start_time=self.month, end_time=self.now)
        vnic_compartments = {v.get("compartmentId") or comp_id for r in instances for v in r["details"]["vnics"]}
        streams = []
        for vnic_compartment in sorted(vnic_compartments):
            streams.extend(self.pages(scope + "/metrics/network/" + vnic_compartment,
                                      client.summarize_metrics_data, vnic_compartment, details))
        days, dates, seen = defaultdict(float), [], set()
        for stream in streams:
            dimensions = _get(stream, "dimensions", {}) or {}
            rid = dimensions.get("resourceId")
            owner = vnic_owner.get(rid)
            if owner is None:
                continue  # Never count NLB metrics or other unassociated VNICs.
            for point in _get(stream, "aggregated_datapoints", []) or []:
                stamp, value = _date(_get(point, "timestamp")), _number(_get(point, "value"))
                key = (rid, _iso(stamp))
                if stamp and self.month <= stamp <= self.now and value is not None and value >= 0 and key not in seen:
                    seen.add(key)
                    days[stamp.date().isoformat()] += value
                    dates.append(_iso(stamp))
                    owner["networkBytesOut"] = (owner["networkBytesOut"] or 0) + value
                    owner["details"]["networkAsOf"] = max(owner["details"].get("networkAsOf", ""), _iso(stamp))
        return days, dates

    def outbound_usage(self, home: str) -> dict:
        """Read official quantities, including zero-cost usage, without quota claims."""
        result = empty_outbound_usage()
        end = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
        if end <= self.month:
            result["officialNote"] = "本月尚无已结束的 UTC 日期，官方日用量暂不可用。"
            return result
        details = self.cloud._sdk.usage_api.models.RequestSummarizedUsagesDetails(
            tenant_id=self.tenancy_id, time_usage_started=self.month, time_usage_ended=end,
            granularity="DAILY", query_type="USAGE", is_aggregate_by_time=False,
            group_by=["service", "skuName", "skuPartNumber", "unit"])
        scope = "usage/outbound"
        rows = self.pages(scope, self.cloud._client("usage", home).request_summarized_usages, details)
        incomplete = any(e["scope"] == scope for e in self.errors)
        uncertain = False
        unit_unknown = False
        totals: dict[str, Decimal] = defaultdict(Decimal)
        sku_totals: dict[tuple, Decimal] = defaultdict(Decimal)
        seen: dict[tuple, Decimal] = {}
        group_tiers: dict[tuple, set[str]] = defaultdict(set)
        as_of = []
        byte_total = Decimal(0)
        for row in rows:
            classification = _usage_classification(row)
            if classification == "unrelated" or _get(row, "is_forecast", False):
                continue
            if classification == "uncertain":
                uncertain = True
                continue
            start = _date(_get(row, "time_usage_started"))
            ended = _date(_get(row, "time_usage_ended"))
            if start is None or ended is None or not self.month <= start < ended <= end:
                uncertain = True
                continue
            try:
                quantity = Decimal(str(_get(row, "computed_quantity")))
                if not quantity.is_finite() or quantity < 0 or not math.isfinite(float(quantity)):
                    raise ValueError
            except (InvalidOperation, ValueError):
                uncertain = True
                continue
            unit = " ".join(str(_get(row, "unit") or "").split())
            sku = str(_get(row, "sku_part_number")).upper()
            # The requested grouping should provide one quantity per SKU/unit/day.
            # Explicit free/overage flags may partition it; otherwise conflicting
            # duplicate groups are ambiguous, not additional transfer to sum.
            raw_tier = str(_get(row, "overages_flag") or "").casefold()
            tier = {"n": "free", "no": "free", "false": "free", "y": "overage", "yes": "overage", "true": "overage", "": ""}.get(raw_tier)
            if tier is None:
                uncertain = True
                continue
            group = (sku, unit.casefold(), _iso(start), _iso(ended))
            group_tiers[group].add(tier)
            if "" in group_tiers[group] and len(group_tiers[group]) > 1:
                uncertain = True  # A total plus its free/overage subset would double count.
            key = (*group, tier)
            if key in seen:
                if seen[key] != quantity:
                    uncertain = True
                continue
            seen[key] = quantity
            totals[unit] += quantity
            sku_totals[(sku, str(_get(row, "sku_name")), str(_get(row, "service")), unit)] += quantity
            as_of.append(_iso(ended))
            factor = BYTE_UNITS.get(unit.casefold())
            if factor is None:
                unit_unknown = True
            else:
                byte_total += quantity * factor
        result["officialSkus"] = [
            {"skuPartNumber": sku, "skuName": name, "service": service, "unit": unit, "quantity": float(quantity)}
            for (sku, name, service, unit), quantity in sorted(sku_totals.items())]
        result["officialAsOf"] = max(as_of) if as_of else None
        if not math.isfinite(float(byte_total)):
            uncertain = True
        if incomplete or uncertain:
            result["officialStatus"] = "partial"
            result["officialNote"] = "Usage API 出站用量存在分页失败、未识别 SKU、缺失数量或重复分组冲突；未给出完整合计，已识别原始项见 officialSkus。免费额度范围未核实。"
            if uncertain:
                self.error(scope + "/classification", CloudError("部分出站计费项无法可靠识别或合并，官方月总量暂不可用。"))
            return result
        if not totals:
            return result
        if len(totals) == 1:
            result["officialUnit"], quantity = next(iter(totals.items()))
            result["officialQuantity"] = float(quantity)
        result["officialStatus"] = "unit_unverified" if unit_unknown else "available"
        if not unit_unknown:
            result["officialMonthBytes"] = float(byte_total)
        result["officialNote"] = (
            "官方 VCN 出站已报告用量来自 Usage API，包含费用为零的用量；仅覆盖截至 officialAsOf 的 UTC 完整日期，存在账单延迟。"
            + ("原始数量/单位已保留，但单位的字节换算尚未核实，officialMonthBytes 保持空值。" if unit_unknown
               else "GB 按 10⁹ 字节、GiB 按 2³⁰ 字节换算；不叠加监控或 NLB 处理字节。")
            + "免费 10 TB 的租户/区域共享范围未核实，不推算已用免费额度或剩余额度。")
        return result

    def cost(self, home: str) -> dict:
        result = empty_cost()
        previous = (self.month - timedelta(days=1)).replace(day=1)
        # UTC daily boundary avoids representing the current unfinished day as final.
        end = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
        details = self.cloud._sdk.usage_api.models.RequestSummarizedUsagesDetails(
            tenant_id=self.tenancy_id, time_usage_started=previous, time_usage_ended=end,
            granularity="DAILY", query_type="COST", group_by=["service"])
        rows = self.pages("usage/cost", self.cloud._client("usage", home).request_summarized_usages, details)
        currencies = {_get(row, "currency") for row in rows if _number(_get(row, "computed_amount")) is not None}
        if len(currencies) > 1 or (currencies and None in currencies):
            self.error("usage/currency", CloudError("账单币种缺失或包含多个币种，未合并金额。"))
            return result
        if currencies:
            result["currency"] = next(iter(currencies))
        daily, services = defaultdict(float), defaultdict(float)
        previous_values, as_of = [], []
        for row in rows:
            amount = _number(_get(row, "computed_amount"))
            start, ended = _date(_get(row, "time_usage_started")), _date(_get(row, "time_usage_ended"))
            if amount is None or start is None or start >= end or start < previous:
                continue
            if ended:
                as_of.append(_iso(ended))
            if start < self.month:
                previous_values.append(amount)
            else:
                daily[start.date().isoformat()] += amount
                services[_get(row, "service") or "未分类服务"] += amount
        result.update(monthToDate=sum(daily.values()) if daily else None,
                      previousMonth=sum(previous_values) if previous_values else None,
                      asOf=max(as_of) if as_of else None,
                      daily=[{"date": day, "amount": value} for day, value in sorted(daily.items())],
                      byService=[{"name": name, "amount": value} for name, value in sorted(services.items(), key=lambda pair: (-pair[1], pair[0]))])
        return result


def empty_cost() -> dict:
    return {"currency": "", "monthToDate": None, "previousMonth": None, "asOf": None, "forecast": None,
            "daily": [], "byService": [], "note": "OCI Usage API 已报告费用（UTC 日界），存在延迟和后续调整；不含尚未报告的用量。空值不代表免费或零费用，预测暂不可用。"}


def empty_outbound_usage() -> dict:
    return {"officialMonthBytes": None, "officialQuantity": None, "officialUnit": None,
            "officialAsOf": None, "officialSource": "usage_api", "officialStatus": "unavailable", "officialSkus": [],
            "officialNote": "已尝试读取 Usage API 官方出站用量；尚无可识别的本月数据，不等于零用量。账单存在延迟，免费额度范围未核实。"}
