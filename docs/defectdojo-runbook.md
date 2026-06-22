# DefectDojo Integration Runbook

This runbook describes how to deploy DefectDojo locally, bootstrap the product/engagement, expose it via ngrok, configure GitHub Actions secrets, and verify end-to-end finding ingestion.

---

## A. Local DefectDojo Deployment

DefectDojo requires its own Docker Compose stack. **Do not commit DefectDojo's compose file into this repository.**

> **Port note**: The `finsight` repo's own `docker compose up` binds host port **8080** to the `adminer` service. DefectDojo must run on a different host port to avoid a collision. This runbook uses **8082**.

```bash
# Clone DefectDojo (one-time)
git clone https://github.com/DefectDojo/django-DefectDojo.git ~/defectdojo
cd ~/defectdojo

# Start DefectDojo, overriding the nginx host port to 8082
# The default compose maps nginx to host :8080; override to :8082
docker compose up -d --build \
  --env-file <(echo "DD_PORT=8082")
```

If the official compose does not support `DD_PORT`, use a local override file:

```bash
# ~/defectdojo/docker-compose.override.yml  (NOT committed to finsight repo)
version: "3"
services:
  nginx:
    ports:
      - "8082:8080"
```

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --build
```

**Default credentials**: `admin` / `admin`
**UI**: `http://localhost:8082`

Wait for the stack to be healthy (adminer typically takes ~2 minutes on first run):

```bash
until curl -sf http://localhost:8082/login > /dev/null; do
  echo "Waiting for DefectDojo..."; sleep 5
done
echo "DefectDojo is up."
```

**Troubleshooting — port conflict**:
- If `http://localhost:8082` is unreachable, check nothing else binds 8082: `lsof -i :8082`
- If 8080 is already taken by the finsight adminer, ensure you used the override above
- Stop adminer only if you need 8080: `docker compose stop adminer` (in the finsight repo)

---

## B. Product and Engagement Bootstrap

### Step 1 — Log in

Navigate to `http://localhost:8082` and sign in with `admin` / `admin`.

### Step 2 — Create a Product Type

Go to **Products → Product Types → Add Product Type**.
- Name: `Application` (or any category that fits)
- Save.

### Step 3 — Create the Product

Go to **Products → Add Product**.
- Name: `finsight`
- Product Type: the type you just created
- Save.

### Step 4 — Create the Engagement

Go to the `finsight` product → **Engagements → Add Engagement**.
- Name: `CI Security Scan` (EXACT string — any variation creates a duplicate engagement)
- Engagement type: `CI/CD`
- Status: `In Progress`
- Save.

> The upload script sends `engagement_name=CI Security Scan` on every API call. If the name does not match exactly, DefectDojo creates a second parallel engagement instead of updating the existing one.

### Step 5 — Find the Numeric Product ID

Open the product page and note the URL:
```
http://localhost:8082/product/3/findings
                              ↑
                         product ID = 3
```

Or retrieve it via API:
```bash
curl -sS -H "Authorization: Token <your-token>" \
  "http://localhost:8082/api/v2/products/?name=finsight" | python3 -m json.tool
# Look for "id" in the results array
```

### Step 6 — Generate an API Token

- Click your username (top right) → **API v2** → **Generate Token**, or
- POST to `/api/v2/api-token-auth/`:

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' \
  "http://localhost:8082/api/v2/api-token-auth/" | python3 -m json.tool
# Response: {"token": "..."}
```

Keep this token — you will use it as the `DEFECTDOJO_TOKEN` secret.

### Optional — Create the product via API

```bash
T="<your-api-token>"
curl -sS -H "Authorization: Token ${T}" \
  -F 'name=finsight' \
  -F 'prod_type=1' \
  -F 'description=CI security findings' \
  "http://localhost:8082/api/v2/products/" | python3 -m json.tool
```

---

## C. ngrok Tunnel

GitHub Actions runners cannot reach `localhost`. You must expose DefectDojo via an ngrok tunnel.

### Start the tunnel

```bash
ngrok http 8082
```

ngrok prints output like:

```
Forwarding  https://abc123def.ngrok-free.app -> http://localhost:8082
```

Copy the `https://...ngrok-free.app` URL. This is your `DEFECTDOJO_URL`.

**Known limitation — URL rotation**: The free ngrok tier assigns a new URL each time you restart the tunnel. After each ngrok restart you **must** update the `DEFECTDOJO_URL` GitHub secret (see Section D). If the secret is stale, the `defectdojo-upload` CI job will fail, but `continue-on-error: true` ensures the overall workflow still passes green.

