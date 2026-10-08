"""Synthetic SDK boundary tests. No configuration/key files or OCI network access."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import inspect
import json
import threading
import time
from types import SimpleNamespace as NS

import oci
import pytest

from server.cloud import CloudClient, CloudError, _Collector, _safe_error
from server.demo import DemoCloudClient, demo_snapshot

UTC = timezone.utc
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def response(data=None, etag=None, page=None):
    headers = {}
    if etag:
        headers["etag"] = etag
    if page:
        headers["opc-next-page"] = page
    return NS(data=[] if data is None else data, headers=headers)


CLASSES = {"identity": oci.identity.IdentityClient, "compute": oci.core.ComputeClient,
           "network": oci.core.VirtualNetworkClient, "block": oci.core.BlockstorageClient,
           "nlb": oci.network_load_balancer.NetworkLoadBalancerClient,
           "lb": oci.load_balancer.LoadBalancerClient, "object": oci.object_storage.ObjectStorageClient,
           "monitoring": oci.monitoring.MonitoringClient, "usage": oci.usage_api.UsageapiClient}


class FakeService:
    def __init__(self, service):
        self.service = service
        self.handlers = {}
        self.calls = []

    def __getattr__(self, name):
        actual = getattr(CLASSES[self.service], name)  # Misspelled SDK methods fail.
        signature = inspect.signature(actual)

        def call(*args, **kwargs):
            signature.bind(None, *args, **kwargs)
            self.calls.append((name, args, kwargs))
            handler = self.handlers.get(name)
            return handler(*args, **kwargs) if callable(handler) else handler or response()
        return call


def fake_cloud():
    # Bypass __init__: reading any real OCI profile is prohibited in this suite.
    cloud = object.__new__(CloudClient)
    cloud._config = {"tenancy": "synthetic-tenancy", "region": "region-a"}
    cloud._sdk = oci
    cloud._workers = 3
    cloud._collection_timeout = 5
    cloud._timeout = (5, 20)
    cloud._retry = oci.retry.NoneRetryStrategy()
    cloud._slots = threading.BoundedSemaphore(3)
    cloud._client_lock = threading.Lock()
    cloud._clients = {(service, region): FakeService(service) for service in CLASSES for region in ("region-a", "region-b")}
    ident = cloud._clients["identity", "region-a"]
    ident.handlers["get_tenancy"] = response(NS(name="合成租户"))
    ident.handlers["list_region_subscriptions"] = response([
        NS(region_name="region-a", is_home_region=True, status="READY"),
        NS(region_name="region-b", is_home_region=False, status="READY")])
    for region in ("region-a", "region-b"):
        cloud._clients["object", region].handlers["get_namespace"] = response("synthetic-namespace")
    return cloud


def collector(cloud):
    result = _Collector(cloud)
    result.now = NOW
    result.month = NOW.replace(day=1, hour=0)
    return result


def service(cloud, name, region="region-a"):
    return cloud._clients[name, region]


def instance(rid="synthetic-instance", state="RUNNING", name="合成实例"):
    return NS(id=rid, display_name=name, lifecycle_state=state, shape="VM.Standard.A1.Flex",
              shape_config=NS(ocpus=2, memory_in_gbs=12), availability_domain="SYNTHETIC:AD-1", compartment_id="app")


def set_instance(cloud, state="RUNNING", etag="v1"):
    obj = instance(state=state)
    service(cloud, "compute").handlers["get_instance"] = response(obj, etag=etag)
    return obj


def point(value, day=8):
    return NS(timestamp=NOW.replace(day=day, hour=11, minute=30), value=value)


def stream(rid, points):
    return NS(dimensions={"resourceId": rid}, aggregated_datapoints=points)


def test_collect_all_pages_regions_compartments_and_resource_kinds():
    cloud = fake_cloud()
    identity = service(cloud, "identity")
    identity.handlers["list_region_subscriptions"] = lambda *a, **kw: (
        response([NS(region_name="region-b", is_home_region=False, status="READY")]) if kw.get("page")
        else response([NS(region_name="region-a", is_home_region=True, status="READY")], page="region-page-2"))
    identity.handlers["list_compartments"] = lambda *a, **kw: (
        response([NS(id="nested", name="嵌套区间", lifecycle_state="ACTIVE")]) if kw.get("page")
        else response([NS(id="app", name="应用区间", lifecycle_state="ACTIVE")], page="comp-page-2"))
    for region in ("region-a", "region-b"):
        service(cloud, "identity", region).handlers["list_availability_domains"] = response([NS(name="SYNTHETIC:AD-1")])
        compute = service(cloud, "compute", region)
        compute.handlers["list_instances"] = lambda compartment_id, **kw: response([instance()] if compartment_id == "app" else [])
        compute.handlers["list_vnic_attachments"] = response([NS(instance_id="synthetic-instance", vnic_id="synthetic-vnic", lifecycle_state="ATTACHED")])
        network = service(cloud, "network", region)
        network.handlers["get_vnic"] = response(NS(display_name="主网卡", public_ip="192.0.2.1", private_ip="10.0.0.1", compartment_id="app"))
        network.handlers["list_private_ips"] = response([NS(id="private-one", ip_address="10.0.0.1", is_primary=True)])
        network.handlers["list_vcns"] = lambda compartment_id, **kw: response([NS(id="synthetic-vcn", display_name="网络", cidr_blocks=["10.0.0.0/16"])] if compartment_id == "app" else [])
        for method in ("list_volumes", "list_boot_volumes"):
            service(cloud, "block", region).handlers[method] = lambda compartment_id, **kw: response([NS(id="synthetic-volume", display_name="存储卷", size_in_gbs=50)] if compartment_id == "app" else [])
        service(cloud, "object", region).handlers["list_buckets"] = lambda namespace_name, compartment_id, **kw: response([NS(name="synthetic-bucket")] if compartment_id == "app" else [])
        service(cloud, "object", region).handlers["get_bucket"] = response(NS(approximate_size=2**30, approximate_count=12))
    nlb = NS(id="synthetic-nlb", display_name="跨区入口", lifecycle_state="ACTIVE", compartment_id="app",
             ip_addresses=[NS(ip_address="198.51.100.10", is_public=True)], listeners={"tls": NS(port=443, protocol="TCP", default_backend_set_name="home")})
    backend = NS(name="192.0.2.1:443", ip_address="192.0.2.1", port=443, weight=1, is_drain=False, is_offline=False)
    nlb_service = service(cloud, "nlb", "region-b")
    nlb_service.handlers["list_network_load_balancers"] = lambda compartment_id, **kw: response(NS(items=[nlb] if compartment_id == "app" else []))
    nlb_service.handlers["get_network_load_balancer"] = response(nlb)
    nlb_service.handlers["list_backend_sets"] = response(NS(items=[NS(name="home", policy="FIVE_TUPLE")]))
    nlb_service.handlers["list_backends"] = response(NS(items=[backend]))
    nlb_service.handlers["get_network_load_balancer_health"] = response(NS(status="OK"))
    nlb_service.handlers["get_backend_set_health"] = response(NS(status="OK"))
    lb = NS(id="synthetic-lb", display_name="应用均衡", lifecycle_state="ACTIVE", is_private=True,
            ip_addresses=[NS(ip_address="10.0.0.5", is_public=False)], backend_sets={"app": NS(backends=[backend])}, listeners={})
    service(cloud, "lb").handlers["list_load_balancers"] = lambda compartment_id, **kw: response([lb] if compartment_id == "nested" else [])
    service(cloud, "lb").handlers["get_load_balancer"] = response(lb)
    service(cloud, "lb").handlers["get_backend_set_health"] = response(NS(status="CRITICAL", critical_state_backend_names=[backend.name]))

    snapshot = collector(cloud).collect()
    assert snapshot["errors"] == []
    assert {r["kind"] for r in snapshot["resources"]} == {"instance", "nlb", "lb", "vcn", "bucket", "bootVolume", "blockVolume"}
    assert [r["id"] for r in snapshot["regions"]] == ["region-a", "region-b"]
    assert "serverId" not in snapshot
    for region in ("region-a", "region-b"):
        scopes = {kw["compartment_id"] for name, _, kw in service(cloud, "compute", region).calls if name == "list_instances"}
        assert scopes == {"synthetic-tenancy", "app", "nested"}
    nlb_result = next(r for r in snapshot["resources"] if r["kind"] == "nlb")
    assert nlb_result["details"]["backendSets"][0]["backends"][0]["ipAddress"] == "192.0.2.1"
    assert nlb_result["publicIps"] == ["198.51.100.10"]
    lb_result = next(r for r in snapshot["resources"] if r["kind"] == "lb")
    assert lb_result["details"]["backendSets"][0]["backends"][0]["health"] == "CRITICAL"
    assert lb_result["actions"] == []
    assert snapshot["traffic"]["monthBytes"] is None
    assert snapshot["cost"]["monthToDate"] is None
    json.dumps(snapshot, allow_nan=False)


def test_pagination_failure_keeps_previous_page_and_sanitizes_provider_exception():
    cloud = fake_cloud()
    c = collector(cloud)

    def paged(**kw):
        if kw.get("page"):
            raise oci.exceptions.ServiceError(403, "Forbidden", {}, "SYNTHETIC-SECRET-MUST-NOT-LEAK")
        return response(["first"], page="second")

    assert c.pages("scope", paged) == ["first"]
    assert c.errors == [{"scope": "scope", "message": "OCI 身份验证失败或无权读取此范围。"}]
    assert "SECRET" not in json.dumps(c.errors)


def test_repeated_page_token_is_bounded():
    c = collector(fake_cloud())
    calls = []

    def paged(**kw):
        calls.append(kw)
        return response([1], page="same")

    assert c.pages("scope", paged) == [1, 1]
    assert len(calls) == 2
    assert c.errors


def test_metrics_do_not_double_count_nlb_or_turn_missing_values_into_zero():
    cloud = fake_cloud()
    c = collector(cloud)
    resources = [{"id": "instance-a", "cpuPercent": None, "memoryPercent": None, "networkBytesOut": None,
                  "details": {"metricsAsOf": None, "vnics": [{"id": "vnic-a", "compartmentId": "network-comp"}]}},
                 {"id": "instance-b", "cpuPercent": None, "memoryPercent": None, "networkBytesOut": None,
                  "details": {"metricsAsOf": None, "vnics": []}}]

    def metrics(compartment_id, details, **kw):
        if details.query.startswith("CpuUtilization"):
            return response([stream("instance-a", [point(20, day=7), point(0)]), stream("instance-b", [point(float("nan"))])])
        if details.query.startswith("MemoryUtilization"):
            return response([])
        assert details.namespace == "oci_vcn"
        assert details.query == "VnicToNetworkBytes[1h].sum()"
        assert compartment_id == "network-comp"
        return response([stream("vnic-a", [point(100, day=7), point(200), point(-1), point(float("inf"))]),
                         stream("vnic-a", [point(200)]), stream("nlb-unrelated-vnic", [point(999999)])])

    service(cloud, "monitoring").handlers["summarize_metrics_data"] = metrics
    days, dates = c.metrics("region-a/app", service(cloud, "monitoring"), "app", resources)
    assert days == {"2026-10-07": 100, "2026-10-08": 200}
    assert len(dates) == 2
    assert resources[0]["networkBytesOut"] == 300
    assert resources[0]["cpuPercent"] == 0
    assert resources[0]["memoryPercent"] is None
    assert resources[1]["networkBytesOut"] is None
    assert resources[1]["cpuPercent"] is None


def usage_row(day, amount, service_name="Compute", currency="USD"):
    start = datetime.fromisoformat(day).replace(tzinfo=UTC)
    return NS(time_usage_started=start, time_usage_ended=start + timedelta(days=1),
              computed_amount=amount, service=service_name, currency=currency)


def test_usage_all_pages_daily_service_totals_delayed_asof_and_no_forecast():
    cloud = fake_cloud()
    usage = service(cloud, "usage")

    def query(details, **kw):
        assert details.query_type == "COST"
        assert details.group_by == ["service"]
        assert details.time_usage_ended == NOW.replace(hour=0)
        if kw.get("page"):
            return response(NS(items=[usage_row("2026-10-02", 4, "Storage"), usage_row("2026-10-02", -1)]))
        return response(NS(items=[usage_row("2026-09-01", 9), usage_row("2026-10-01", 2)]), page="next")

    usage.handlers["request_summarized_usages"] = query
    result = collector(cloud).cost("region-a")
    assert result["monthToDate"] == 5
    assert result["previousMonth"] == 9
    assert result["daily"] == [{"date": "2026-10-01", "amount": 2}, {"date": "2026-10-02", "amount": 3}]
    assert result["byService"] == [{"name": "Storage", "amount": 4}, {"name": "Compute", "amount": 1}]
    assert result["asOf"] == "2026-10-03T00:00:00Z"
    assert result["forecast"] is None


def test_mixed_currency_is_never_summed():
    cloud = fake_cloud()
    service(cloud, "usage").handlers["request_summarized_usages"] = response(NS(items=[usage_row("2026-10-01", 1), usage_row("2026-10-01", 2, currency="EUR")]))
    c = collector(cloud)
    assert c.cost("region-a")["monthToDate"] is None
    assert c.errors[0]["scope"] == "usage/currency"


@pytest.mark.parametrize("action,state,provider_action", [
    ("instance.start", "STOPPED", "START"), ("instance.stop", "RUNNING", "SOFTSTOP"),
    ("instance.reboot", "RUNNING", "SOFTRESET")])
def test_power_actions_use_sdk_allowlist_and_conditional_fresh_resource(action, state, provider_action):
    cloud = fake_cloud()
    set_instance(cloud, state=state)
    calls = []

    def mutation(instance_id, action, **kw):
        calls.append((instance_id, action, kw))
        return response()

    service(cloud, "compute").handlers["instance_action"] = mutation
    prepared = cloud.prepare_action(action, "region-a", "synthetic-instance", {})
    assert prepared["requiresText"] == ("合成实例" if state == "RUNNING" else None)
    result = cloud.execute_action(action, "region-a", "synthetic-instance", {}, prepared["etag"], prepared["context"])
    assert result["status"] == "submitted"
    assert calls[0][1] == provider_action
    assert calls[0][2]["if_match"] == "v1"
    assert isinstance(calls[0][2]["retry_strategy"], oci.retry.NoneRetryStrategy)
    assert len([c for c in service(cloud, "compute").calls if c[0] == "get_instance"]) == 2


@pytest.mark.parametrize("action,params", [("instance.terminate", {}), ("shell.exec", {"cmd": "false"}),
    ("instance.start", {"unapproved": True}), ("instance.rename", {"displayName": " "}),
    ("instance.rename", {"displayName": "bad\nname"}), ("instance.rename", {"displayName": " good "}),
    ("nlb.backend.disable", {"backendSetName": "x", "backendName": ""})])
def test_invalid_operations_are_rejected_before_any_sdk_call(action, params):
    cloud = fake_cloud()
    with pytest.raises(CloudError):
        cloud.prepare_action(action, "region-a", "synthetic-instance", params)
    assert all(not client.calls for client in cloud._clients.values())


@pytest.mark.parametrize("state", ["STARTING", "STOPPING", "TERMINATED", "TERMINATING", "UNKNOWN_ENUM_VALUE"])
def test_busy_or_terminal_instance_state_is_rejected(state):
    cloud = fake_cloud()
    set_instance(cloud, state=state)
    with pytest.raises(CloudError, match="状态"):
        cloud.prepare_action("instance.rename", "region-a", "synthetic-instance", {"displayName": "new"})


def test_stale_etag_or_changed_params_do_not_mutate():
    cloud = fake_cloud()
    set_instance(cloud)
    prepared = cloud.prepare_action("instance.rename", "region-a", "synthetic-instance", {"displayName": "new"})
    set_instance(cloud, etag="v2")
    with pytest.raises(CloudError) as err:
        cloud.execute_action("instance.rename", "region-a", "synthetic-instance", {"displayName": "new"}, prepared["etag"], prepared["context"])
    assert err.value.code == "stale_resource"
    set_instance(cloud)
    with pytest.raises(CloudError):
        cloud.execute_action("instance.rename", "region-a", "synthetic-instance", {"displayName": "different"}, prepared["etag"], prepared["context"])
    assert not [c for c in service(cloud, "compute").calls if c[0] == "update_instance"]


def test_missing_confirmation_etag_and_unsubscribed_region_fail_closed():
    cloud = fake_cloud()
    set_instance(cloud, etag=None)
    with pytest.raises(CloudError) as err:
        cloud.prepare_action("instance.stop", "region-a", "synthetic-instance", {})
    assert err.value.code == "etag_unavailable"
    with pytest.raises(CloudError) as err:
        cloud.execute_action("instance.stop", "region-a", "synthetic-instance", {})
    assert err.value.code == "confirmation_required"
    with pytest.raises(CloudError) as err:
        cloud.prepare_action("instance.stop", "region-never-subscribed", "synthetic-instance", {})
    assert err.value.code == "invalid_region"


def setup_backend(cloud, *, drain=False, offline=False):
    nlb = service(cloud, "nlb")
    parent = NS(id="synthetic-nlb", display_name="入口", lifecycle_state="ACTIVE")
    backend = NS(name="192.0.2.1:443", ip_address="192.0.2.1", port=443, weight=7,
                 is_drain=drain, is_offline=offline, is_backup=True)
    nlb.handlers["get_network_load_balancer"] = response(parent, etag="parent-v1")
    nlb.handlers["get_backend"] = response(backend, etag="backend-v1")
    return nlb, parent, backend


@pytest.mark.parametrize("action,drain,offline", [("nlb.backend.disable", False, False), ("nlb.backend.enable", True, True)])
def test_nlb_updates_preserve_backend_configuration_and_use_actual_sdk_argument_order(action, drain, offline):
    cloud = fake_cloud()
    nlb, _, _ = setup_backend(cloud, drain=drain, offline=offline)
    calls = []

    def update(network_load_balancer_id, update_backend_details, backend_set_name, backend_name, **kw):
        assert isinstance(update_backend_details, oci.network_load_balancer.models.UpdateBackendDetails)
        calls.append((update_backend_details, backend_set_name, backend_name, kw))
        return response()

    nlb.handlers["update_backend"] = update
    params = {"backendSetName": "home", "backendName": "192.0.2.1:443"}
    prepared = cloud.prepare_action(action, "region-a", "synthetic-nlb", params)
    cloud.execute_action(action, "region-a", "synthetic-nlb", params, prepared["etag"], prepared["context"])
    model, set_name, backend_name, kw = calls[0]
    assert model.is_drain is action.endswith("disable")
    assert model.is_offline is False
    assert model.weight == 7 and model.is_backup is True
    assert set_name == "home" and backend_name == params["backendName"]
    assert kw["if_match"] == "backend-v1"


def test_nlb_parent_change_invalidates_confirmation_and_already_draining_is_noop():
    cloud = fake_cloud()
    nlb, parent, _ = setup_backend(cloud, drain=True)
    params = {"backendSetName": "home", "backendName": "192.0.2.1:443"}
    prepared = cloud.prepare_action("nlb.backend.disable", "region-a", "synthetic-nlb", params)
    assert cloud.execute_action("nlb.backend.disable", "region-a", "synthetic-nlb", params, prepared["etag"], prepared["context"])["status"] == "succeeded"
    nlb.handlers["get_network_load_balancer"] = response(parent, etag="parent-v2")
    with pytest.raises(CloudError) as err:
        cloud.execute_action("nlb.backend.disable", "region-a", "synthetic-nlb", params, prepared["etag"], prepared["context"])
    assert err.value.code == "stale_resource"
    assert not [c for c in nlb.calls if c[0] == "update_backend"]


def test_sdk_precondition_failure_after_fresh_read_is_safe_and_not_retried():
    cloud = fake_cloud()
    set_instance(cloud)
    calls = []

    def mutation(*args, **kwargs):
        calls.append(1)
        raise oci.exceptions.ServiceError(412, "NoEtagMatch", {}, "SYNTHETIC-PRIVATE-REQUEST")

    service(cloud, "compute").handlers["instance_action"] = mutation
    p = cloud.prepare_action("instance.stop", "region-a", "synthetic-instance", {})
    with pytest.raises(CloudError) as error:
        cloud.execute_action("instance.stop", "region-a", "synthetic-instance", {}, p["etag"], p["context"])
    assert error.value.code == "stale_resource"
    assert "PRIVATE" not in str(error.value)
    assert calls == [1]


def test_deadline_prevents_further_provider_calls_and_limits_global_concurrency():
    cloud = fake_cloud()
    called = []
    with pytest.raises(CloudError):
        cloud._call(lambda **kw: called.append(1), deadline=time.monotonic() - 1)
    assert not called
    lock = threading.Lock()
    active, peak = 0, 0

    def slow(**kw):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(.02)
        with lock:
            active -= 1
        return response()

    threads = [threading.Thread(target=lambda: cloud._call(slow)) for _ in range(9)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak <= cloud._workers


def test_demo_snapshot_all_views_and_isolated_mutation():
    demo = DemoCloudClient()
    snapshot = demo.collect()
    assert snapshot["mode"] == "demo" and len(snapshot["resources"]) >= 7
    assert snapshot["traffic"]["officialMonthBytes"] is None
    assert snapshot["cost"]["forecast"] is None
    target = next(r for r in snapshot["resources"] if r["id"] == "demo-instance-home")
    p = demo.prepare_action("instance.rename", target["region"], target["id"], {"displayName": "新名称"})
    result = demo.execute_action("instance.rename", target["region"], target["id"], {"displayName": "新名称"}, p["etag"], p["context"])
    assert result["status"] == "succeeded"
    assert target["name"] != "新名称"  # Returned snapshots cannot mutate provider state.
    assert next(r for r in demo.collect()["resources"] if r["id"] == target["id"])["name"] == "新名称"
    with pytest.raises(CloudError):
        demo.execute_action("instance.rename", target["region"], target["id"], {"displayName": "新名称"}, p["etag"], p["context"])
    json.dumps(demo_snapshot(NOW), allow_nan=False)


def test_configuration_is_private_and_region_client_options_are_bounded(monkeypatch):
    config = {"tenancy": "synthetic-tenancy", "region": "region-a"}
    reads, created = [], []

    def read_config(**kwargs):
        reads.append(kwargs)
        return config

    def construct(cfg, **kwargs):
        created.append((cfg, kwargs))
        return NS()

    monkeypatch.setattr(oci.config, "from_file", read_config)
    monkeypatch.setattr(oci.config, "validate_config", lambda _: None)
    monkeypatch.setattr(oci.identity, "IdentityClient", construct)
    cloud = CloudClient("synthetic-config-never-opened", "TEST", max_workers=100)
    assert cloud._workers == 8
    cloud._client("identity", "region-b")
    assert reads == [{"file_location": "synthetic-config-never-opened", "profile_name": "TEST"}]
    assert created[0][0]["region"] == "region-b"
    assert config["region"] == "region-a"
    assert created[0][1]["timeout"] == (5, 20)
    assert isinstance(created[0][1]["retry_strategy"], oci.retry.NoneRetryStrategy)


def test_configuration_exception_never_exposes_original_message(monkeypatch):
    def invalid_config(**kwargs):
        raise RuntimeError("SYNTHETIC-PRIVATE-KEY-CONTENT")

    monkeypatch.setattr(oci.config, "from_file", invalid_config)
    with pytest.raises(CloudError) as error:
        CloudClient("synthetic-config-never-opened")
    assert error.value.code == "cloud_config"
    assert "PRIVATE" not in str(error.value)


def test_partial_region_failure_is_visible_without_discarding_inventory():
    cloud = fake_cloud()
    service(cloud, "compute").handlers["list_instances"] = response([instance()])

    def forbidden(**kwargs):
        raise oci.exceptions.ServiceError(403, "Forbidden", {}, "SYNTHETIC-PRIVATE-DIAGNOSTIC")

    service(cloud, "block").handlers["list_volumes"] = forbidden
    snapshot = collector(cloud).collect()
    assert any(r["kind"] == "instance" for r in snapshot["resources"])
    assert snapshot["regions"][0]["status"] == "error"
    assert any(alert["id"] == "partial-data" for alert in snapshot["alerts"])
    assert "PRIVATE" not in json.dumps(snapshot)


def test_rename_noop_and_sdk_model_preserve_explicit_name():
    cloud = fake_cloud()
    set_instance(cloud)
    params = {"displayName": "合成实例"}
    p = cloud.prepare_action("instance.rename", "region-a", "synthetic-instance", params)
    assert cloud.execute_action("instance.rename", "region-a", "synthetic-instance", params, p["etag"], p["context"])["status"] == "succeeded"
    assert not [c for c in service(cloud, "compute").calls if c[0] == "update_instance"]
    params = {"displayName": "应用 · 新名称"}
    p = cloud.prepare_action("instance.rename", "region-a", "synthetic-instance", params)
    cloud.execute_action("instance.rename", "region-a", "synthetic-instance", params, p["etag"], p["context"])
    _, args, kwargs = next(c for c in service(cloud, "compute").calls if c[0] == "update_instance")
    assert isinstance(args[1], oci.core.models.UpdateInstanceDetails)
    assert args[1].display_name == params["displayName"]
    assert kwargs["if_match"] == "v1"


def outbound_row(quantity=1, unit="GB", sku="B88327", name="Outbound Data Transfer Zone 1", day="2026-10-01", service_name="Virtual Cloud Network", tier=None):
    start = datetime.fromisoformat(day).replace(tzinfo=UTC)
    return NS(time_usage_started=start, time_usage_ended=start + timedelta(days=1),
              computed_quantity=quantity, computed_amount=0.0, unit=unit, sku_part_number=sku,
              sku_name=name, service=service_name, overages_flag=tier)


def test_official_usage_queries_all_pages_and_counts_free_gb_months_without_inventing_byte_basis():
    cloud = fake_cloud()
    queries = []

    def query(details, **kwargs):
        queries.append(details)
        assert details.query_type == "USAGE"
        assert details.group_by == ["service", "skuName", "skuPartNumber", "unit"]
        assert details.time_usage_started == NOW.replace(day=1, hour=0)
        assert details.time_usage_ended == NOW.replace(hour=0)
        assert details.is_aggregate_by_time is False
        if kwargs.get("page"):
            return response(NS(items=[outbound_row("2.5", "GB Months", day="2026-10-02")]))
        return response(NS(items=[outbound_row("1.25", "GB Months")]), page="next")

    service(cloud, "usage").handlers["request_summarized_usages"] = query
    result = collector(cloud).outbound_usage("region-a")
    assert len(queries) == 2
    assert result["officialQuantity"] == 3.75
    assert result["officialUnit"] == "GB Months"
    assert result["officialMonthBytes"] is None
    assert result["officialStatus"] == "unit_unverified"
    assert result["officialSource"] == "usage_api"
    assert result["officialAsOf"] == "2026-10-03T00:00:00Z"
    assert result["officialSkus"][0]["quantity"] == 3.75


@pytest.mark.parametrize("unit,factor", [("GB", 10**9), ("GiB", 2**30), ("MB", 10**6), ("MiB", 2**20), ("Bytes", 1)])
def test_explicit_transfer_units_have_distinct_decimal_binary_factors(unit, factor):
    cloud = fake_cloud()
    service(cloud, "usage").handlers["request_summarized_usages"] = response(NS(items=[outbound_row(2, unit)]))
    result = collector(cloud).outbound_usage("region-a")
    assert result["officialMonthBytes"] == 2 * factor
    assert result["officialQuantity"] == 2
    assert result["officialUnit"] == unit
    assert result["officialStatus"] == "available"


def test_official_usage_excludes_ingress_processed_storage_and_unrelated_product_outbound():
    cloud = fake_cloud()
    rows = [outbound_row(5), outbound_row(999, sku="SYNTHETIC-IN", name="Inbound Data Transfer"),
            outbound_row(999, sku="SYNTHETIC-NLB", name="Network Load Balancer Processed Bytes", service_name="Network Load Balancer"),
            outbound_row(999, sku="SYNTHETIC-STORAGE", name="Storage Capacity", service_name="Block Storage"),
            outbound_row(999, sku="SYNTHETIC-DB", name="MySQL Database Outbound Data Transfer", service_name="MySQL")]
    service(cloud, "usage").handlers["request_summarized_usages"] = response(NS(items=rows))
    result = collector(cloud).outbound_usage("region-a")
    assert result["officialMonthBytes"] == 5 * 10**9
    assert len(result["officialSkus"]) == 1


def test_official_usage_unknown_vcn_transfer_sku_makes_total_incomplete():
    cloud = fake_cloud()
    rows = [outbound_row(5), outbound_row(7, sku="SYNTHETIC-UNKNOWN", name="Outbound Data Transfer New Zone")]
    service(cloud, "usage").handlers["request_summarized_usages"] = response(NS(items=rows))
    c = collector(cloud)
    result = c.outbound_usage("region-a")
    assert result["officialMonthBytes"] is None
    assert result["officialQuantity"] is None
    assert result["officialStatus"] == "partial"
    assert result["officialSkus"][0]["quantity"] == 5
    assert c.errors[0]["scope"] == "usage/outbound/classification"


def test_official_usage_mixed_known_units_convert_bytes_but_never_sum_raw_quantity():
    cloud = fake_cloud()
    rows = [outbound_row(1, "GB"), outbound_row(1, "GiB", sku="B93455", name="Outbound Data Transfer Zone 2")]
    service(cloud, "usage").handlers["request_summarized_usages"] = response(NS(items=rows))
    result = collector(cloud).outbound_usage("region-a")
    assert result["officialMonthBytes"] == 10**9 + 2**30
    assert result["officialQuantity"] is None and result["officialUnit"] is None


@pytest.mark.parametrize("quantity,unit", [(None, "GB"), (-1, "GB"), (float("nan"), "GB"), (3, "GB Hours")])
def test_official_unknown_quantity_or_unit_never_becomes_zero_or_assumed_bytes(quantity, unit):
    cloud = fake_cloud()
    service(cloud, "usage").handlers["request_summarized_usages"] = response(NS(items=[outbound_row(quantity, unit)]))
    result = collector(cloud).outbound_usage("region-a")
    assert result["officialMonthBytes"] is None
    assert result["officialStatus"] in {"partial", "unit_unverified"}


def test_official_pagination_failure_preserves_raw_items_but_not_partial_month_total():
    cloud = fake_cloud()

    def query(details, **kwargs):
        if kwargs.get("page"):
            raise oci.exceptions.ServiceError(403, "Forbidden", {}, "SYNTHETIC-PRIVATE-ERROR")
        return response(NS(items=[outbound_row(5)]), page="next")

    service(cloud, "usage").handlers["request_summarized_usages"] = query
    result = collector(cloud).outbound_usage("region-a")
    assert result["officialStatus"] == "partial"
    assert result["officialMonthBytes"] is None and result["officialQuantity"] is None
    assert result["officialSkus"][0]["quantity"] == 5
    assert "PRIVATE" not in json.dumps(result)


def test_official_duplicate_groups_are_deduped_and_explicit_tiers_are_disjoint():
    cloud = fake_cloud()
    rows = [outbound_row(10, tier="N"), outbound_row(10, tier="N"), outbound_row(2, tier="Y")]
    service(cloud, "usage").handlers["request_summarized_usages"] = response(NS(items=rows))
    result = collector(cloud).outbound_usage("region-a")
    assert result["officialQuantity"] == 12
    assert result["officialMonthBytes"] == 12 * 10**9
    rows.append(outbound_row(11, tier="N"))
    result = collector(cloud).outbound_usage("region-a")
    assert result["officialStatus"] == "partial"
    assert result["officialMonthBytes"] is None
    # A total plus one explicit tier cannot be summed safely.
    service(cloud, "usage").handlers["request_summarized_usages"] = response(NS(items=[outbound_row(12), outbound_row(10, tier="N")]))
    result = collector(cloud).outbound_usage("region-a")
    assert result["officialStatus"] == "partial"
    assert result["officialMonthBytes"] is None


def test_full_snapshot_attempts_usage_and_keeps_official_and_monitoring_fields_distinct():
    cloud = fake_cloud()

    def query(details, **kwargs):
        return response(NS(items=[outbound_row(2)] if details.query_type == "USAGE" else []))

    service(cloud, "usage").handlers["request_summarized_usages"] = query
    snapshot = collector(cloud).collect()
    traffic = snapshot["traffic"]
    assert traffic["officialMonthBytes"] == 2 * 10**9
    assert traffic["officialQuantity"] == 2
    assert traffic["source"] == "billing"
    assert traffic["officialAsOf"] == traffic["asOf"]
    assert traffic["todayBytes"] is None and traffic["monthBytes"] is None
    assert traffic["freeAllowanceBytes"] is None
    assert snapshot["cost"]["monthToDate"] is None
    assert {args[0].query_type for name, args, _ in service(cloud, "usage").calls if name == "request_summarized_usages"} == {"COST", "USAGE"}
    json.dumps(snapshot, allow_nan=False)


def test_official_explicit_zero_is_distinct_from_no_rows_and_first_day_has_no_completed_daily_window():
    cloud = fake_cloud()
    service(cloud, "usage").handlers["request_summarized_usages"] = response(NS(items=[outbound_row(0)]))
    assert collector(cloud).outbound_usage("region-a")["officialMonthBytes"] == 0
    service(cloud, "usage").handlers["request_summarized_usages"] = response(NS(items=[]))
    assert collector(cloud).outbound_usage("region-a")["officialMonthBytes"] is None
    c = collector(cloud)
    c.now = NOW.replace(day=1)
    before = len(service(cloud, "usage").calls)
    result = c.outbound_usage("region-a")
    assert result["officialMonthBytes"] is None
    assert "尚无已结束" in result["officialNote"]
    assert len(service(cloud, "usage").calls) == before
