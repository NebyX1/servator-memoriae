import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { get } from 'node:http';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const probe = url => new Promise(resolve => {
  const req = get(url, res => { let body = ''; res.on('data', x => body += x); res.on('end', () => resolve(body)); });
  req.on('error', () => resolve('')); req.setTimeout(1000, () => req.destroy());
});
const ensureFree = port => new Promise((resolve, reject) => {
  const s = createServer(); s.once('error', reject); s.listen(port, '127.0.0.1', () => s.close(resolve));
});

// Rehusar arrancar si un servicio real ocupa alguno de los puertos de prueba.
await ensureFree(18547); await ensureFree(18548);
const temporary = mkdtempSync(join(tmpdir(), 'servator-browser-e2e-'));
const nonce = randomUUID();
const localMode = process.argv.includes('--local-mode');
const testEnv = { ...process.env, SERVATOR_E2E_LOCAL_MODE: localMode ? '1' : '0' };
const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const api = spawn(python, ['e2e/server.py'], { env: { ...testEnv, SERVATOR_E2E_DIR: temporary, SERVATOR_E2E_NONCE: nonce }, stdio: 'inherit' });
let vite;
let result = 1;
try {
  let ready = false;
  for (let i = 0; i < 200; i++) {
    if (api.exitCode !== null) throw new Error('No inició el backend de prueba');
    if (await probe('http://127.0.0.1:18547/__e2e_ready') === nonce) { ready = true; break; }
    await sleep(100);
  }
  if (!ready) throw new Error('El backend de prueba no estuvo listo');
  vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--config', 'e2e/vite.config.mjs'], { stdio: 'inherit' });
  ready = false;
  for (let i = 0; i < 200; i++) {
    if (vite.exitCode !== null) throw new Error('No inició la interfaz de prueba');
    if ((await probe('http://127.0.0.1:18548/')).includes('/src/main.tsx')) { ready = true; break; }
    await sleep(100);
  }
  if (!ready) throw new Error('La interfaz de prueba no estuvo lista');
  const tests = spawn(process.execPath, ['node_modules/@playwright/test/cli.js', 'test', ...process.argv.slice(2).filter(arg => arg !== '--local-mode')], { env: testEnv, stdio: 'inherit' });
  result = await new Promise((resolve, reject) => { tests.on('error', reject); tests.on('exit', code => resolve(code ?? 1)); });
} finally {
  api.kill(); if (vite) vite.kill();
  await sleep(500);
  const target = resolve(temporary);
  if (dirname(target) === resolve(tmpdir()) && basename(target).startsWith('servator-browser-e2e-')) {
    try { rmSync(target, { recursive: true, force: true }); } catch (err) { console.error('No se pudo eliminar el directorio temporal:', err.message); }
  }
}
process.exit(result);
