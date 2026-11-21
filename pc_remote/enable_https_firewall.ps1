#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
trap {
    $_ | Out-String | Set-Content -LiteralPath (Join-Path $projectRoot '.pc-helper-runtime\firewall-error.log')
    exit 1
}
$directPath = Join-Path $projectRoot '.pc-helper-runtime\direct.json'
$direct = Get-Content -LiteralPath $directPath -Raw | ConvertFrom-Json
$lan = [System.Net.IPAddress]::Parse($direct.lan_ip)
if ($lan.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or
    -not (Get-NetIPAddress -IPAddress $lan.ToString() -ErrorAction SilentlyContinue)) {
    throw 'Configured LAN IPv4 is not assigned to this PC.'
}
$program = Join-Path $projectRoot '.pc-helper-runtime\caddy\caddy.exe'
if (-not (Test-Path -LiteralPath $program -PathType Leaf)) { throw 'Caddy is not installed.' }
$ruleName = 'PC-Helper-Direct-HTTPS'
$rule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($rule) {
    if ($rule.Group -ne 'PC Helper direct access') { throw 'Firewall rule name is already in use.' }
    $rule | Set-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -Profile Any
    $rule | Get-NetFirewallApplicationFilter | Set-NetFirewallApplicationFilter -Program $program
    $rule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort 80,443
    $rule | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -LocalAddress $lan.ToString() -RemoteAddress Any
} else {
    New-NetFirewallRule -Name $ruleName -DisplayName 'PC Helper HTTPS (Caddy)' -Group 'PC Helper direct access' `
        -Direction Inbound -Action Allow -Enabled True -Profile Any -Program $program `
        -Protocol TCP -LocalPort 80,443 -LocalAddress $lan.ToString() | Out-Null
}
@{ok=$true;lan=$lan.ToString()} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectRoot '.pc-helper-runtime\firewall.json')
Write-Host 'PC Helper: Caddy TCP ports 80 and 443 enabled for the configured LAN address.'
