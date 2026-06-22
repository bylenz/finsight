# Informe Final — DevSecOps (FinSight)

Carpeta de entrega del **Informe Final** del proyecto (UTEC — Semana 16, **30% de la nota final**).

El informe redactado está en [`informe-final.md`](./informe-final.md). El trabajo de implementación
pendiente (para generar la evidencia real) está en [`pendientes.md`](./pendientes.md).

## Mapa de requisitos (PDF → sección del informe)

| # | Requisito del PDF | Sección en `informe-final.md` | Estado |
|---|-------------------|-------------------------------|--------|
| a | Título y descripción del proyecto | §1 | ✅ redactado |
| b | Diagrama de modelado de amenazas STRIDE | §2 | ✅ diagrama base / ⏳ exportar a draw.io |
| c | Explicación de 5 vulnerabilidades STRIDE | §3 | ✅ redactado |
| d | Elección de herramientas SAST y DAST + evidencia pipeline | §4 | ✅ elección / ⏳ evidencia |
| e | Secret scanning y SCA + evidencia pipeline | §5 | ✅ elección / ⏳ evidencia |
| f | Centralización en DefectDojo | §6 | ✅ enfoque / ⏳ evidencia |
| g | Tabla de mitigaciones (≥5 hallazgos priorizados) | §7 | ✅ borrador / ⏳ ajustar con escaneo real |
| h | Situación inicial vs. resultados | §8 | ✅ redactado / ⏳ métricas finales |
| i | Pipeline CI/CD completo (diagrama + script) | §9 | ✅ diagrama + YAML borrador / ⏳ ejecutar |
| j | Lecciones aprendidas | §10 | ✅ redactado |
| k | Recomendaciones para otros proyectos | §11 | ✅ redactado |

✅ = contenido escrito · ⏳ = requiere evidencia (capturas / reportes) — ver `pendientes.md`.

## Entregables que exige el PDF (sección 5)

> Reemplazar los placeholders antes de la entrega.

1. **Link del repositorio** (código + configuración del pipeline): https://github.com/bylenz/finsight
2. **Link del diagrama STRIDE en draw.io**: `⏳ TODO`
3. **Link de la plantilla STRIDE (Excel)**: `⏳ TODO`
4. **Informe en PDF** (este `informe-final.md` exportado, cubriendo el punto 2 + links): `⏳ TODO`
5. **Exposición** (mismo informe o PPT): `⏳ TODO`

## Nota sobre las guías de referencia

Las 2 guías técnicas (secret scanning/SCA/SAST y DefectDojo del repo `utec-devops-2026/laboratorios`)
y la plantilla de jobs DevSecOps (snippet de GitLab) fueron consultadas y sus herramientas/flujos
están reflejados en este informe. Los 2 enlaces de Google (diagrama y plantilla STRIDE oficiales) del
PDF están corruptos por el OCR (404); el modelo STRIDE de este informe se construyó desde cero para
FinSight. Si se requiere la plantilla oficial, proporcionar las URLs correctas.
