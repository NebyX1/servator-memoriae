import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'node:url';

test.skip(process.env.SERVATOR_E2E_LOCAL_MODE !== '1', 'Esta prueba usa el modo local sin login.');

test('abre la aplicación y guarda un escaneo sin pedir credenciales', async ({ page }) => {
  // También cubre el caso en el que el navegador quedó en la pantalla anterior de login.
  await page.goto('/entrar');
  await expect(page.getByRole('heading', { name: '¿Qué querés organizar?' })).toBeVisible();
  await expect(page.getByText('Modo de prueba').first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Salir' })).toHaveCount(0);

  await page.getByLabel('Nombre del documento').fill('Documento de prueba local');
  await page.getByRole('button', { name: 'Continuar', exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles(fileURLToPath(new URL('./fixtures/page.png', import.meta.url)));
  await page.getByRole('button', { name: 'Continuar', exact: true }).click();
  const upload = page.waitForResponse(r => r.url().includes('/upload') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Guardar y transcribir' }).click();
  const response = await upload;
  expect(response.status()).toBe(200);
  const data = await response.json();
  expect(data.errors).toEqual([]);
  expect(data.added).toHaveLength(1);
  await expect(page.getByRole('heading', { name: 'En espera' })).toBeVisible();
  await page.getByRole('link', { name: 'Abrir mis documentos' }).click();
  await expect(page.getByRole('button', { name: /Documento de prueba local/ })).toBeVisible();
  // Una visita nueva conserva el acceso sin depender de una sesión iniciada.
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '¿Qué querés organizar?' })).toBeVisible();
});

test('configuración guarda la elección y muestra GPU no disponible', async ({ page }) => {
  await page.goto('/configuracion');
  await expect(page.getByRole('heading', { name: 'Configuración', exact: true })).toBeVisible();
  const gpu = page.getByRole('button', { name: /GPU NVIDIA/ });
  await expect(gpu).toBeDisabled();
  const automatic = page.getByRole('button', { name: /^Automático/ });
  await automatic.click();
  await expect(page.getByText('Preferencia guardada para las próximas transcripciones.')).toBeVisible();
  await expect(automatic).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(automatic).toHaveAttribute('aria-pressed', 'true');
  const cpu = page.getByRole('button', { name: /^CPU/ });
  await cpu.click();
  await expect(cpu).toHaveAttribute('aria-pressed', 'true');
});

test('solo Kraken permite cambiar CPU y GPU', async ({ page }) => {
  await page.goto('/configuracion');
  await expect(page.getByRole('group', { name: 'Dispositivo de procesamiento' })).toBeVisible();
  await page.getByRole('button', { name: /^Análisis doble/ }).click();
  await expect(page.getByText('Método actual: Análisis doble')).toBeVisible();
  await expect(page.getByRole('group', { name: 'Dispositivo de procesamiento' })).toHaveCount(0);
  await page.reload();
  await expect(page.getByText('Método actual: Análisis doble')).toBeVisible();
  await page.getByRole('button', { name: /^Kraken/ }).click();
  await expect(page.getByRole('group', { name: 'Dispositivo de procesamiento' })).toBeVisible();
});

test('la comparación permite elegir y corregir antes de confirmar', async ({ page }) => {
  const fixture = { available: true, job_id: 'trabajo-test', mode: 'dual', review: null,
    engines: { kraken: { status: 'completed', text: 'año 1923', device: 'cpu', model_version: 'v1' },
      paddleocr_vl: { status: 'completed', text: 'año 1928', device: 'cpu', model_version: 'rev' } },
    comparison: { differences: 1, chunks: [ { kind: 'equal', kraken: 'año ', second: 'año ' },
      { kind: 'replace', kraken: '1923', second: '1928', attention: 'cifras o fechas' } ] } };
  await page.route('**/api/v1/pages/*/ocr', route => route.fulfill({ json: fixture }));
  let saved;
  await page.route('**/api/v1/pages/*/ocr/review', async route => {
    saved = route.request().postDataJSON();
    fixture.review = { text: saved.text, source: saved.source, version: 1, job_id: saved.job_id, created_at: '2026-01-01' };
    await route.fulfill({ json: { ok: true, version: 1 } });
  });
  await page.goto('/');
  await page.getByLabel('Nombre del documento').fill('Comparación de prueba');
  await page.getByRole('button', { name: 'Continuar', exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles(fileURLToPath(new URL('./fixtures/page.png', import.meta.url)));
  await page.getByRole('button', { name: 'Continuar', exact: true }).click();
  await page.getByRole('button', { name: 'Guardar y transcribir' }).click();
  await expect(page.getByRole('heading', { name: 'En espera' })).toBeVisible();
  await page.getByRole('link', { name: 'Abrir mis documentos' }).click();
  await page.getByRole('button', { name: /Comparación de prueba/ }).click();
  await expect(page.getByText('Encontramos 1 diferencias', { exact: false })).toBeVisible();
  await expect(page.getByText('Palabras diferentes')).toBeVisible();
  await expect(page.getByText('Revisá con atención: cifras o fechas.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Elegir lectura' }).first().click();
  const editor = page.getByLabel('Texto para confirmar');
  await expect(editor).toHaveValue('año 1923');
  await editor.fill('año 1923 [ilegible]');
  await page.getByRole('button', { name: 'Confirmar transcripción' }).click();
  await expect.poll(() => saved?.text).toBe('año 1923 [ilegible]');
  expect(saved.source).toBe('manual');
  let exportOptions;
  await page.route('**/api/v1/exports', async route => {
    exportOptions = route.request().postDataJSON();
    await route.fulfill({ json: { job_id: 'exportacion-test' } });
  });
  await page.route('**/api/v1/exports/exportacion-test/download', route => route.fulfill({ body: '%PDF-1.4 prueba', contentType: 'application/pdf' }));
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'PDF con imágenes' }).click();
  expect((await download).suggestedFilename()).toMatch(/-facsimil\.pdf$/);
  expect(exportOptions.format).toBe('pdf-facsimil');
});
