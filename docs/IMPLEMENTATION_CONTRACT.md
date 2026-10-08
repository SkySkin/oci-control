# Implementation contract v1

Product name **OCI Control / 云境**. Python 3.10+ FastAPI server in `server/` (CI/recommended 3.12), React+TypeScript+Vite web in `web/`; Android Capacitor wrapper in `mobile/` (platform agent owns mobile package). Root owns Python app/auth/db/config/test integration. OCI agent owns `server/cloud.py`, `server/demo.py`, `tests/test_cloud.py`, `docs/OCI.md`. Frontend agent owns `web/`, PRODUCT.md, DESIGN.md. Platform agent owns `mobile/`, scripts/, Dockerfile, compose.yaml, .github/, README.md, docs/INSTALL.md; coordinate API details via this contract. Root owns Python dependency files and repo defaults.

## API (root implements)

- GET `/api/health` public returns `{status:"ok",version:"0.1.0"}` (no secrets).
- GET `/api/session` returns `{authenticated:boolean,csrfToken?:string,serverId?:string,version:"0.1.0",mode:"live"|"demo"}`. Authenticated response also `capabilities:{actions:["instance.start","instance.stop","instance.reboot","instance.rename","nlb.backend.enable","nlb.backend.disable"]}`.
- POST `/api/login` JSON `{password:string,client:"web"|"android"}` returns `{authenticated:true,csrfToken:string,serverId:string,token?:string}`. Web gets HttpOnly host-only session cookie, token returned ONLY for android/native login. Android uses bearer, web unsafe calls use `X-CSRF-Token`. Browser JSON requests must pass same-origin validation; native HTTP no Origin permitted. Login rate limited. Persistent revocable 90-day renewable server sessions; secret digest changes invalidate all.
- POST `/api/logout` revokes current session; snapshots retained locally but require explicit offline-view UX. Web may display prior snapshot offline before server auth check; no cloud action offline. Separate clear local data button.
- GET `/api/snapshot` returns snapshot below; initial unavailable returns 503 with error object and retry hint. GET `/api/status` authenticated setup status `{configured:boolean,cliInstalled:boolean,refreshing:boolean,lastError:string|null,lastRefreshAt:string|null}`. No secrets.
- POST `/api/refresh` returns 202 `{status:"refreshing"}` triggers a single background collector. Default background every 5 minutes. Old snapshot remains during refresh.
- POST `/api/actions/prepare` JSON `{action,region,resourceId,params:{...}}`; response `{confirmationId,action,resourceName,summary,expiresAt,requiresText:string|null}`. Preview resolves real resource, backend allowed state/params; dangerous operations require typing resource name. Backend changes params `{backendSetName,backendName}` and rename `{displayName}`. Prepared action records bound to session and current etag.
- POST `/api/actions/execute` JSON `{confirmationId,confirmationText?,idempotencyKey}` returns `{operationId,status:"succeeded"|"submitted",message}`. Atomic once-only execution, fresh ETag, failures audited. No arbitrary provider methods, shell, paths, destructive terminate/delete operations.
- GET `/api/audit` returns `{events:[{id,at,action,resourceName,region,status,message}]}` recent 100.
- Errors `{error:{code,message}}` non-sensitive.

## Snapshot exact shape

