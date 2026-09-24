$ErrorActionPreference = 'Stop'
$composePath = Join-Path $PSScriptRoot 'ostis-compose.yml'
$kbPath = Join-Path $PSScriptRoot 'ostis-kb'

docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Engine is unreachable. Start Docker Desktop or check Docker access.'
}

New-Item -ItemType Directory -Force -Path $kbPath | Out-Null

docker-compose -f $composePath run --rm machine build
if ($LASTEXITCODE -ne 0) {
    throw 'Could not build the sc-machine knowledge base.'
}

docker-compose -f $composePath up -d
if ($LASTEXITCODE -ne 0) {
    throw 'Could not start sc-server.'
}

Write-Host 'sc-server: ws://localhost:8090/ws_json'
Write-Host 'Run the app from the project root: .\.venv\Scripts\python.exe app.py'
