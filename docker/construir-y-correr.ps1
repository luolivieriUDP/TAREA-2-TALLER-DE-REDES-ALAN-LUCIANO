# =====================================================================
# Construye las imágenes con Dockerfile (sin importar postgres:17 ni usar
# docker-compose), crea la red y levanta servidor + cliente.
# Es idempotente: se puede correr las veces que quieras.
# Uso:  powershell -ExecutionPolicy Bypass -File construir-y-correr.ps1
# =====================================================================
$dockerDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$capturaDir = (Resolve-Path (Join-Path $dockerDir "..\captura")).Path
Push-Location $dockerDir

Write-Host "== Construyendo imagen del servidor (Dockerfile) =="
docker build -t tarea2/psql-servidor -f servidor/Dockerfile .
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR al construir el servidor"; Pop-Location; exit 1 }

Write-Host "== Construyendo imagen del cliente (Dockerfile) =="
docker build -t tarea2/psql-cliente -f cliente/Dockerfile .
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR al construir el cliente"; Pop-Location; exit 1 }

Write-Host "== Red redpsql (subred 172.18.0.0/16) =="
$nets = docker network ls --format "{{.Name}}"
if ($nets -notcontains "redpsql") {
    docker network create --subnet 172.18.0.0/16 redpsql | Out-Null
    Write-Host "   red creada"
} else {
    Write-Host "   ya existe (ok)"
}

Write-Host "== Levantando el servidor (IP 172.18.0.2) =="
docker rm -f psql-servidor 2>$null | Out-Null
docker run -d --name psql-servidor --network redpsql --ip 172.18.0.2 --hostname servidor `
    -p 5432:5432 -v "${capturaDir}:/capturas" tarea2/psql-servidor | Out-Null

Write-Host "== Levantando el cliente (IP 172.18.0.3) =="
docker rm -f psql-cliente 2>$null | Out-Null
docker run -d --name psql-cliente --network redpsql --ip 172.18.0.3 tarea2/psql-cliente | Out-Null

Write-Host "== Esperando a que el cliente pueda conectarse al servidor =="
$ok = $false
for ($i = 1; $i -le 40; $i++) {
    Start-Sleep -Seconds 2
    docker exec -e PGPASSWORD=redes2025 psql-cliente psql -h servidor -U taller -d tallerdb -c "SELECT 1" *> $null
    if ($LASTEXITCODE -eq 0) { $ok = $true; break }
}
if ($ok) { Write-Host "   servidor listo para recibir conexiones" }
else { Write-Host "   AVISO: el servidor aun no responde; espera unos segundos mas" }

Pop-Location
Write-Host ""
Write-Host "Listo. Ya puedes conectarte. Contenedores en ejecucion:"
docker ps --format "{{.Names}}  {{.Image}}  {{.Status}}"
