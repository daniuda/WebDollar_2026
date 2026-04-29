param(
    [string]$TargetHost = "webdollar.cloudns.nz",
    [string]$User       = "ubuntu",
    [string]$KeyPath    = "$env:USERPROFILE\.ssh\github_actions_vps",
    [string]$RemoteDir  = "/home/ubuntu/webd-checkout",
    [string]$NginxConf  = "/etc/nginx/sites-enabled/webd-explorer-https",
    [int]$ApiPort       = 3002,
    [string]$AppPrefix  = "/webd-checkout/",
    [string]$NodeUrl    = "https://webdollar.io"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $PSScriptRoot

function Run-Step {
    param([string]$Label, [scriptblock]$Action)
    Write-Host "`n==> $Label"
    & $Action
}

function Assert-OK {
    param([string]$Context)
    if ($LASTEXITCODE -ne 0) { throw "$Context failed (exit $LASTEXITCODE)" }
}

if (-not (Test-Path -LiteralPath $KeyPath)) {
    throw "SSH key not found: $KeyPath"
}

$sshOpts = @("-i", $KeyPath, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=15")

Push-Location $projectDir
$localTempScript = $null
try {

    Run-Step "Upload app files to VPS /tmp/webd-checkout-upload" {
        $filesToUpload = @("index.html", "main.js", "style.css", "server.py")

        ssh @sshOpts "${User}@${TargetHost}" "rm -rf /tmp/webd-checkout-upload && mkdir -p /tmp/webd-checkout-upload"
        Assert-OK "Create temp dir"

        foreach ($f in $filesToUpload) {
            $local = Join-Path $projectDir $f
            if (Test-Path -LiteralPath $local) {
                scp @sshOpts "$local" "${User}@${TargetHost}:/tmp/webd-checkout-upload/$f"
                Assert-OK "Upload $f"
                Write-Host "  Uploaded: $f"
            }
        }
    }

    $remoteScript = @'
#!/bin/bash
set -e

REMOTE_DIR="__REMOTE_DIR__"
API_PORT=__API_PORT__
NGINX_CONF="__NGINX_CONF__"
APP_PREFIX="__APP_PREFIX__"
NODE_URL="__NODE_URL__"
SERVICE_NAME="webd-checkout"

echo "[1/5] Copiez fisierele..."
mkdir -p "$REMOTE_DIR"
cp -a /tmp/webd-checkout-upload/. "$REMOTE_DIR/"

echo "[2/5] Configurez systemd..."
cat <<SERVICE | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null
[Unit]
Description=WebDollar Checkout payment server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${REMOTE_DIR}
ExecStart=/usr/bin/python3 ${REMOTE_DIR}/server.py --host 127.0.0.1 --port ${API_PORT} --node-url ${NODE_URL}
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}.service
sudo systemctl restart ${SERVICE_NAME}.service
sleep 2

STATUS=$(sudo systemctl is-active ${SERVICE_NAME}.service)
echo "  systemd status: $STATUS"

echo "[3/5] Verific API local..."
curl -fsS "http://127.0.0.1:${API_PORT}/" -o /dev/null && echo "  HTTP OK" || echo "  HTTP warn (poate serveste fisiere statice normal)"

echo "[4/5] Actualizez nginx..."
if ! sudo grep -Fq "location ${APP_PREFIX}" "$NGINX_CONF"; then
    sudo python3 - <<'PY'
from pathlib import Path

conf_path = Path("__NGINX_CONF__")
text = conf_path.read_text(encoding="utf-8")

block = """
    location __APP_PREFIX__ {
        proxy_pass http://127.0.0.1:__API_PORT__/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

"""

last = text.rfind("}")
text = text[:last] + block + text[last:]
conf_path.write_text(text, encoding="utf-8")
print("  Nginx block adaugat.")
PY
else
    echo "  Nginx block exista deja, skip."
fi

sudo nginx -t
sudo systemctl reload nginx
echo "  Nginx reloaded."

echo "[5/5] Verific URL public..."
STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://__TARGET_HOST____APP_PREFIX__")
echo "  https://__TARGET_HOST____APP_PREFIX__ → HTTP $STATUS_CODE"
echo "DEPLOY_OK"
'@

    $remoteScript = $remoteScript.Replace("__REMOTE_DIR__",  $RemoteDir)
    $remoteScript = $remoteScript.Replace("__API_PORT__",    $ApiPort.ToString())
    $remoteScript = $remoteScript.Replace("__NGINX_CONF__",  $NginxConf)
    $remoteScript = $remoteScript.Replace("__APP_PREFIX__",  $AppPrefix)
    $remoteScript = $remoteScript.Replace("__NODE_URL__",    $NodeUrl)
    $remoteScript = $remoteScript.Replace("__TARGET_HOST__", $TargetHost)
    $remoteScript = $remoteScript -replace "`r`n", "`n"
    $remoteScript = $remoteScript -replace "`r",   "`n"

    $localTempScript = Join-Path ([System.IO.Path]::GetTempPath()) "webd-checkout-deploy.sh"
    [System.IO.File]::WriteAllText($localTempScript, $remoteScript, [System.Text.UTF8Encoding]::new($false))

    Run-Step "Rulare script remote pe VPS" {
        scp @sshOpts "$localTempScript" "${User}@${TargetHost}:/tmp/webd-checkout-deploy.sh"
        Assert-OK "Upload script"

        ssh @sshOpts "${User}@${TargetHost}" "bash /tmp/webd-checkout-deploy.sh"
        Assert-OK "Deploy script"
    }

    Write-Host "`n==> Deploy webd-checkout finalizat!"
    Write-Host "    URL: https://$TargetHost$AppPrefix"
    Write-Host "    Exemplu: https://$TargetHost${AppPrefix}?to=WEBD`$AdresaTa&amount=10"
}
finally {
    if ($localTempScript -and (Test-Path -LiteralPath $localTempScript)) {
        Remove-Item -LiteralPath $localTempScript -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
