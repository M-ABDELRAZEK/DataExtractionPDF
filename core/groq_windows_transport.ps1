# Windows PowerShell 5.1 Groq HTTPS fallback. Called by Python on a non-JSON 403.
# No secrets passed as command-line arguments or stored on disk.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$responseEnvelope = @{ ok = $false; http_status = 0; body = ''; error = '' }
try {
    $payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $key = [string]$payload.api_key
    $bodyJson = [string]$payload.body_json
    $timeoutSeconds = [int]$payload.timeout_seconds
    if ([string]::IsNullOrWhiteSpace($key) -or [string]::IsNullOrWhiteSpace($bodyJson)) {
        throw 'Missing API key or request body'
    }
    $headers = @{ Authorization = ('Bearer ' + $key); Accept = 'application/json' }
    $result = Invoke-WebRequest -Uri 'https://api.groq.com/openai/v1/chat/completions' `
        -Method Post -Headers $headers -Body ([Text.Encoding]::UTF8.GetBytes($bodyJson)) `
        -ContentType 'application/json; charset=utf-8' -UseBasicParsing -TimeoutSec $timeoutSeconds
    $responseEnvelope = @{ ok = $true; http_status = [int]$result.StatusCode;
                           body = [string]$result.Content; error = '' }
}
catch {
    $response = $_.Exception.Response
    $status = 0
    $responseText = ''
    if ($null -ne $response) {
        try { $status = [int]$response.StatusCode } catch { }
        try {
            $stream = $response.GetResponseStream()
            if ($null -ne $stream) {
                $reader = New-Object System.IO.StreamReader($stream, [Text.Encoding]::UTF8)
                try { $responseText = $reader.ReadToEnd() }
                finally { $reader.Dispose() }
            }
        }
        catch { }
    }
    $responseEnvelope = @{ ok = $false; http_status = $status;
                           body = $responseText; error = 'PowerShell HTTPS transport failed' }
}
finally {
    $key = $null
    $payload = $null
}
# Single machine-readable JSON line for Python. No provider debug dumps or headers.
[Console]::Out.WriteLine(($responseEnvelope | ConvertTo-Json -Compress -Depth 8))
