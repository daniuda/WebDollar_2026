param(
    [string]$TargetHost = "webdollar.cloudns.nz",
    [string]$User       = "ubuntu",
    [string]$KeyPath    = "$env:USERPROFILE\.ssh\github_actions_vps",
    [string]$RemoteDir  = "/home/ubuntu/webd-staking",
    [string]$NginxConf  = "/etc/nginx/sites-enabled/webd-explorer-https",
    [int]$ApiPort       = 3004,
    [string]$AppPrefix  = "/webd-staking/"
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

    Run-Step "Upload fișiere la VPS" {
        $filesToUpload = @("server.py", "tx_builder.py", "dashboard.html", "config.example.json")

        ssh @sshOpts "${User}@${TargetHost}" "rm -rf /tmp/webd-staking-upload && mkdir -p /tmp/webd-staking-upload"
        Assert-OK "Create temp dir"

        foreach ($f in $filesToUpload) {
            $local = Join-Path $projectDir $f
            if (Test-Path -LiteralPath $local) {
                scp @sshOpts "$local" "${User}@${TargetHost}:/tmp/webd-staking-upload/$f"
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
SERVICE_NAME="webd-staking"

echo "[1/6] Instalare cryptography..."
pip3 install cryptography 2>/dev/null && echo "  cryptography OK" \
  || { sudo apt-get install -y python3-cryptography 2>/dev/null && echo "  python3-cryptography apt OK"; } \
  || echo "  [WARN] cryptography indisponibil — payout-urile automate dezactivate"

echo "[2/6] Copiez fisierele..."
mkdir -p "$REMOTE_DIR"
cp /tmp/webd-staking-upload/server.py "$REMOTE_DIR/server.py"
cp /tmp/webd-staking-upload/tx_builder.py "$REMOTE_DIR/tx_builder.py"
cp /tmp/webd-staking-upload/dashboard.html "$REMOTE_DIR/dashboard.html"
cp /tmp/webd-staking-upload/config.example.json "$REMOTE_DIR/config.example.json"

if [ ! -f "$REMOTE_DIR/config.json" ]; then
  cp "$REMOTE_DIR/config.example.json" "$REMOTE_DIR/config.json"
  echo "  !! config.json creat — completeaza adresa pool + cheia privata in $REMOTE_DIR/config.json"
else
  echo "  config.json existent, pastrat"
fi

echo "[3/6] Configurez systemd..."
cat <<SERVICE | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null
[Unit]
Description=WebDollar Delegated Staking Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${REMOTE_DIR}
ExecStart=/usr/bin/python3 ${REMOTE_DIR}/server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}.service
sudo systemctl restart ${SERVICE_NAME}.service
sleep 3

STATUS=$(sudo systemctl is-active ${SERVICE_NAME}.service 2>/dev/null || echo "failed")
echo "  systemd status: $STATUS"

echo "[4/6] Verific API..."
curl -fsS "http://127.0.0.1:${API_PORT}/api/stats" -o /dev/null \
  && echo "  API OK" || echo "  [WARN] API nu raspunde (normal daca config.json nu e completat)"

echo "[5/6] Actualizez nginx..."
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
    echo "  Nginx block exista deja."
fi

sudo nginx -t && sudo systemctl reload nginx
echo "  Nginx reloaded."

echo "[6/6] Verific URL public..."
STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://__TARGET_HOST____APP_PREFIX__" || echo "000")
echo "  https://__TARGET_HOST____APP_PREFIX__ -> HTTP $STATUS_CODE"
echo ""
echo "=============================="
echo " DEPLOY OK!"
echo " URL: https://__TARGET_HOST____APP_PREFIX__"
echo " Completeaza: $REMOTE_DIR/config.json"
echo " Restart dupa config: sudo systemctl restart ${SERVICE_NAME}"
echo "=============================="
'@

    $remoteScript = $remoteScript.Replace("__REMOTE_DIR__",  $RemoteDir)
    $remoteScript = $remoteScript.Replace("__API_PORT__",    $ApiPort.ToString())
    $remoteScript = $remoteScript.Replace("__NGINX_CONF__",  $NginxConf)
    $remoteScript = $remoteScript.Replace("__APP_PREFIX__",  $AppPrefix)
    $remoteScript = $remoteScript.Replace("__TARGET_HOST__", $TargetHost)
    $remoteScript = $remoteScript -replace "`r`n", "`n"
    $remoteScript = $remoteScript -replace "`r",   "`n"

    $localTempScript = Join-Path ([System.IO.Path]::GetTempPath()) "webd-staking-deploy.sh"
    [System.IO.File]::WriteAllText($localTempScript, $remoteScript, [System.Text.UTF8Encoding]::new($false))

    Run-Step "Rulare script remote pe VPS" {
        scp @sshOpts "$localTempScript" "${User}@${TargetHost}:/tmp/webd-staking-deploy.sh"
        Assert-OK "Upload script"
        ssh @sshOpts "${User}@${TargetHost}" "bash /tmp/webd-staking-deploy.sh"
        Assert-OK "Deploy script"
    }

    Write-Host "`n==> Deploy finalizat!"
    Write-Host "    Dashboard: https://$TargetHost$AppPrefix"
    Write-Host ""
    Write-Host "    Pasul urmator — completeaza config.json pe VPS:"
    Write-Host "    ssh ubuntu@$TargetHost -i $KeyPath"
    Write-Host "    nano /home/ubuntu/webd-staking/config.json"
    Write-Host "    sudo systemctl restart webd-staking"
}
finally {
    if ($localTempScript -and (Test-Path -LiteralPath $localTempScript)) {
        Remove-Item -LiteralPath $localTempScript -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
