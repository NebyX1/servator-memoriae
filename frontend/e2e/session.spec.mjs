import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'node:url';

test.skip(process.env.SERVATOR_E2E_LOCAL_MODE === '1', 'Estas pruebas verifican el modo con login.');

const email = 'prueba@example.com';
const password = 'clave-de-prueba-123';
const png = fileURLToPath(new URL('./fixtures/page.png', import.meta.url));

async function login(page) {
  await page.goto('/');
  await page.getByLabel('Correo').fill(email);
  await page.getByLabel('Contraseña').fill(password);
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(page.getByRole('heading', { name: '¿Qué querés organizar?' })).toBeVisible();
}

async function prepare(page, title) {
  await page.getByLabel('Nombre del documento').fill(title);
  await page.getByRole('button', { name: 'Continuar', exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles(png);
  await expect(page.getByText('page.png')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar', exact: true }).click();
  await expect(page.getByText(title, { exact: true })).toBeVisible();
}

async function submitAndCheck(page) {
  const upload = page.waitForResponse(r => r.url().includes('/upload') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Guardar y transcribir' }).click();
  const result = await upload;
  expect(result.status()).toBe(200);
  const body = await result.json();
  expect(body.errors).toEqual([]);
  expect(body.added).toHaveLength(1);
  await expect(page.getByRole('heading', { name: 'En espera' })).toBeVisible();
  await expect(page.getByText(/0 de 1 páginas procesadas/)).toBeVisible();
}

test('reauthentication after 401 preserves the selected image', async ({ page, context }) => {
  await login(page);
  await prepare(page, 'Prueba sesión interrumpida');
  const other = await context.newPage();
  await other.goto('/');
  await other.getByRole('button', { name: 'Salir' }).click();
  await expect(other.getByRole('heading', { name: 'Entrar al archivo' })).toBeVisible();
  const denied = page.waitForResponse(r => r.url().includes('/documents') && r.request().method() === 'POST' && r.status() === 401);
  await page.getByRole('button', { name: 'Guardar y transcribir' }).click();
  await denied;
  const dialog = page.getByRole('dialog', { name: 'Volvé a entrar' });
  await expect(dialog).toBeVisible();
  await expect(page.getByText('Prueba sesión interrumpida', { exact: true })).toBeVisible();
  await dialog.getByLabel('Contraseña').fill(password);
  await dialog.getByRole('button', { name: 'Continuar' }).click();
  await expect(dialog).toBeHidden();
  await submitAndCheck(page);
});

test('a session renewed in another tab lets the existing form submit', async ({ page, context }) => {
  await login(page);
  await prepare(page, 'Prueba acceso en otra pestaña');
  const other = await context.newPage();
  await other.goto('/');
  await other.getByRole('button', { name: 'Salir' }).click();
  await expect(other.getByRole('heading', { name: 'Entrar al archivo' })).toBeVisible();
  await other.getByLabel('Correo').fill(email);
  await other.getByLabel('Contraseña').fill(password);
  await other.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(other.getByRole('heading', { name: '¿Qué querés organizar?' })).toBeVisible();
  await expect(page.getByText('Prueba acceso en otra pestaña', { exact: true })).toBeVisible();
  await submitAndCheck(page);
});
