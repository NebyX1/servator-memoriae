# Instalación de Servator Memoriae

La vía recomendada para Windows con Docker Desktop, Linux y macOS es el bootstrap de Docker. Consultá [INSTRUCCIONES_AGENTE.md](../INSTRUCCIONES_AGENTE.md) para comprobar primero el hardware y elegir CPU o NVIDIA, y [docs/deployment/DOCKER.md](../docs/deployment/DOCKER.md) para más detalles.

En Windows ejecutá `.\scripts\bootstrap.ps1 -Device auto` desde la raíz; en Linux/macOS ejecutá `bash scripts/bootstrap.sh --device auto`. Ambos conservan `.env` y los datos existentes. No borres los volúmenes para resolver un error.

El entrenamiento de Kraken está deshabilitado hasta que pueda validarse de extremo a extremo. Las correcciones y los datos de entrenamiento existentes se conservan.
