<#
Installs the flowlytix-power automation. Safe to re-run; it does not stop or start anything.
  .\deployment\aws\setup-power.ps1
#>
param([string]$Profile = 'flowlytix', [string]$Region = 'ap-south-1')
$ErrorActionPreference = 'Continue'
$awsExe = Join-Path $env:LOCALAPPDATA 'Programs\Amazon\AWSCLIV2\aws.exe'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$state = Get-Content (Join-Path $here 'out\state.json') -Raw | ConvertFrom-Json
$work = Join-Path ([IO.Path]::GetTempPath()) ('flowlytix-power-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
$common = @('--profile', $Profile, '--region', $Region)
$name = 'flowlytix-power'
$param = '/flowlytix/power_mode'
$account = $state.account

function Invoke-Aws {
  $out = & $awsExe @args @common 2>&1 | ForEach-Object { "$_" }
  if ($LASTEXITCODE -ne 0) { throw "aws $($args[0..1] -join ' ') failed: $out" }
  return $out
}
function Test-Aws { & $awsExe @args @common *> $null; return ($LASTEXITCODE -eq 0) }
function Write-JsonFile($file, $value) {
  $path = Join-Path $work $file
  [IO.File]::WriteAllText($path, ($value | ConvertTo-Json -Depth 10 -Compress))
  return "file://$path"
}

try {
  $trust = Write-JsonFile 'trust.json' @{ Version = '2012-10-17'; Statement = @(@{ Effect = 'Allow'; Principal = @{ Service = 'lambda.amazonaws.com' }; Action = 'sts:AssumeRole' }) }
  if (-not (Test-Aws iam get-role --role-name $name)) { Invoke-Aws iam create-role --role-name $name --assume-role-policy-document $trust | Out-Null }
  $policy = Write-JsonFile 'policy.json' @{ Version = '2012-10-17'; Statement = @(
    @{ Effect = 'Allow'; Action = 'ec2:DescribeInstances'; Resource = '*' },
    @{ Effect = 'Allow'; Action = @('ec2:StartInstances', 'ec2:StopInstances'); Resource = "arn:aws:ec2:${Region}:${account}:instance/$($state.instance)" },
    @{ Effect = 'Allow'; Action = @('rds:DescribeDBInstances', 'rds:StartDBInstance', 'rds:StopDBInstance'); Resource = "arn:aws:rds:${Region}:${account}:db:$($state.rds)" },
    @{ Effect = 'Allow'; Action = @('ssm:GetParameter', 'ssm:PutParameter'); Resource = "arn:aws:ssm:${Region}:${account}:parameter$param" },
    @{ Effect = 'Allow'; Action = @('logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents'); Resource = "arn:aws:logs:${Region}:${account}:log-group:/aws/lambda/${name}*" }
  ) }
  Invoke-Aws iam put-role-policy --role-name $name --policy-name $name --policy-document $policy | Out-Null

  if (-not (Test-Aws ssm get-parameter --name $param)) { Invoke-Aws ssm put-parameter --name $param --type String --value running | Out-Null }

  $zip = Join-Path $work 'function.zip'
  Compress-Archive -LiteralPath (Join-Path $here 'power\lambda_function.py') -DestinationPath $zip
  $variables = Write-JsonFile 'env.json' @{ Variables = @{ INSTANCE_ID = $state.instance; DB_ID = $state.rds; STATE_PARAMETER = $param } }
  if (Test-Aws lambda get-function --function-name $name) {
    Invoke-Aws lambda update-function-code --function-name $name --zip-file "fileb://$zip" | Out-Null
    Invoke-Aws lambda wait function-updated --function-name $name | Out-Null
    Invoke-Aws lambda update-function-configuration --function-name $name --environment $variables --timeout 30 --memory-size 128 | Out-Null
  } else {
    $created = $false
    for ($i = 0; $i -lt 12 -and -not $created; $i++) {   # a new IAM role takes a few seconds to appear
      $created = Test-Aws lambda create-function --function-name $name --runtime python3.12 --handler lambda_function.lambda_handler `
        --role "arn:aws:iam::${account}:role/$name" --zip-file "fileb://$zip" --environment $variables --timeout 30 --memory-size 128
      if (-not $created) { Start-Sleep -Seconds 5 }
    }
    if (-not $created) { throw 'Could not create the Lambda function' }
  }
  Invoke-Aws lambda wait function-active-v2 --function-name $name | Out-Null

  $rule = Invoke-Aws events put-rule --name $name --schedule-expression 'rate(5 minutes)' --state ENABLED --description 'FlowLytix power steps' --query RuleArn --output text
  $ruleArn = "$rule".Trim()
  if (-not (Test-Aws lambda get-policy --function-name $name)) {
    Invoke-Aws lambda add-permission --function-name $name --statement-id events --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn $ruleArn | Out-Null
  }
  $targets = Write-JsonFile 'targets.json' @{ Rule = $name; Targets = @(@{ Id = 'power'; Arn = "arn:aws:lambda:${Region}:${account}:function:$name" }) }
  Invoke-Aws events put-targets --cli-input-json $targets | Out-Null
  # Stay inside CloudWatch's free allowance of 3 dashboards.
  $dashboards = @((Invoke-Aws cloudwatch list-dashboards --query 'DashboardEntries[].DashboardName' --output text) -split '\s+' | Where-Object { $_ -and $_ -ne 'None' })
  if ($dashboards -notcontains 'FlowLytix-Control' -and $dashboards.Count -ge 3) {
    throw 'This account already has 3 CloudWatch dashboards; a fourth would be billed.'
  }
  $body = Write-JsonFile 'dashboard.json' @{ widgets = @(@{
    type = 'custom'; x = 0; y = 0; width = 14; height = 8
    properties = @{ title = 'FlowLytix power control'; endpoint = "arn:aws:lambda:${Region}:${account}:function:$name"
      updateOn = @{ refresh = $true; resize = $false; timeRange = $false } }
  }) }
  Invoke-Aws cloudwatch put-dashboard --dashboard-name FlowLytix-Control --dashboard-body $body | Out-Null
  Write-Host 'flowlytix-power installed.'
  Write-Host "Dashboard: https://${Region}.console.aws.amazon.com/cloudwatch/home?region=${Region}#dashboards/dashboard/FlowLytix-Control"
} finally {
  Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
