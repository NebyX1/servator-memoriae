# Mejorar la lectura de una caligrafía

La revisión humana permite reunir ejemplos para un futuro entrenamiento: transcribí páginas de la misma caligrafía y confirmá o corregí cada renglón. Conviene preparar varias páginas representativas y mantener algunas apartadas para comprobar el resultado.

**Estado actual:** el entrenamiento y la activación de modelos propios todavía no están validados de extremo a extremo. No interpretes métricas o modelos de ejecuciones anteriores como prueba de mejora. Podés seguir usando el lector general y guardar tus correcciones.

Para implementar esta función de forma fiable hay que generar datos de entrenamiento compatibles con Kraken, separar páginas de entrenamiento y evaluación, entrenar un candidato y medir sus predicciones sobre páginas reservadas. La documentación de [Kraken](https://kraken.re/3.0/ketos.html) describe los formatos y herramientas de entrenamiento; [eScriptorium](https://gitlab.com/scripta/escriptorium) es una referencia de interfaz integrada con Kraken. La cantidad de ejemplos necesaria depende de la escritura y la calidad de las imágenes; unos pocos renglones no garantizan una mejora.
