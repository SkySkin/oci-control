# OCI 接入与数据口径

云境通过官方 Python `oci` SDK 访问 OCI；不调用 CLI 或 shell 执行云操作。安装要求 Python 3.10+。配置、签名密钥、密码及运行快照必须位于仓库之外；浏览器与 Android 只接收授权后的资源快照，不接收 OCI 凭据。

在服务器设置 `OCI_CONFIG_FILE` 和 `OCI_PROFILE`，例如使用运行目录下的标准 OCI SDK 配置文件。配置包含的 `key_file` 应指向同样位于仓库之外、仅服务用户可读的私钥。请按 OCI 官方流程创建专用 API 身份，不要使用租户管理员密钥。云境不会改写现有 OCI 配置、全局环境变量或共享 CLI 默认值。

## 权限与覆盖范围

SDK 先读取租户、订阅区域和 `ACCESSIBLE` 的全部嵌套区间，然后逐区域、逐区间采集。根区间也会单独读取。资源在何处可见取决于 API 身份的实际 IAM 授权；读取区间列表本身不代表能读取该区间所有服务。列举失败、区域未就绪及部分服务权限不足会写入快照 `errors`，成功的结果仍保留。空列表伴随错误时不能解释为没有资源。

IAM 策略应根据部署的区间和身份配置。以下使用**合成组名**，是只读策略模板，不是要求授予整租户管理员权限；可将资源策略的 `in tenancy` 缩小为实际区间范围。

```text
Allow group OCIControlReaders to inspect tenancies in tenancy
Allow group OCIControlReaders to inspect compartments in tenancy
Allow group OCIControlReaders to read instances in tenancy
Allow group OCIControlReaders to read virtual-network-family in tenancy
Allow group OCIControlReaders to read volume-family in tenancy
Allow group OCIControlReaders to read load-balancers in tenancy
Allow group OCIControlReaders to read network-load-balancers in tenancy
Allow group OCIControlReaders to read buckets in tenancy
Allow group OCIControlReaders to read objectstorage-namespaces in tenancy
Allow group OCIControlReaders to read metrics in tenancy
Allow group OCIControlReaders to read usage-report in tenancy
```

费用权限可能由租户的成本管理和组织账单权限进一步限制；请对照 OCI 当前 IAM 文档配置。云境不会将费用读取失败转换为 0。写操作需要额外授予目标区间的相应 OCI 权限；仅有以上读取权限时可以查看，但执行操作会被 OCI 拒绝。应用的操作白名单不能替代 IAM。建议为此身份配置受限策略，仅允许所需实例的电源操作和显示名称更新、所需 NLB 的后端更新，不授予终止或删除权限。

采集内容：

- Compute 实例：形状、OCPU、内存、生命周期、VNIC 主/辅助 IPv4 地址与 IPv6 地址；不读取实例登录凭据、元数据或用户数据。
- NLB 与普通 LB：地址、监听器、后端集、各后端状态、排空/离线标志、健康检查配置及服务报告的健康状态。跨区域后端按实际地址展示，不把 NLB 所在区域当作实例区域。
- 各可用域的启动卷、块存储卷、对象存储桶、VCN。桶大小与对象数量为 OCI 提供的近似值；不列举或读取对象内容。
- Compute Agent 的 CPU/内存指标，以及实例关联 VNIC 的网络指标。代理没有开启、停止中的实例、权限缺失或无采样时保留 `null`。

`details.backendSets` 固定为数组：

```json
[{"name":"synthetic-home","policy":"FIVE_TUPLE","health":"OK","healthChecker":{"protocol":"TCP","port":443,"urlPath":null},"backends":[{"name":"192.0.2.20:443","ipAddress":"192.0.2.20","port":443,"isOffline":false,"isDrain":false,"isBackup":false,"weight":1,"health":"OK","targetId":null}]}]
```

示例地址来自文档保留网段。实际授权资源的 IP 会出现在运行快照中，运行快照必须保持私有，不能提交至仓库。后端集仅返回整体异常而不能确定个别后端健康时，个别后端 `health` 为 `null`，不推定正常。

## 费用与流量不能混用

费用来自 Usage API 的 `COST` 日汇总，按 `service` 分组，使用 UTC 日界。查询覆盖上一自然月及本月已经结束的日期；`monthToDate`、`previousMonth`、`daily`、`byService` 均为 API 已报告的金额。信用调整可能产生负值。币种缺失或混合时不合并金额。`asOf` 是返回数据的最新区间结束时间，不是查询发起时间。费用会延迟、补录和调整；缺失日期不填假零，部分分页失败时保留已取得数据并报告错误。

