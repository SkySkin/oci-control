import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

test('Android bundles the web app and keeps navigation local', () => {
  const config = JSON.parse(read('capacitor.config.json'));
  assert.equal(config.appId, 'com.ocicontrol.app');
  assert.equal(config.webDir, '../web/dist');
  assert.equal(config.server.url, undefined);
  assert.equal(config.server.allowNavigation, undefined);
  assert.equal(config.android.allowMixedContent, false);
  // Explicit native requests only; browser-style fetch must not silently change transport.
  assert.equal(config.plugins.CapacitorHttp.enabled, false);
});

test('Android disables bridge logging and WebView debugging for every build', () => {
  const config = JSON.parse(read('capacitor.config.json'));
  // Bridge logs may include plugin arguments, including the bearer passed to SecureSession.
  assert.equal(config.loggingBehavior, 'none');
  assert.equal(config.android.webContentsDebuggingEnabled, false);
});

test('Android credential storage cannot enter cloud backups or device transfer', () => {
  const manifest = read('android/app/src/main/AndroidManifest.xml');
  assert.match(manifest, /android:allowBackup="false"/);
  assert.match(manifest, /android:fullBackupContent="false"/);
  assert.match(manifest, /android:dataExtractionRules="@xml\/data_extraction_rules"/);
  assert.match(manifest, /android.permission.INTERNET/);
  const rules = read('android/app/src/main/res/xml/data_extraction_rules.xml');
  for (const section of ['cloud-backup', 'device-transfer']) {
    const body = rules.match(new RegExp(`<${section}[^>]*>([\\s\\S]*?)</${section}>`))[1];
    for (const domain of ['root', 'file', 'database', 'sharedpref', 'external']) {
      assert.ok(body.includes(`domain="${domain}" path="."`));
    }
  }
});

test('Capacitor packages are aligned to one v7 version', () => {
  const pkg = JSON.parse(read('package.json'));
  const versions = ['@capacitor/android', '@capacitor/core', '@capacitor/cli']
    .map((name) => pkg.dependencies[name] ?? pkg.devDependencies[name]);
  assert.equal(new Set(versions).size, 1);
  assert.match(versions[0], /^7\.\d+\.\d+$/);
});