---

## D. Repository Secrets Configuration

Navigate to the repository on GitHub:
**Settings → Secrets and Variables → Actions → New repository secret**

| Secret Name | Value |
|---|---|
| `DEFECTDOJO_URL` | ngrok HTTPS URL, no trailing slash (e.g. `https://abc123def.ngrok-free.app`) |
| `DEFECTDOJO_TOKEN` | API token from Section B, Step 6 |
| `DEFECTDOJO_PRODUCT_ID` | Numeric product ID from Section B, Step 5 |

> When `DEFECTDOJO_URL` is not set, the `defectdojo-upload` CI job is automatically skipped. The overall workflow remains green. This is by design — finding ingestion is evidence-on-demand, not a CI gate.

---

## E. Verification

### Trigger a run

```bash
# Push to main (triggers the full security pipeline)
git push origin main

# Or manually via GitHub Actions UI
# Go to Actions → Security Pipeline → Run workflow
```

### Verify findings appear

1. Open `http://localhost:8082` (while ngrok is running)
2. Navigate to **Products → finsight → Engagements → CI Security Scan → Tests**
3. You should see one Test entry per tool:
   - `Gitleaks Scan`
   - `Trufflehog Scan`
   - `Trivy Scan FS`
   - `Trivy Scan Image`
   - `Semgrep JSON Report`
   - `Bandit Scan`
   - `ZAP Scan`

### Deduplication check

Run the workflow twice against the same commit. The finding count for each test must remain the same (reimport closes stale findings and reopens existing ones — no duplicates are created).

### Verify the job was skipped (no DEFECTDOJO_URL)

Remove the `DEFECTDOJO_URL` secret (or do not set it). Trigger the workflow. The `defectdojo-upload` job should show status **Skipped** while all scan jobs still run and upload their artifacts normally. Overall workflow status: **Success**.

---

## F. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `defectdojo-upload` job: **Skipped** | `DEFECTDOJO_URL` secret not set | Expected behavior when running without local DefectDojo. Set the secret to enable uploads. |
| `defectdojo-upload` job: **Failed** (but overall workflow: Success) | ngrok URL is stale or DefectDojo is not running | Restart `ngrok http 8082`, copy new URL, update `DEFECTDOJO_URL` secret. |
| `HTTP 400 Bad Request` from upload script | `product_id` mismatch or `engagement_name` mismatch | Verify `DEFECTDOJO_PRODUCT_ID` matches the product URL in DefectDojo UI. Verify the engagement is named exactly `CI Security Scan`. |
| `HTTP 401 Unauthorized` | API token invalid or expired | Regenerate token via DefectDojo UI → API v2 → Generate Token. Update `DEFECTDOJO_TOKEN` secret. |
| `http://localhost:8082` unreachable | Port conflict or stack not started | Check `lsof -i :8082`. Ensure DefectDojo is running on port 8082 (not 8080). Confirm `docker compose ps` shows nginx healthy. |
| Two parallel engagements created | `engagement_name` string mismatch | Delete the extra engagement in DefectDojo UI. Ensure the script and any manual setup use exactly `CI Security Scan`. |

---

## Manual Validation Commands (T2)

Run these locally to validate the upload script before pushing. Requires DefectDojo running on `:8082` and an ngrok tunnel.

```bash
# Export required environment variables
export DEFECTDOJO_URL="http://localhost:8082"
export DEFECTDOJO_TOKEN="<token-from-section-b>"
export DEFECTDOJO_PRODUCT_ID="<id-from-section-b>"

# SCENARIO-1: successful upload
bash scripts/upload_to_defectdojo.sh "Semgrep JSON Report" path/to/semgrep-report.json
# Expected: exit 0, HTTP 2xx, finding visible in DefectDojo UI

# SCENARIO-2: missing file (graceful skip)
bash scripts/upload_to_defectdojo.sh "Trivy Scan" /nonexistent-file.json
# Expected: exit 0, INFO skip message, no HTTP call

# SCENARIO-3: TruffleHog NDJSON cleanup
bash scripts/upload_to_defectdojo.sh "Trufflehog Scan" path/to/trufflehog-report.json
# Expected: exit 0, only SourceMetadata lines uploaded, temp file deleted

# SCENARIO-4: missing env var (error exit)
unset DEFECTDOJO_URL
bash scripts/upload_to_defectdojo.sh "Bandit Scan" path/to/bandit-report.json
# Expected: exit 1, ERROR message, no HTTP call
```
