param(
    [string]$TargetHost = "webdollar.cloudns.nz",
    [string]$User       = "ubuntu",
    [string]$KeyPath    = "$env:USERPROFILE\.ssh\github_actions_vps",
    [string]$RemoteDir  = "/home/ubuntu/webd-checkout",
    [string]$NginxConf  = "/etc/nginx/sites-enabled/webd-explorer-https",
    [int]$ApiPort       = 3002,
    [string]$AppPrefix  = "/webd-checkout/"
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

    Run-Step "Upload app files to VPS /tmp/webd-checkout" {
        # Fisierele care merg pe server (fara node_modules, fara scripts/)
        $filesToUpload = @("index.html", "main.js", "style.css", "server.js", "package.json", "package-lock.json", ".gitignore")

        ssh @sshOpts "${User}@${TargetHost}" "rm -rf /tmp/webd-checkout-upload && mkdir -p /tmp/webd-checkout-upload"
        Assert-OK "Create temp dir"

        foreach ($f in $filesToUpload) {
            $local = Join-Path $projectDir $f
            if (Test-Path -LiteralPath $local) {
                scp @sshOpts "$local" "${User}@${TargetHost}:/tmp/webd-checkout-upload/$f"
                Assert-OK "Upload $f"
                Write-Host "  Uploaded: $f"
            } else {
                Write-Host "  Skipped (not found): $f"
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

echo "[1/5] Copiez fisierele..."
mkdir -p "$REMOTE_DIR"
cp -a /tmp/webd-checkout-upload/. "$REMOTE_DIR/"
cd "$REMOTE_DIR"

echo "[2/5] npm install (fara devDeps)..."
npm install --omit=dev

echo "[3/5] Configurez PM2..."
if ! command -v pm2 &>/dev/null; then
    sudo npm install -g pm2
fi

# Opreste daca ruleaza deja
pm2 delete webd-checkout 2>/dev/null || true

NODE_URL=https://webdollar.io \
PORT=$API_PORT \
PAYMENT_TIMEOUT_MS=600000 \
CORS_ORIGIN="*" \
pm2 start "$REMOTE_DIR/server.js" \
    --name webd-checkout \
    --interpreter node \
    --
pm2 save

# Asteapta pornirea
sleep 2
curl -fsS "http://127.0.0.1:$API_PORT/" -o /dev/null || true
echo "  PM2 status: $(pm2 pid webd-checkout || echo unknown)"

echo "[4/5] Actualizez nginx..."

# Adauga location /webd-checkout/ daca nu exista deja
if ! sudo grep -Fq "location $APP_PREFIX" "$NGINX_CONF"; then
    sudo python3 - <<PY
from pathlib import Path

conf_path = Path("$NGINX_CONF")
text = conf_path.read_text(encoding="utf-8")

block = """
    location $APP_PREFIX {
        proxy_pass http://127.0.0.1:$API_PORT/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

"""

# Insereaza inainte de ultima }
last_brace = text.rfind("}")
text = text[:last_brace] + block + text[last_brace:]
conf_path.write_text(text, encoding="utf-8")
print("  Nginx block adaugat.")
PY
else
    echo "  Nginx block exista deja, skip."
fi

sudo nginx -t
sudo systemctl reload nginx
echo "  Nginx reloaded."

echo "[5/5] Verific HTTP..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://__TARGET_HOST____APP_PREFIX__")
if [ "$STATUS" = "200" ]; then
    echo "  OK: https://__TARGET_HOST____APP_PREFIX__ → HTTP $STATUS"
    echo DEPLOY_OK
else
    echo "  WARNING: HTTP $STATUS (poate dureaza cateva secunde)"
    echo DEPLOY_OK
fi
'@

    $remoteScript = $remoteScript.Replace("__REMOTE_DIR__", $RemoteDir)
    $remoteScript = $remoteScript.Replace("__API_PORT__", $ApiPort.ToString())
    $remoteScript = $remoteScript.Replace("__NGINX_CONF__", $NginxConf)
    $remoteScript = $remoteScript.Replace("__APP_PREFIX__", $AppPrefix)
    $remoteScript = $remoteScript.Replace("__TARGET_HOST__", $TargetHost)
    $remoteScript = $remoteScript -replace "`r`n", "`n"
    $remoteScript = $remoteScript -replace "`r", "`n"

    $localTempScript = Join-Path ([System.IO.Path]::GetTempPath()) "webd-checkout-deploy.sh"
    [System.IO.File]::WriteAllText($localTempScript, $remoteScript, [System.Text.UTF8Encoding]::new($false))

    Run-Step "Rulare script remote" {
        scp @sshOpts "$localTempScript" "${User}@${TargetHost}:/tmp/webd-checkout-deploy.sh"
        Assert-OK "Upload remote script"

        ssh @sshOpts "${User}@${TargetHost}" "bash /tmp/webd-checkout-deploy.sh"
        Assert-OK "Remote deploy script"
    }

    Run-Step "Verificare URL final" {
        $url = "https://$TargetHost$AppPrefix"
        $status = curl.exe -s -o NUL -w "%{http_code}" $url
        Write-Host "  $url → HTTP $status"
        if ($status -ne "200") {
            Write-Host "  ATENTIE: HTTP $status. Verifica manual sau asteapta cateva secunde."
        }
    }

    Write-Host "`n==> Deploy webd-checkout finalizat!"
    Write-Host "    URL: https://$TargetHost$AppPrefix"
    Write-Host "    Exemplu plata: https://$TargetHost${AppPrefix}?to=WEBD`$AdresaTa&amount=10"
}
finally {
    if ($localTempScript -and (Test-Path -LiteralPath $localTempScript)) {
        Remove-Item -LiteralPath $localTempScript -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