```ts
type Snapshot={schemaVersion:1;serverId:string;generatedAt:string;mode:"live"|"demo";tenancy:{name:string;homeRegion:string};regions:Region[];resources:Resource[];cost:Cost;traffic:Traffic;alerts:Alert[];errors:{scope:string;message:string}[]};
type Region={id:string;name:string;isHome:boolean;status:"ready"|"error";resourceCount:number};
type Resource={id:string;name:string;kind:"instance"|"nlb"|"lb"|"bootVolume"|"blockVolume"|"bucket"|"vcn";region:string;compartment:string;state:string;shape?:string;ocpus?:number;memoryGb?:number;sizeGb?:number;publicIps?:string[];privateIps?:string[];createdAt?:string;cpuPercent?:number|null;memoryPercent?:number|null;networkBytesOut?:number|null;freeEligible?:boolean|null;details?:Record<string,unknown>;actions:string[]};
type Cost={currency:string;monthToDate:number|null;previousMonth:number|null;asOf:string|null;forecast:number|null;daily:{date:string;amount:number}[];byService:{name:string;amount:number}[];note:string};
type Traffic={todayBytes:number|null;monthBytes:number|null;officialMonthBytes:number|null;freeAllowanceBytes:number|null;asOf:string|null;source:"monitoring"|"billing"|"unavailable";daily:{date:string;bytes:number}[];note:string};
type Alert={id:string;level:"info"|"warning"|"critical";title:string;message:string;resourceId?:string};
```

No missing metric becomes fake zero. Do not add NLB processed bytes to instance/VNIC output and label billable egress. Region+all authorized compartments inventory, partial failures preserved. Billing only known data-transfer SKUs/units and preserve uncertainty; top-level today/month monitoring is explicitly estimate, not quota consumption. Details may hold backendSets/listeners/health/etc for UI.

## OCI collector interface (cloud agent implements)

`CloudClient(config_path: str, profile: str="DEFAULT")`; `collect() -> dict` snapshot without serverId (root injects). `prepare_action(action,region,resource_id,params) -> dict` containing `{resourceName,summary,requiresText,etag,context:{...}}` JSON-serializable internal target (no secrets). `execute_action(action,region,resource_id,params,etag=None,context=None) -> dict` result. Class `CloudError` with safe public message; no credential content in errors. Demo mode `DemoCloudClient` same interface synthetic fixture, clearly mode demo; no live writes. OCI config through `OCI_CONFIG_FILE` and `OCI_PROFILE`; do not modify shared config or global env defaults. Native authenticated operations root calls synchronous provider in thread executor.

## Runtime configuration (root implements)

`OCI_CONTROL_DATA_DIR` default `./data` (gitignored), `OCI_CONTROL_PASSWORD_HASH_FILE` path OR runtime `password.hash` (PBKDF2-SHA256 existing format pbkdf2-sha256$iterations$hex-salt$hex-digest); `OCI_CONFIG_FILE` default ~/.oci/config; `OCI_PROFILE` DEFAULT; `OCI_CONTROL_PUBLIC_URL` canonical HTTPS origin; `OCI_CONTROL_ALLOW_HTTP` default false explicit trusted LAN/IP option; `OCI_CONTROL_MODE` live (demo explicit); `OCI_CONTROL_HOST` 127.0.0.1; `OCI_CONTROL_PORT` 8787; `OCI_CONTROL_WEB_DIR` web/dist; `OCI_CONTROL_REFRESH_SECONDS` 300. CLI `python -m server configure` interactive setup password/no secret echo; `python -m server` starts service. Health and session are only public endpoints plus static assets.

## Android bridge (platform agent implements; frontend consumes)

Capacitor local bundled web, user enters server URL. Native `CapacitorHttp` API for requests (no server-wide CORS needed). Native Keystore custom plugin **SecureSession** with `{set({key,value}),get({key})->{value:string|null},remove({key})}`. Detect `window.Capacitor` platform via `@capacitor/core`; frontend can registerPlugin to access secure plugin. Persist nonsecret server URL and snapshots locally, bearer only secure plugin. App retains server and snapshots on logout; does not send queued mutations after reconnect. On network failure show timestamped last-known data. Explicit warning/opt-in for http:// connection; reject invalid URLs, credentials-in-URL, non-http(s), unexpected redirects. Server identity from session scopes cache; never mix accounts. Frontend can import Capacitor core v7 or compatible agreed version; platform agent communicates final version. Android build workflow produces installable APK with persistent release signing from GH secrets when set, otherwise clearly labeled debug artifact. No private keystore in git.
