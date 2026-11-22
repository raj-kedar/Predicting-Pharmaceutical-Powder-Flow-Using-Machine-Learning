<#
Builds the FlowLytix image on this PC and pushes it to a private Amazon ECR repository.
Needs Docker Desktop running and the AWS CLI signed in (aws configure sso / aws sso login).

  .\deployment\aws\push-image.ps1 -Region ap-south-1 [-Profile flowlytix]
Prints the image URI to use with make-user-data.ps1 and in the server's .env.
#>
param(
  [Parameter(Mandatory = $true)][string]$Region,
  [string]$Profile = '',
  [string]$Repository = 'flowlytix'
)
# 'Continue', not 'Stop': in Windows PowerShell 5.1, 'Stop' turns any stderr output from aws
# or docker (even harmless warnings and progress) into a fatal error. Every native command
# below is checked by its exit code instead.
$ErrorActionPreference = 'Continue'
$root = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) '..\..')
$common = @('--region', $Region)
if ($Profile) { $common += @('--profile', $Profile) }

function Invoke-Aws { & aws @args @common; if ($LASTEXITCODE -ne 0) { throw "aws $($args -join ' ') failed" } }

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) { throw 'AWS CLI not found. Install it first (see deployment\aws\README.md).' }
foreach ($required in 'models\manifest.json', 'app\package-lock.json') {
  if (-not (Test-Path (Join-Path $root $required))) { throw "Missing $required. The image needs the trained models and frontend lockfile." }
}

$account = Invoke-Aws sts get-caller-identity --query Account --output text
$registry = "$account.dkr.ecr.$Region.amazonaws.com"

& aws ecr describe-repositories --repository-names $Repository @common *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Creating private ECR repository '$Repository'"
  Invoke-Aws ecr create-repository --repository-name $Repository --image-scanning-configuration 'scanOnPush=true' `
    --encryption-configuration 'encryptionType=AES256' | Out-Null
  # Keep only the 3 newest images so storage stays small.
  $policy = '{"rules":[{"rulePriority":1,"description":"keep 3","selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":3},"action":{"type":"expire"}}]}'
  $policyFile = New-TemporaryFile
  [System.IO.File]::WriteAllText($policyFile, $policy)
  Invoke-Aws ecr put-lifecycle-policy --repository-name $Repository --lifecycle-policy-text "file://$policyFile" | Out-Null
  Remove-Item $policyFile
}

$tag = Get-Date -Format 'yyyyMMdd-HHmmss'
$uri = "${registry}/${Repository}:$tag"
docker build --platform linux/amd64 -t $uri $root
if ($LASTEXITCODE -ne 0) { throw 'docker build failed' }

# The 12-hour ECR token is too long for Windows Credential Manager, so log in and push with
# a temporary, private Docker config that is deleted afterwards. The engine address is kept.
$engine = (docker context inspect --format '{{.Endpoints.docker.Host}}' | Out-String).Trim()
$tempConfig = Join-Path ([IO.Path]::GetTempPath()) ("ecr-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempConfig | Out-Null
$savedConfig, $savedHost, $savedPath = $env:DOCKER_CONFIG, $env:DOCKER_HOST, $env:Path
$dockerExe = (Get-Command docker).Source
try {
  [System.IO.File]::WriteAllText((Join-Path $tempConfig 'config.json'), '{"auths":{}}')
  $env:DOCKER_CONFIG = $tempConfig
  if ($engine) { $env:DOCKER_HOST = $engine }
  # Docker silently uses any credential helper found on PATH; hide them for these two commands.
  $env:Path = ($env:Path -split ';' | Where-Object {
      $_ -and -not (Get-ChildItem -LiteralPath $_ -Filter 'docker-credential-*' -ErrorAction SilentlyContinue) }) -join ';'
  # Windows PowerShell 5.1 corrupts text piped into native programs, so pass the token
  # through cmd from a private file inside the temporary config folder.
  $tokenFile = Join-Path $tempConfig 'token'
  [System.IO.File]::WriteAllText($tokenFile, (Invoke-Aws ecr get-login-password | Out-String).Trim(),
    (New-Object System.Text.UTF8Encoding $false))
  cmd /c "`"$dockerExe`" login --username AWS --password-stdin $registry < `"$tokenFile`""
  if ($LASTEXITCODE -ne 0) { throw 'docker login to ECR failed' }
  Remove-Item -LiteralPath $tokenFile -Force
  & $dockerExe push $uri
  if ($LASTEXITCODE -ne 0) { throw 'docker push failed' }
} finally {
  $env:DOCKER_CONFIG, $env:DOCKER_HOST, $env:Path = $savedConfig, $savedHost, $savedPath
  Remove-Item -LiteralPath $tempConfig -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host "Image pushed: $uri" -ForegroundColor Green
Write-Host 'Use this value for -ImageUri and for IMAGE_URI in the server .env.'
