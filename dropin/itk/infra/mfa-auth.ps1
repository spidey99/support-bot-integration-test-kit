# MFA Helper - Sets up temporary credentials
# Usage: .\mfa-auth.ps1 -Code 123456

param(
    [Parameter(Mandatory=$true)]
    [string]$Code,
    
    [Parameter(Mandatory=$false)]
    [string]$MfaArn = $env:ITK_MFA_ARN
)

if (-not $MfaArn) {
    Write-Host "Error: MFA ARN not provided. Set ITK_MFA_ARN or pass -MfaArn" -ForegroundColor Red
    exit 1
}

$MFA_ARN = $MfaArn

Write-Host "Getting session token..." -ForegroundColor Yellow

$result = aws sts get-session-token `
    --serial-number $MFA_ARN `
    --token-code $Code `
    --duration-seconds 43200 `
    --output json 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed: $result" -ForegroundColor Red
    exit 1
}

$creds = $result | ConvertFrom-Json

# Set environment variables for this session
$env:AWS_ACCESS_KEY_ID = $creds.Credentials.AccessKeyId
$env:AWS_SECRET_ACCESS_KEY = $creds.Credentials.SecretAccessKey
$env:AWS_SESSION_TOKEN = $creds.Credentials.SessionToken

# Also save to a profile for persistence
aws configure set aws_access_key_id $creds.Credentials.AccessKeyId --profile itk-mfa
aws configure set aws_secret_access_key $creds.Credentials.SecretAccessKey --profile itk-mfa
aws configure set aws_session_token $creds.Credentials.SessionToken --profile itk-mfa

Write-Host "MFA authenticated! Credentials valid for 12 hours." -ForegroundColor Green
Write-Host "Profile 'itk-mfa' created. Use: `$env:AWS_PROFILE='itk-mfa'" -ForegroundColor Cyan

# Verify
aws sts get-caller-identity
