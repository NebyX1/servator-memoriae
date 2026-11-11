# Bootstrap idempotente Servator Memoriae (Windows PowerShell). Nunca hace `down -v`.
# Uso: .\scripts\bootstrap.ps1 [-Device auto|cpu|cuda] [-Yes] [-Help]
param(
  [string]$Device = "auto",
  [switch]$Yes,
  [switch]$Help
)
$ErrorActionPreference = "Stop"
if ($Help) { Write-Host "Uso: .\scripts\bootstrap.ps1 [-Device auto|cpu|cuda] [-Yes]"; exit 0 }
if ($Device -notin @("auto", "cpu", "cuda")) { throw "Dispositivo inválido: use auto, cpu o cuda." }
& docker compose version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Se requiere Docker Compose v2." }
& docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "El motor de Docker no está disponible. Iniciá Docker Desktop y reintentá." }

$Root = Split-Path (Split-Path $MyInvocation.MyCommand.Path -Parent) -Parent
Set-Location $Root
function Log($m) { Write-Host "[bootstrap] $m" }

if (-not (Test-Path ".env")) { Log ".env no existe -> copio .env.example"; Copy-Item ".env.example" ".env" }
Log ".env conservado (no se sobrescribe)."

# SECRET_KEY
$envText = Get-Content ".env" -Raw
if ($envText -match "cambiar-por" -or $envText -notmatch "(?m)^SECRET_KEY=") {
  $bytes = New-Object byte[] 32; (New-Object System.Security.Cryptography.RNGCryptoServiceProvider).GetBytes($bytes)
  $s = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
  if ($envText -match "(?m)^SECRET_KEY=") { $envText = $envText -replace "(?m)^SECRET_KEY=.*", "SECRET_KEY=$s" }
  else { $envText += "`nSECRET_KEY=$s`n" }
  Set-Content ".env" $envText -NoNewline
  Log "SECRET_KEY generado."
}
# carga .env al entorno (sin sobrescribir variables ya definidas)
Get-Content ".env" | ForEach-Object {
  if ($_ -match "^\s*#" -or $_ -notmatch "=") { return }
  $k, $v = $_.Split("=", 2); $k = $k.Trim(); $v = $v.Trim()
  if (-not [string]::IsNullOrEmpty($k) -and -not (Test-Path "env:$k")) { Set-Item "env:$k" $v }
}
function Upsert-Env($k, $v) {
  $t = Get-Content ".env" -Raw
  if ($t -match "(?m)^$k=") { $t = $t -replace "(?m)^$k=.*", "$k=$v" } else { $t += "`n$k=$v`n" }
  Set-Content ".env" $t -NoNewline
  Set-Item "env:$k" $v
}

# dispositivo
$hasNvidia = $false
try { & nvidia-smi -L 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { $hasNvidia = $true } } catch {}
$resolved = $Device
# Elegir CUDA automáticamente solo si Docker anuncia el runtime NVIDIA.
$hasToolkit = ((& docker info --format '{{json .Runtimes}}' 2>$null) -match 'nvidia')
# Docker Desktop/WSL puede exponer /dev/dxg aunque no liste un runtime NVIDIA.
# Comprobar el acceso dentro de un contenedor evita detectar solo el driver del host.
if ($Device -eq "auto" -and $hasNvidia -and -not $hasToolkit) {
  $probeImage = "python:3.11-slim"
  & docker run --rm --gpus all --entrypoint /bin/sh $probeImage -c 'test -e /dev/nvidia0 || test -e /dev/dxg' 2>$null | Out-Null
  $hasToolkit = ($LASTEXITCODE -eq 0)
}
if ($Device -eq "auto") { $resolved = if ($hasNvidia -and $hasToolkit) { "cuda" } else { "cpu" } }
if ($Device -eq "cuda" -and -not $hasNvidia) { throw "CUDA requiere una GPU NVIDIA disponible." }
Set-Content ".device" $resolved -NoNewline
Log "perfil dispositivo: $resolved (pedido: $Device) -> .device"
if ($resolved -eq "cuda") { Upsert-Env "DEVICE_MODE" "cuda"; Upsert-Env "TORCH_INDEX_URL" "https://download.pytorch.org/whl/cu130" }
else { Upsert-Env "DEVICE_MODE" "cpu"; Upsert-Env "TORCH_INDEX_URL" "https://download.pytorch.org/whl/cpu" }

