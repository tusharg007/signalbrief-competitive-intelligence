param([ValidateRange(1,65535)][int]$Port = 8000, [string]$Model = '', [string]$PublicUrl = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run uv sync --frozen --extra dev --python 3.11 first.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) { & $pythonPath -m signalbrief.setup }
$originalModel = $env:LLM_MODEL
$originalBaseUrl = $env:PUBLIC_BASE_URL
$originalSecureCookies = $env:SECURE_COOKIES
$originalRuntimeKey = $env:LLM_API_KEY
$originalRuntimeHook = $env:ZAPIER_HOOK_URL
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Choose another -Port before starting the worker."
}
if ($PublicUrl) {
    $publicUri = [uri]$PublicUrl
    if ($publicUri.Scheme -ne 'https' -or $publicUri.UserInfo -or $publicUri.Query -or $publicUri.Fragment -or $publicUri.AbsolutePath -ne '/') {
        throw 'PublicUrl must be a plain HTTPS origin, such as https://your-domain.ngrok-free.app'
    }
}
$runtimeFlags = (& $pythonPath -c "import json; from signalbrief.config import Settings; s=Settings(); print(json.dumps({'model_key':bool(s.model_key),'hook':bool(s.zapier_hook_url.get_secret_value())}))") | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Configuration could not be loaded. Check .env syntax.' }
if (-not $runtimeFlags.model_key) {
    $modelSecret = Read-Host 'Model API key (hidden; used for this session only)' -AsSecureString
    $env:LLM_API_KEY = [System.Net.NetworkCredential]::new('', $modelSecret).Password
    if (-not $env:LLM_API_KEY) { throw 'A model API key is required.' }
}
if (-not $runtimeFlags.hook) {
    $hookSecret = Read-Host 'Zapier Catch Hook URL (hidden; Enter to leave delivery disabled)' -AsSecureString
    $env:ZAPIER_HOOK_URL = [System.Net.NetworkCredential]::new('', $hookSecret).Password
}
if ($Model) { $env:LLM_MODEL = $Model }
if ($PublicUrl) {
    $env:PUBLIC_BASE_URL = $PublicUrl.TrimEnd('/')
    $env:SECURE_COOKIES = 'true'
} else {
    $env:PUBLIC_BASE_URL = "http://localhost:$Port"
    $env:SECURE_COOKIES = 'false'
}
# This is an operator-run launcher; the worker will send authorized workflow notifications to Zapier.
$workerProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'signalbrief.worker') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
try {
    & $pythonPath -m uvicorn signalbrief.api:create_app --factory --host 127.0.0.1 --port $Port --no-proxy-headers
} finally {
    if (-not $workerProcess.HasExited) { Stop-Process -Id $workerProcess.Id }
    $env:LLM_MODEL = $originalModel
    $env:PUBLIC_BASE_URL = $originalBaseUrl
    $env:SECURE_COOKIES = $originalSecureCookies
    $env:LLM_API_KEY = $originalRuntimeKey
    $env:ZAPIER_HOOK_URL = $originalRuntimeHook
}
