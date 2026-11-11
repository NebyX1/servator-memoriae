# Pruebas de sesión en navegador

Estas pruebas usan la SPA React y las rutas Flask reales con CSRF activado. El proceso de prueba crea una base SQLite, una cuenta ficticia y almacenamiento temporales en el sistema operativo; no usa la base, las credenciales ni los archivos del stack de Docker. Usa los puertos locales 18547 y 18548 y se niega a iniciarse si ya están ocupados.

Desde la raíz del repositorio, con Python 3.11 y Node instalados:

```bash
python -m pip install -r frontend/e2e/requirements.txt
cd frontend
npm ci
npx playwright install chromium
npm run test:e2e
npm run test:e2e:local
```

En Windows el test utiliza Chrome instalado si está en su ubicación habitual; en otras plataformas utiliza el Chromium de Playwright. Para elegir otro navegador Chromium, definí `PLAYWRIGHT_EXECUTABLE_PATH` con su ruta. El proceso del navegador usa un perfil de pruebas aislado.

El primer comando comprueba la recuperación de sesión y el segundo abre la aplicación, crea un documento y sube una imagen sin login en modo de prueba local. También verifica que Configuración guarde la preferencia y no ofrezca una GPU que no está disponible. Se comprueba que la respuesta de subida contiene el archivo y no errores. Redis no se inicia: el trabajo queda pendiente y estas pruebas **no validan** OCR, el worker ni la configuración Docker. La compatibilidad del cliente antiguo se prueba en `tests/test_csrf.py`; la SPA antigua empaquetada no se incluye entre las pruebas de navegador.