try { docker compose version 2>$null | Out-Null } catch { Log "ERROR: docker compose v2 requerido"; exit 1 }

$compose = @("-f", "docker-compose.yml")
if ($resolved -eq "cuda") { $compose += @("-f", "docker-compose.gpu.yml"); Log "GPU: override activado." } else { Log "CPU: stack base." }

$coreServices = @("init", "backend", "worker", "worker-setup", "dispatcher", "frontend")
if ($resolved -eq "cuda") { $coreServices += "worker-gpu" }
Log "build de servicios principales..."
& docker compose @compose build @coreServices
if ($LASTEXITCODE -ne 0) { throw "Falló la construcción de los servicios principales." }
Log "build del lector opcional PaddleOCR-VL..."
& docker compose @compose build paddle
$paddleBuilt = ($LASTEXITCODE -eq 0)
if ($paddleBuilt) {
  Log "up (sin -v)..."
  & docker compose @compose up -d
} else {
  Log "WARN: no se pudo construir PaddleOCR-VL. Se iniciará Kraken; revisá la conexión y reintentá el bootstrap."
  & docker compose @compose stop paddle 2>$null | Out-Null
  & docker compose @compose up -d @coreServices
}
if ($LASTEXITCODE -ne 0) { throw "Falló el arranque de Docker Compose." }

Log "ps:"
& docker compose @compose ps

Log "init idempotente (migrate+bucket)..."
& docker compose @compose run --rm init; if ($LASTEXITCODE -ne 0) { Log "WARN init retornó $LASTEXITCODE (puede ser re-ejecución segura)" }

Log "descarga modelo (prepare_model idempotente)..."
$prep = "from wsgi import app; app.app_context().push(); "
$prep += "from app.models import Job, ModelVersion, User; from app.services_queue import new_job, dispatch; "
$prep += "m=ModelVersion.query.filter_by(version='v1').first(); print('v1 existe' if m else 'sin v1'); "
$prep += "j=(Job.query.filter_by(kind='prepare_model',idempotency_key='prepare-v1').first() if not m else None); "
$prep += "u=(User.query.first() if (j is None and not m) else None); "
$prep += "j=(new_job('prepare_model',(u.id if u else None),{'model':'ppocrv6-medium','version':'v1'},idem_key='prepare-v1',total=1) if (j is None and not m) else j); "
$prep += "dispatch(j) if j is not None else None; print('prepare encolado' if (j is not None and not m) else 'omitido')"
try {
  & docker compose @compose exec -T backend python -c $prep 2>&1 | Out-Host
  if ($LASTEXITCODE -ne 0) { Log "WARN prepare_model retornó $LASTEXITCODE (el dispatcher rescata PENDING; ver logs worker)" }
} catch { Log "WARN prepare_model falló (dispatcher rescata PENDING): $_" }

Log "smoke tests..."
$port = if ($env:FRONT_PORT) { $env:FRONT_PORT } else { "8787" }
try { Invoke-RestMethod "http://localhost:$port/health" -TimeoutSec 10 | Out-Host; Log "frontend /health OK" } catch { Log "WARN frontend health falló: $_" }
try { Invoke-RestMethod "http://localhost:$port/ready" -TimeoutSec 10 | Out-Host } catch { Log "WARN ready no disponible o modelo pendiente: $_" }
try { python scripts/diagnose.py } catch { Log "WARN diagnose: $_" }

Log "=================================================="
Log "URL: http://localhost:$port"
Log "modo: $resolved"
try { python scripts/diagnose.py --json | Out-File -Encoding utf8 ".agent-report.json"; Log "informe: .agent-report.json" } catch {}
if ($env:LOCAL_TEST_MODE -eq "1") { Log "Modo de prueba local: acceso directo, sin contraseña." }
else { Log "Primer acceso: docker compose exec backend flask --app wsgi create-admin (con ADMIN_PASSWORD en entorno)" }
Log "=================================================="