本版不生成费用预测，`forecast` 为 `null`。无法确认免费资格、配额及结算口径时，`freeEligible`、`freeAllowanceBytes` 为 `null`。没有硬预算封顶保证。不能把所有 Usage API 数量单位中带 GB 的项目视为出站流量；存储容量等项目也可能使用 GB 单位。

官方出站另行请求 Usage API 的 **`USAGE`**（不是 `COST`），按 `service / skuName / skuPartNumber / unit` 分组，读取本月已结束 UTC 日期的全部分页。若本月尚无已结束日期，暂不发起零长度日查询。本版只纳入下列已经在 Oracle 公共产品目录和服务说明确认的 **VCN 出站** SKU；服务须为 VCN，名称也必须明确为 `Outbound Data Transfer`：

| SKU | 官方产品范围 |
| --- | --- |
| `B88327` | 北美、欧洲与英国始发；Usage 名称可能为 `Outbound Data Transfer Zone 1` |
| `B93455` | APAC、日本和南美始发 |
| `B93456` | 中东与非洲始发 |

这些 SKU 各自使用同一个产品号包含免费与超额阶梯，因此会纳入 `computed_amount=0` 的 `computed_quantity`，不通过费用是否为零筛选。无需额外叠加一个“免费用量”估计。若 API 明确返回不重叠的免费/超额标志，可合计其数量；完全相同的分组重复项只计一次。总计行与同组阶梯行同时出现、同组数量冲突、未知 VCN 传输 SKU、数量缺失或分页失败时，不输出假装完整的总量。入站、NLB/LB/防火墙处理字节、存储容量以及其他产品的专属出站 SKU 不纳入本项。

返回值除了 `officialMonthBytes`，还提供可选字段：

- `officialQuantity` / `officialUnit`：完整读取且单位一致时，官方原始数量合计与原始单位。多单位不能直接加成一个数量，保留空值。
- `officialAsOf`：识别到的官方日用量最后结束时间；与 Monitoring 的时间分别保留。新开通的 NLB 和当天流量暂不出现在日账单中是可能的，不能据此判断无流量。
- `officialSource: "usage_api"`；`officialStatus` 为 `available`、`unit_unverified`、`partial` 或 `unavailable`。
- `officialSkus`：已识别的 `{skuPartNumber, skuName, service, unit, quantity}` 原始合计项。总状态为 `partial` 时，这些项仅供说明已取得的数据，不是全月总量。
- `officialNote`：该次查询的范围、单位和延迟说明。`traffic.source` / `asOf` 优先描述 Monitoring；只有官方数据时来源为 `billing`。`todayBytes / monthBytes / daily` 始终保持 Monitoring 估计，不挪用官方数据填充。

明确的 SI 单位 `GB / MB / TB` 分别乘以 10⁹ / 10⁶ / 10¹²；明确的 `GiB / MiB / TiB` 分别乘以 2³⁰ / 2²⁰ / 2⁴⁰。不同明确单位可以换算后合计字节，但不合并原始数量。

**`GB Months` 特殊情况：** 已确认 VCN 出站 SKU 可能以此单位返回日用量。产品目录的对应计量名为 `Gigabyte Outbound Data Transfer Per Month`，因此保留并合计原始数量，不乘日数/月数，也不按存储 GB-month 的时间平均方法处理。Oracle 服务说明 V092326 第 16 页定义它是自然月内的出站传输数量，包括互联网及跨 OCI 区域传输；该条定义没有给出字节乘数。相邻存储条目的二进制定义不能直接挪用到出站。因此在没有更明确依据时，此单位返回 `officialQuantity`、`officialUnit="GB Months"`、`officialStatus="unit_unverified"`，同时 `officialMonthBytes=null`，不静默假定 SI 或二进制基数。

公共目录显示这些 SKU 有从 0 到 10240 的免费价格档，但这本身不能证明当前账户的免费额度是在区域、租户、订阅或组织层级如何共享。因此本版不硬编码“剩余 10 TB”、已用免费额度比例或硬性限额；官方已报告数量本身可以显示。使用自定义合同的账户应以自身账单与 OCI 成本管理为准。

CPU/内存使用 `oci_computeagent` 的 `CpuUtilization[5m].mean()` 与 `MemoryUtilization[5m].mean()`，取最近一小时内的最新样本。每个指标的时间位于资源 `details.cpuPercentAsOf` / `memoryPercentAsOf`，不是实时值。

网络使用 `oci_vcn` 的 `VnicToNetworkBytes[1h].sum()`，读取本月数据并按 UTC 日期汇总。只计实例已关联的 VNIC；不加上 NLB/LB 处理字节，避免同一转发链路在入口和实例重复汇总。VNIC 处于其他区间时按 VNIC 的区间查询指标。

