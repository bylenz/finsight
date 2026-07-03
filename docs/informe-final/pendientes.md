# Pendientes — Implementación DevSecOps (evidencia del informe)

Trabajo de implementación necesario para convertir el esqueleto del informe en una entrega con
**evidencia real**. Cada ítem cierra un `⏳ TODO(evidence)` de [`informe-final.md`](./informe-final.md).

> **Seguimiento SDD (engram):** cada sección está mapeada a un cambio SDD.
> - `security-pipeline` — proposal #879 · spec #881 · design #880 · tasks #882
> - `defectdojo-centralization` — proposal #883 · spec #886 · design #885 · tasks #887
> - `security-hardening` — proposal #884 · spec #888 · design #889 · tasks #890
> - _(manual)_ — items que `sdd-apply` no puede ejecutar (diagramas, PDF, exposición).

## Estado actual (automatizado en esta sesión)

- ✅ **Pipeline** — `security.yml` (Gitleaks, TruffleHog, Trivy+SBOM, Semgrep, Bandit, ZAP) + pre-commit hooks (PR #19). CI en verde.
- ✅ **Escaneo real ejecutado localmente** — `reports/*.json` generados (Gitleaks: sin fugas; Semgrep/Bandit/Trivy/TruffleHog con datos).
- ✅ **DefectDojo desplegado** (`:8082`) + Product `FinSight` + Engagement `CI Security Scan` + **22 hallazgos ingeridos** vía `reimport-scan` (script `upload_to_defectdojo.sh`, con fix `product_name`).
- ✅ **Evidencia capturada** — `docs/informe-final/evidence/dd-*.png` (dashboard por severidad + hallazgos).
- ✅ **STRIDE draw.io** — `stride-finsight.drawio` (abrir/importar en diagrams.net).
- ✅ **Plantilla STRIDE Excel** — `stride-finsight.xlsx` (hojas STRIDE + Mitigaciones).
- ✅ **Informe PDF** — `informe-final.pdf` (diagramas Mermaid + evidencia embebidos).
- ✅ **Cambios de código** — IDOR (PR #21), rate-limit (PR #22), refresh tokens (PR #23), audit log (PR #24).

### Solo queda en tu mano (manual, sin bugs de mi parte)
- 🔲 Subir `stride-finsight.drawio` a draw.io y `stride-finsight.xlsx` a Google Sheets/Drive → obtener los **links** que pide la rúbrica (requieren tu cuenta Google).
- 🔲 Pegar esos 2 links + el link del PDF en el `README.md` (sección de entregables).
- 🔲 (Opcional) Túnel **ngrok** hacia `:8082` + guardar `DEFECTDOJO_URL/TOKEN/PRODUCT_ID` como secrets del repo, si quieres que el job `defectdojo-upload` corra en CI (requiere tu authtoken de ngrok).
- 🔲 Preparar la **exposición** (mismo informe o PPT).

## Pipeline (GitHub Actions) · SDD: `security-pipeline`
- [ ] Crear `.github/workflows/security.yml` con los jobs: `secret-scan` (gitleaks, trufflehog),
      `sca` (trivy fs + imagen + SBOM CycloneDX), `sast` (semgrep, bandit), `dast` (OWASP ZAP baseline),
      `defectdojo-upload`. Borrador en §9.2 del informe.
- [ ] Mantener los jobs `lint`/`test` existentes en `ci.yml`.
- [ ] Ejecutar el pipeline y capturar cada job en verde.

## Pre-commit · SDD: `security-pipeline`
- [ ] Agregar hooks de **Gitleaks** y **TruffleHog** a `.pre-commit-config.yaml` (ya existe `detect-private-key`).
- [ ] `pre-commit install` + probar que un secreto de ejemplo es **bloqueado** (captura).

## DefectDojo · SDD: `defectdojo-centralization`
- [ ] Desplegar localmente: `docker compose -f docker-compose.yml -f docker-compose.override.dev.yml up -d --build`.
- [ ] Crear Product Type `Aplicaciones Web` → Product `FinSight` → Engagement `CI/CD`.
- [ ] Obtener API token y `DEFECTDOJO_PRODUCT_ID`.
- [ ] Crear `scripts/upload_to_defectdojo.sh` (llamada `reimport-scan`, limpieza de NDJSON de TruffleHog).
- [ ] Exponer con **ngrok** y guardar `DEFECTDOJO_URL`, `DEFECTDOJO_TOKEN`, `DEFECTDOJO_PRODUCT_ID` como *secrets* del repo.
- [ ] Capturas: Products → FinSight (por severidad/herramienta) y Metrics → Product Metrics.

## STRIDE · _(manual)_
- [ ] Rehacer el diagrama (§2) en **draw.io** y publicar el enlace.
- [ ] Completar la **plantilla STRIDE (Excel)** y publicar el enlace.
- [ ] (Si la rúbrica exige las oficiales) conseguir del docente las URLs correctas de Google (las del PDF están 404 por OCR).

## Tabla de hallazgos (§7) · SDD: evidencia de `security-pipeline` + `defectdojo-centralization`
- [ ] Reemplazar el borrador con los hallazgos reales del primer escaneo: IDs, severidad real, herramienta que lo detectó.

## Situación inicial vs. resultados (§8) · SDD: evidencia de `defectdojo-centralization`
- [ ] Agregar métricas reales: Nº de hallazgos por severidad antes/después, tiempo de detección, % mitigado.

## Entrega final · _(manual)_
- [ ] Exportar `informe-final.md` → **PDF**.
- [ ] Completar los 5 links del `README.md` (repo, draw.io, Excel, PDF, exposición).
- [ ] Preparar la exposición (mismo informe o PPT).

## Mejoras de seguridad en el código · SDD: `security-hardening` (4 PRs encadenados)
- [ ] Autorización a nivel de objeto (validar `household_id`) en `expenses`/`budgets` — mitiga IDOR.
- [ ] Rate limiting en la API (p. ej. SlowAPI) — mitiga DoS / abuso de costo del LLM.
- [ ] Denylist de JWT por `jti` + refresh tokens — mitiga reuso de token robado.
- [ ] Audit logging de eventos de seguridad — cierra la brecha de Repudiation.
