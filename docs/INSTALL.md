# 安装与运行

本文适用于 **云境 OCI Control 0.1.0**。示例域名与地址均为占位示例。所有运行数据和秘密必须放在代码目录之外；公开仓库中不要保存真实部署信息。

## 选择方式

| 方式 | 适合 | 依赖 |
| --- | --- | --- |
| 原生 | 已有 Python/OCI CLI 的主机，方便 systemd 管理 | Python 3.10+（推荐 3.12）、venv、Node.js 22+、npm |
| Docker Compose | 隔离依赖、固定非 root 运行用户 | Docker Engine、Compose v2、可只读挂载的 OCI 配置 |
| Android | 连接上述自托管服务 | Android 6.0/API 23+；新系统与更新的 WebView 更稳妥 |

Node.js 只用于编译网页；Python 服务提供静态网页及 API。客户端不安装 OCI CLI，不接收 OCI 云密钥。源码安装不需要执行 `curl | sh`。从各项目官方渠道下载软件、核对来源后再安装。

## 原生安装

从本项目仓库获取源码，进入 checkout。Ubuntu/Debian 先通过系统软件源安装 Python、对应的 `python3-venv`、必要编译工具；Node.js 22 LTS 可从 [nodejs.org](https://nodejs.org/en/download) 获取并核验校验和。系统 Python 版本较旧时，可使用发行版支持的新版 Python 并设置 `PYTHON_BIN`。

```bash
export OCI_CONTROL_DATA_DIR="$HOME/.local/share/oci-control"
# 可选：export PYTHON_BIN=python3.12
./scripts/install-native.sh
```

安装脚本先创建项目 `.venv`，安装根目录锁定/约束的 Python 依赖，执行 `npm ci` 和网页构建，然后检查 OCI 配置是否存在。它只检测文件存在，不读取或输出配置内容，不自动运行云命令。首次安装最后调用 `python -m server configure`，交互读取密码且不回显。已有摘要时不自动重置密码。无需把密码作为命令参数或环境变量传入。

若使用手工安装，等价步骤为：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci --prefix web
npm run build --prefix web
export OCI_CONTROL_DATA_DIR="$HOME/.local/share/oci-control"
.venv/bin/python -m server configure
```

OCI CLI 已作为运行依赖安装在 `.venv/bin/oci`。也可遵循 [Oracle 官方安装说明](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm) 使用独立安装，不要求下载后立即执行未经审阅的安装脚本。

```bash
.venv/bin/oci setup config
```

根据官方引导创建专用 API 用户/密钥并上传公钥。私钥只保存在服务端，目录通常 `0700`、文件 `0600`。`OCI_CONFIG_FILE` 默认指向 `~/.oci/config`，`OCI_PROFILE` 默认 `DEFAULT`。多账户/现有 CLI 用户建议单独配置文件和 profile；不要改变共享配置或其他程序的全局默认值。私钥路径 `key_file` 必须可被服务运行用户读取。无头服务应使用它能非交互读取的专用受限凭据，不要在网页填入密钥口令。

配置错误或权限不足时，登录后查看连接状态/采集错误。完整授权范围和支持的资源见 [OCI.md](OCI.md)。采集只覆盖 API 用户可访问的资源；缺失项不能证明账户内不存在其他资源。

## IP、端口与 HTTP

默认服务监听 `127.0.0.1:8787`。直接本机 HTTP 开发：

```bash
export OCI_CONTROL_DATA_DIR="$HOME/.local/share/oci-control"
export OCI_CONTROL_PUBLIC_URL="http://127.0.0.1:8787"
export OCI_CONTROL_ALLOW_HTTP=true
./scripts/run-native.sh
```

可信局域网中通过服务器 IP 访问时，`OCI_CONTROL_HOST=0.0.0.0` 或指定 LAN 地址，`OCI_CONTROL_PUBLIC_URL` 设为客户端实际使用的 origin，例如 `http://192.0.2.10:8787`（文档示例 IP，需替换）。防火墙仅放行受信任网段到该端口，OCI 主机还需核对 NSG/安全列表及系统防火墙。

HTTP 必须显式启用 `OCI_CONTROL_ALLOW_HTTP=true`，Android 还需勾选连接页的风险确认。HTTP 会暴露网络上的密码、会话凭证和资源资料；公网访问推荐 HTTPS。不要混用不同 IP/域名访问同一部署：浏览器同源校验、会话与缓存依赖稳定的规范 URL。

## 自有域名与 HTTPS 反向代理

将自有域名解析到反向代理入口，只向外公开 `443`；服务仍绑定回环地址。设置：

```bash
export OCI_CONTROL_PUBLIC_URL="https://oci.example.com"
export OCI_CONTROL_ALLOW_HTTP=false
./scripts/run-native.sh
```

可使用 [Caddy 官方安装包](https://caddyserver.com/docs/install) 自动管理 HTTPS。下面是可审阅的 Caddyfile 示例；`oci.example.com` 必须换成你的域名：

```caddyfile
oci.example.com {
    reverse_proxy 127.0.0.1:8787
}
```

或使用现有 Nginx/Traefik，将同一 origin 的静态页面和 `/api/` 一并代理至服务，保留 `Host`/转发头，正确配置证书并避免缓存认证/API 响应。不要将 API 另置到无关域名后开放全站 CORS。内网代理到服务的 HTTP 不要求打开客户端 HTTP 登录开关，规范 URL 仍为 HTTPS。

## Cloudflare Tunnel

适合不直接公开源站端口的自有域名部署。按 [Cloudflare 官方文档](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) 安装 `cloudflared`，审阅包与来源，使用自己的 Cloudflare 账户创建命名 Tunnel，并把域名路由到本机服务。Tunnel 凭据和配置放在仓库外，例如 `~/.cloudflared/`。

可在 Cloudflare 控制台配置公开主机名，源站服务为 `http://127.0.0.1:8787`。若采用本地配置，其结构为：

```yaml
tunnel: <YOUR-TUNNEL-ID>
credentials-file: /absolute/private/path/tunnel.json
ingress:
  - hostname: oci.example.com
    service: http://127.0.0.1:8787
  - service: http_status:404
```

服务使用 `OCI_CONTROL_PUBLIC_URL=https://oci.example.com`、`OCI_CONTROL_ALLOW_HTTP=false`。将 `cloudflared` 注册为操作系统服务；不要把 Tunnel token 写进项目文件、截图或日志。公网 URL 应稳定，临时 quick tunnel 地址不适合长期会话与 Android 配置。

Tunnel 只提供网络入口，不替代面板登录。额外启用 Cloudflare Access 浏览器挑战时，原生 Android API 请求可能无法通过；0.1.0 没有 Access 服务令牌集成，不能把 Cloudflare 服务令牌塞入前端或 APK。请选择与原生 API 兼容的入口策略。

## Docker Compose

Compose 使用 `/data` 命名卷持久化密码摘要、会话、快照与审计。容器 UID/GID 均为 `10001`，根文件系统只读，临时文件仅写 `/tmp`，不需要特权模式或 Docker socket。

先在仓库外准备一个**独立的** OCI 配置目录。例如 `~/.config/oci-control/oci`，其中放 `config` 与专用私钥。不要复制其他账户资料进 checkout。容器将该目录只读挂载为 `/oci`，所以配置内写 `key_file=/oci/api_key.pem`，而非主机的 `/home/...` 路径。主机上的原有配置保持不变。

在 Linux 上，为容器 UID 授予读取权限。可以将专用目录/文件归属给 UID `10001` 后设置目录 `0700`、文件 `0600`，或者给 UID `10001` 添加最小 ACL；不要用全局可读 `0644` 暴露私钥。若 OCI CLI 发出权限检查提示，应核查真实权限与 ACL。macOS/Docker Desktop 的共享文件权限行为不同，需验证容器实际可读性。

```bash
export OCI_CONFIG_DIR="$HOME/.config/oci-control/oci"
export OCI_PROFILE=DEFAULT
export OCI_CONTROL_PUBLIC_URL="http://127.0.0.1:8787"
export OCI_CONTROL_ALLOW_HTTP=true
docker compose build
docker compose run --rm oci-control python -m server configure
docker compose up -d
docker compose ps
```

首次密码设置需要交互终端；不要使用 `-T`。如果只是演示，仍需创建一个空的 `OCI_CONFIG_DIR` 目录供只读挂载，并设置 `OCI_CONTROL_MODE=demo`，无需私钥或真实配置。

默认端口映射到 `127.0.0.1:8787`。可信 LAN 暴露时显式 `export OCI_CONTROL_BIND_IP=0.0.0.0`，并设置实际 `OCI_CONTROL_PUBLIC_URL`。`OCI_CONTROL_PORT` 控制主机映射端口，容器内部固定为 `8787`。反向代理/Tunnel 与容器在同一主机时，通常保持默认回环绑定。

若使用主机目录持久化，替换 Compose 中 `state:/data` 为仓库外的绝对路径，并先让 UID `10001` 对目录可写，权限建议 `0700`。不要把状态目录放进源码，也不要把 `/data` 整体开放给其他用户。挂载额外密码摘要文件需自行添加只读卷和 `OCI_CONTROL_PASSWORD_HASH_FILE` 环境项。

停止用 `docker compose down`，它会保留命名卷。**`docker compose down -v` 会删除状态卷**，包括当前会话和审计，不能作为普通升级命令。

## 环境变量

| 变量 | 默认/建议 | 用途 |
| --- | --- | --- |
| `OCI_CONTROL_DATA_DIR` | 脚本：`~/.local/share/oci-control`；容器：`/data` | 敏感运行数据；始终在 checkout 外 |
| `OCI_CONTROL_PASSWORD_HASH_FILE` | 数据目录的 `password.hash` | 可选外部摘要文件；通过交互配置生成 |
| `OCI_CONFIG_FILE` | 原生 `~/.oci/config`；容器 `/oci/config` | 服务端 OCI 配置 |
| `OCI_PROFILE` | `DEFAULT` | OCI 配置 profile |
| `OCI_CONTROL_PUBLIC_URL` | 配置为实际访问的规范 origin | 如 `https://oci.example.com`，不带子路径 |
| `OCI_CONTROL_ALLOW_HTTP` | `false` | 明确允许可信 HTTP；公网建议关闭 |
| `OCI_CONTROL_MODE` | `live` | `demo` 仅合成数据 |
| `OCI_CONTROL_HOST` | `127.0.0.1` | 原生监听地址；容器固定 `0.0.0.0` |
| `OCI_CONTROL_PORT` | `8787` | 原生监听/Compose 主机端口 |
| `OCI_CONTROL_WEB_DIR` | `web/dist` | 网页构建输出；运行脚本设置绝对路径 |
| `OCI_CONTROL_REFRESH_SECONDS` | `300` | 后台采集间隔；过短可能触发 API 限速 |
| `OCI_CONFIG_DIR` | Compose 为 `~/.oci` | 推荐改为容器专用配置目录 |
| `OCI_CONTROL_BIND_IP` | Compose 为 `127.0.0.1` | 主机端口绑定地址 |

直接 `python -m server` 的配置默认值可能使用相对 `./data`；部署时必须显式设置仓库外的 `OCI_CONTROL_DATA_DIR`。密码不是 OCI 登录密码，服务不需要你的 Oracle 网页账户密码。

## 后台运行、升级与备份

原生部署可使用 systemd。先用专用系统用户安装/配置，再把下列模板存放在系统服务目录，替换路径和用户；不要把实例化后的私人部署配置提交仓库。

```ini
[Unit]
Description=OCI Control
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=oci-control
Group=oci-control
WorkingDirectory=/opt/oci-control
EnvironmentFile=/etc/oci-control/environment
ExecStart=/opt/oci-control/.venv/bin/python -m server
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/oci-control

[Install]
WantedBy=multi-user.target
```

外部 environment 文件设置数据目录 `/var/lib/oci-control`、OCI 配置路径、网页绝对路径及规范 URL，权限限制为服务管理员可读。预先创建数据目录并归属服务用户。systemd 并不加载当前 shell 的 export；每次改配置后重启服务。用 `systemctl` 管理进程，日志中的用户/账户相关信息也不应随意公开。

升级前停止服务，备份运行数据目录及服务端配置到受保护位置，记录当前版本，再获取并审阅新版本。原生重新安装依赖和构建网页后启动；Docker 重新 build 后 `docker compose up -d`，保留原有卷。数据库备份应在停止服务后复制，避免不一致；备份包含有效会话和敏感快照，需加密并限制访问。签名密钥单独离线备份。

改密码使用相同数据目录执行 `python -m server configure`，然后重启服务；服务按密码摘要失效规则撤销旧会话。单次退出只撤销当前会话。丢失设备时应更换面板密码并确认其他客户端重新登录。

## Android 构建

原生包使用 Capacitor **7.6.9**，正式应用 ID `com.ocicontrol.app`，名称“云境 OCI Control”。`mobile/capacitor.config.json` 指向 `../web/dist`，不加载远程 `server.url`；`CapacitorHttp` 只用于显式请求，关闭重定向并校验服务器 origin。TLS 证书验证保持开启，自签名证书需在设备信任策略中正确部署，不能通过跳过证书校验解决。

本地构建需要 **Node.js 22+、JDK 21、Android SDK Platform 35、Build Tools 35.0.0**、可运行对应构建工具的主机。Gradle 8.11.1 由 wrapper 下载并校验 SHA-256；Linux 官方 Android 构建工具通常为 x86_64，ARM Linux 主机建议使用 GitHub Actions。不要把 SDK、`local.properties`、签名文件放进版本控制。

```bash
npm ci --prefix web
npm run build --prefix web
npm ci --prefix mobile
npm test --prefix mobile
npm run build:debug --prefix mobile
```

结果位于 `mobile/android/app/build/outputs/apk/debug/app-debug.apk`。原生 AES-GCM 单元测试验证随机 nonce、篡改拒绝和跨服务器密文隔离，随 `testDebugUnitTest` 执行。Keystore 仪器测试是独立的设备验证：连接专用测试设备后在 `mobile/android` 执行 `./gradlew connectedDebugAndroidTest`；不使用云端凭据。

本仓库的 `.github/workflows/ci.yml` 在 push、PR、手动触发时先运行 Python/网页/原生包约束测试、网页构建、Compose 校验和秘密扫描，再并行检查 Docker、构建 Android。Android 下载同次运行的网页产物后同步，避免在共享 checkout 中并发改写网页构建输出。默认同时生成 `oci-control-0.1.0-debug-apk` 和 `oci-control-0.1.0-unsigned-release-apk`，均包含 APK 和 `SHA256SUMS`，保留 14 天；需要 GitHub 登录下载 Actions 产物。未签名 release 经过 SDK `zipalign -c -P 16 -v 4` 校验，文件名为 `app-release-unsigned.apk`，签名前不能安装。工作流不自动发布 GitHub Release，默认构建不使用任何 GitHub Secrets。

```bash
gh workflow run ci.yml
```

默认调试包的 ID 是 `com.ocicontrol.app.debug`，可与正式包并存。CI 每次的临时调试签名可能不同，旧调试包不一定能覆盖升级；卸载后重装会清除其本地数据。不要将调试包描述为正式签名发行版。

正式交付采用 **CI 构建未签名 APK → 本地签名**。签名私钥及密码仅保留在维护者本地的安全目录，不上传 GitHub，也不配置 GitHub Secrets。使用固定的本地 Android 签名 keystore 并单独备份；后续升级必须使用同一密钥。下载成功运行的 `oci-control-0.1.0-unsigned-release-apk` 后，在仓库外的产物目录核验和签名：

```bash
# 在已解压的产物目录中操作；替换路径和 alias，密码通过交互终端输入。
sha256sum -c SHA256SUMS
java -jar /path/to/android-sdk/build-tools/35.0.0/lib/apksigner.jar sign \
  --ks /absolute/private/path/oci-control-release.jks \
  --ks-key-alias oci-control \
  --out oci-control-0.1.0.apk app-release-unsigned.apk
java -jar /path/to/android-sdk/build-tools/35.0.0/lib/apksigner.jar verify \
  --verbose --print-certs oci-control-0.1.0.apk
sha256sum oci-control-0.1.0.apk > SIGNED-SHA256SUMS
```

本地签名可使用 Java 17 与官方 SDK 的 `apksigner.jar`，无需重建网页或在 ARM 主机运行 x86_64 构建工具。CI 已检查对齐，签名后不要重新 zipalign 或修改 APK。核对验证输出中的公开签名证书指纹与维护者保留的指纹一致，再交付签名 APK 及其校验和；不交付 keystore、密码或签名环境。不要将密码放入命令参数或仓库文件。

工作流保留一个可选的 GitHub 托管签名入口，供选择不同信任策略的部署使用，**本项目此次交付不启用**。它要求在 GitHub Actions Secrets 配置 `ANDROID_KEYSTORE_BASE64`、`ANDROID_KEYSTORE_PASSWORD`、`ANDROID_KEY_ALIAS`、`ANDROID_KEY_PASSWORD`，再在 `main` 手动触发 `signed_release=true`。产物名 `oci-control-0.1.0-signed-release-apk`；临时签名文件会清理。Base64 只是编码，不是加密；显式请求该方式但缺少 Secrets 会失败。

Android 使用服务器规范 origin 存储非秘密的连接设置，bearer 只交给 `SecureSession`，由 Android Keystore 密钥加密保存。系统备份和设备迁移排除应用数据，避免复制加密凭证或快照。退出保留服务器与快照；需要抹去本机资源资料时另外清除本地数据。

## 排查问题

- **无法登录/跨域错误**：核对 `OCI_CONTROL_PUBLIC_URL` 与实际访问的协议、主机、端口完全一致。浏览器只走同源请求，Android 走原生 HTTP；不要通过放开全站 CORS 绕过问题。
- **HTTP 被拒绝**：服务端需显式 `OCI_CONTROL_ALLOW_HTTP=true`，Android 还需 UI 确认；公网应改 HTTPS。
- **Android 连接失败**：检查设备可达性、证书链、代理是否重定向。直接填写最终 HTTPS 地址，客户端不会携带 bearer 跟随跳转。
- **首次快照不可用**：查看面板采集状态，确认 OCI 配置/profile、私钥路径、IAM 授权、网络与 API 限速；不要把原始配置贴入 issue。
- **快照过期**：界面显示的是最后一次采集时间。刷新完成前旧快照仍保留，缺失指标和部分错误不代表资源为零。
- **Docker 私钥不可读/状态不可写**：核对 `/oci` 内路径与 UID `10001` 权限，不能仅检查主机当前用户是否可读。
- **免费额度不一致**：以 Oracle 官方账单、SKU、区域与最新政策为准；预算和监控估算都不能提供硬性费用上限。