这些值仍然是**监控出站估计**：含内网、跨区域、发往其他实例以及丢包前字节；跨实例转发可能在多张网卡观察到同一业务流。没有对业务流量进行端到端去重，也不等于公网计费出站、已用免费额度或精确实时流量。`NetworksBytesOut` 是 Compute Agent 会话累积计数器，本版不会直接求和该计数器。缺少 VNIC 权限或样本会使估计不完整。

## 操作与确认

只允许以下六项操作，均通过官方 SDK：

| 应用操作 | OCI 调用 | 条件 |
| --- | --- | --- |
| `instance.start` | `instance_action(..., "START")` | `STOPPED` |
| `instance.stop` | `instance_action(..., "SOFTSTOP")` | `RUNNING` |
| `instance.reboot` | `instance_action(..., "SOFTRESET")` | `RUNNING` |
| `instance.rename` | `update_instance` 的 `display_name` | `RUNNING` 或 `STOPPED` |
| `nlb.backend.disable` | `update_backend` 设置 `is_drain=true` | 父 NLB `ACTIVE` |
| `nlb.backend.enable` | `update_backend` 设置 `is_drain=false, is_offline=false` | 父 NLB `ACTIVE` |

排空后端用于停止分配新连接，不强制终止已有连接。更新保留地址、端口、权重、备份标志及不需要变更的配置。后端参数固定为 `{backendSetName, backendName}`；显示名称参数固定为 `{displayName}`。额外参数、任意方法名称、shell 命令以及 delete/terminate 操作均不接受。

准备阶段重新读取区域订阅、目标与 ETag；执行阶段再次读取相同目标，并比较完整确认上下文与 ETag，再将 `if_match` 传给 SDK。如果版本变化、目标状态不可操作或服务没有提供 ETag，就拒绝执行并要求重新确认。后端上下文还绑定父 NLB 的 ETag。服务端 API 负责权限、绑定会话的确认记录、输入确认文字、原子幂等键及审计。SDK 不重试写操作；请求已发送但响应丢失时，必须先刷新并检查审计和资源状态，不能假设操作没有发生。

接口返回 `submitted` 只表示 OCI 已接收，不能当作资源已完成启动、停止或修改。同名重命名和已经处于目标排空/启用状态的操作在重新确认版本后作为无修改成功处理。演示模式使用独立内存数据；不会构建 OCI 客户端或执行云写入。

## 性能与失败边界

默认最多 4 个 SDK 请求并发，连接超时 5 秒、读取超时 20 秒；关闭 SDK 自动重试以避免采集和写操作意外放大。采集软时限 180 秒，达到时限后不再发新请求，最后在途网络请求仍可能等待自身超时。因此大租户或持续慢响应可能得到部分清单，可按错误范围定位权限或连接问题。所有提供 `opc-next-page` 的列表接口使用全部页面；SDK 的 Monitoring 汇总接口本身没有分页参数。

API 身份、资源规模和 OCI 限流决定实际采集耗时。一次刷新失败不会授权删除已有离线快照；API 层负责保留旧快照并展示原始时间戳。OCI 原始异常、请求 URL、配置和签名内容不会输出到公共错误消息。

## 开发验证

```sh
.venv/bin/python -m pytest tests/test_cloud.py -q
```

测试使用合成 SDK 响应，校验跨区域/嵌套区间、分页、部分失败、空指标、费用币种、流量去重范围、SDK 操作参数、ETag 与状态变化、并发时限及内存演示。测试不会读取真实配置、调用网络或修改 OCI 资源。真实账户只读验收由部署集成方单独运行；任何云写入都应通过用户明确确认的操作流程。

新增证据：[Oracle 公共产品目录](https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/)（2026-10-08 核验产品号、出站月计量名及阶梯）、[Oracle 云服务说明 PDF](https://www.oracle.com/contracts/docs/paas_iaas_universal_credits_3940775.pdf)（V092326，第 16 页定义、第 243 页 SKU 表）、[网络价格](https://www.oracle.com/cloud/networking/pricing/)。

参考：[Compute 指标](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computemetrics.htm)、[VNIC 指标](https://docs.oracle.com/en-us/iaas/Content/Network/Reference/vnicmetrics.htm)、[Monitoring 查询语言](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Reference/mql.htm)、[Python SDK](https://docs.oracle.com/en-us/iaas/tools/python/latest/)。

新增官方用量测试覆盖 USAGE 查询与分页、零费用用量、GB Months 原始单位保留、GB/GiB 区分、入站/处理字节排除、未知 SKU、混合单位、重复与重叠阶梯、部分失败及独立时间戳；所有数据均为合成。
