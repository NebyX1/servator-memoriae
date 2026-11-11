# Guía de usuario (no técnica)

## 1. Entrar
En modo de prueba local abrí la aplicación y empezá directamente: no necesitás cuenta ni contraseña. Los documentos se guardan. En una instalación configurada con acceso autenticado, ingresá con la cuenta proporcionada por el administrador.

## 2. Organizar
- **Colecciones:** agrupan por fondo (ej. "Actas de Lavalleja 1883"). Botón crear → título y descripción.
- **Documentos:** ficha con tipo (libro/legajo), años, signatura, etiquetas. Creá uno dentro de una colección.

## 3. Subir escaneos
Formatos: JPG, PNG, TIFF multipágina, PDF multipágina. Límite: 512 MB por archivo, 500 páginas por archivo.
- Los archivos se ordenan por nombre (1, 2, 10 — no 1, 10, 2).
- Si repetís un archivo, el sistema avisa "duplicado" y no lo duplica.
- Si un archivo está dañado, se informa y **las demás páginas se conservan**.
- Cada página obtiene imagen + miniatura; el original se guarda intacto.

## 4. Transcribir y revisar
En **Configuración → Motor de transcripción** elegí Kraken, PaddleOCR-VL o Análisis doble. Kraken permite elegir Automático, CPU o GPU NVIDIA. PaddleOCR-VL decide el dispositivo automáticamente. Al elegirlo por primera vez se descarga el modelo y se hace una lectura de prueba; podés seguir usando Kraken. Los cambios se aplican a trabajos nuevos.

En Doble lectura abrí el documento en **Mis documentos**: compará las propuestas con la imagen, elegí una lectura completa, revisá las diferencias, corregí el texto y presioná **Confirmar transcripción**. Una diferencia entre motores no implica que alguno tenga razón. Si uno falla, su propuesta muestra el error y la otra se conserva. La revisión confirmada se guarda aparte de ambos resultados; podés marcar `[ilegible]`.

Lanzá la transcripción desde el documento. Cuando una página queda "done", abríla:
- Cada renglón muestra texto automático y confianza.
- Escribí tu corrección y guardá. Si otro editor guardó antes, verás "Otro editor guardó antes. Recargá y combiná" (error 409): recargá la página antes de reintentar.
- Estados: confirmado, corregido, ilegible, mal corte, omitido. Agregá notas ("tinta corrida", "roto").

## 5. Exportar
En «Mis documentos», elegí el documento y descargá **Word** para obtener un archivo .docx editable con el texto, las correcciones y la separación por página. También podés descargar JSON, PDF de lectura o PDF con imágenes. Las lecturas individuales sin revisión se indican como automáticas. En análisis doble no se exporta una propuesta como definitiva hasta que la confirmes. El PDF con imágenes permite buscar la transcripción de página; los bloques estructurados se conservan en JSON.

## 6. Consejos
Subí por lotes chicos con nombres claros (`acta-1883-001.tif`). Revisá miniaturas antes de transcribir. Confirmá solo lo que leíste completo.
