# Android 客户端

版本由 `package.json`、lockfile 与 `android/app/build.gradle` 保持一致；当前
`versionName=0.2.0`、`versionCode=2`。CI 的所有产物名称从 mobile package 读取。

## 与 Web 的桥接约定

- `@capacitor/app` 固定 **7.1.2**；Capacitor core/android/cli 固定 **7.6.9**。
- Web 注册 `App.addListener('backButton', ...)`，依次处理：最上层弹窗（提交中
  阻止关闭）→资源详情的来源页面→非总览标签返回总览→`App.minimizeApp()`。
  不调用 `exitApp()`，不根据 `canGoBack` 盲目后退 WebView 历史。
- `App.addListener('resume', ...)` 只重验会话、读取 snapshot/status。
  恢复前台不能重放云操作；Web 负责移除过期监听与取消旧服务器请求。
- 原有 `SecureSession.set/get/remove` 不变，凭证仍存 Android Keystore 加密存储。
- Web 通过 `registerPlugin('NativeChrome')` 调用
  `setTheme({ theme: 'light' | 'dark', backgroundColor: '#RRGGBB' }): Promise<void>`。
  `system/light/dark` 用户偏好由 Web 解析；原生仅接受解析后的浅/深色与不透明
  六位颜色，非法参数返回 `INVALID_THEME`。不得把 system 直接传给原生。
- 原生不修改系统夜间模式，避免影响 Web 的 `prefers-color-scheme`。
  启动时使用系统 DayNight 背景，浅色 `#F7F9FC`、深色 `#101418`；加载后以
  Web 解析值为准。Android 6/7 不支持深色导航图标，因此导航栏保留黑底。

## 系统栏、安全区与键盘

`NativeChrome` 是唯一的 inset 所有者。窗口使用 edge-to-edge，原生 content
容器消费 `systemBars | displayCutout | ime` 的并集，并缩小 WebView 可用区域。
IME 和导航栏高度取较大值，不相加；向子节点返回 `CONSUMED`。Capacitor 的
`adjustMarginsForEdgeToEdge` 显式禁用，manifest 保留 `adjustResize`。

Web 在 Android 设置 `html[data-native=true]`，所有 CSS safe-area 变量归零。
弹窗使用可用视口高度和内部滚动，不再添加 IME padding；无需额外 inset 事件或
Keyboard 插件。Web 负责自己的 `visualViewport` 与输入焦点可见性。

日志和 WebView debugging 在所有构建中禁用。HTTP 仅使用显式原生请求，
`CapacitorHttp.enabled=false`，不全局修改 fetch。

## 构建与验证

先等待前端确认最终 `web/dist`，再运行 `npm run sync`。此目录的脚本不构建 Web。
完整 Android 构建以 Linux x64、Java 21、Android SDK 35 的 CI 为准：

```sh
npm ci
npm test
npm run sync
cd android
./gradlew --no-daemon testDebugUnitTest assembleDebug assembleDebugAndroidTest assembleRelease
./gradlew --no-daemon connectedDebugAndroidTest
```

最后一条需要设备或模拟器。CI 使用 API 35 google_apis x86_64、KVM、无界面
软件 GPU 与禁用动画，执行 instrumentation，并始终上传 JUnit/HTML 结果。
安装的应用为独立 `.debug` 包；合成测试不配置服务端或操作云资源。

回归覆盖会话加密、主题输入约束、配置约束，以及设备上的 Keystore 持久化、
重复 inset、旋转方向的合成刘海、主题图标、插件注册。真实 IME 测试加载无脚本
的本地输入框，通过点击呼出键盘并检查 WebView 缩小，系统 Back 关闭键盘后
检查高度恢复。合成 inset 的通过不等于实际设备旋转验证；真机仍需单独验收。

CI 保留未签名 release 与明确标记的 debug APK。正式签名由发布负责人使用
现有密钥完成；密钥与运行数据不进入 checkout。
