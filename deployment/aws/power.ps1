<#
One command to control FlowLytix on AWS:
  .\deployment\aws\power.ps1 stop
  .\deployment\aws\power.ps1 start
  .\deployment\aws\power.ps1 status
#>
param([Parameter(Mandatory = $true)][ValidateSet('start', 'stop', 'status')][string]$Action,
      [string]$Profile = 'flowlytix', [string]$Region = 'ap-south-1')
$ErrorActionPreference = 'Continue'
$aws = Join-Path $env:LOCALAPPDATA 'Programs\Amazon\AWSCLIV2\aws.exe'
if (-not (Test-Path $aws)) { $aws = 'aws' }
$payload = New-TemporaryFile
$response = New-TemporaryFile
try {
  [IO.File]::WriteAllText($payload, "{`"action`":`"$Action`"}")
  & $aws lambda invoke --function-name flowlytix-power --cli-binary-format raw-in-base64-out `
    --payload "file://$payload" --profile $Profile --region $Region $response | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Could not reach AWS. Sign in with: aws login --profile flowlytix' }
  Get-Content -LiteralPath $response -Raw
  if ($Action -ne 'status') { Write-Host 'Accepted. AWS finishes the remaining steps automatically within about 15 minutes.' }
} finally {
  Remove-Item -LiteralPath $payload, $response -Force -ErrorAction SilentlyContinue
}
