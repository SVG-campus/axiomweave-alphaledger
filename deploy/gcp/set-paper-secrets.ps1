[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectId = 'project-757198e6-df23-4e75-b08'
$GcloudCommand = Get-Command gcloud -ErrorAction Stop
$GcloudCmdPath = if ($GcloudCommand.Source.EndsWith('.ps1', [StringComparison]::OrdinalIgnoreCase)) {
    [IO.Path]::ChangeExtension($GcloudCommand.Source, '.cmd')
}
else {
    $GcloudCommand.Source
}
if (-not (Test-Path -LiteralPath $GcloudCmdPath -PathType Leaf)) {
    throw "The Google Cloud CLI command wrapper was not found."
}

function Invoke-GcloudProcess {
    param(
        [Parameter(Mandatory = $true)][string]$CommandArguments,
        [SecureString]$StandardInputValue
    )

    $Pointer = [IntPtr]::Zero
    $PlainValue = $null
    try {
        if ($null -ne $StandardInputValue) {
            $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($StandardInputValue)
            $PlainValue = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
        }

        # Windows PowerShell 5.1 does not expose ProcessStartInfo.ArgumentList.
        # Run the installed gcloud.cmd wrapper through cmd.exe and keep secret
        # material exclusively on redirected standard input.
        $StartInfo = [Diagnostics.ProcessStartInfo]::new()
        $StartInfo.FileName = $env:ComSpec
        $StartInfo.Arguments = "/d /s /c `"`"$GcloudCmdPath`" $CommandArguments`""
        $StartInfo.RedirectStandardInput = $true
        $StartInfo.RedirectStandardOutput = $true
        $StartInfo.RedirectStandardError = $true
        $StartInfo.UseShellExecute = $false
        $StartInfo.CreateNoWindow = $true

        $Process = [Diagnostics.Process]::Start($StartInfo)
        if ($null -ne $PlainValue) {
            $Process.StandardInput.Write($PlainValue)
        }
        $Process.StandardInput.Close()
        $StandardOutput = $Process.StandardOutput.ReadToEnd()
        $StandardError = $Process.StandardError.ReadToEnd()
        $Process.WaitForExit()

        return [pscustomobject]@{
            ExitCode = $Process.ExitCode
            StandardOutput = $StandardOutput
            StandardError = $StandardError
        }
    }
    finally {
        if ($Pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
        }
        $PlainValue = $null
    }
}

function Add-SecretVersionWithoutEcho {
    param([string]$SecretName, [SecureString]$SecureValue)
    if ($SecretName -notmatch '^[a-z0-9-]+$') {
        throw 'Secret name failed the allowlist.'
    }
    $Arguments = "secrets versions add `"$SecretName`" --project=`"$ProjectId`" --data-file=- --quiet"
    $Result = Invoke-GcloudProcess -CommandArguments $Arguments -StandardInputValue $SecureValue
    if ($Result.ExitCode -ne 0) {
        throw "gcloud failed while adding a version to $SecretName"
    }
}

if ($ValidateOnly) {
    $Validation = Invoke-GcloudProcess -CommandArguments '--version'
    if ($Validation.ExitCode -ne 0) {
        throw 'The Google Cloud CLI failed the process-launch validation.'
    }
    Write-Output 'PowerShell 5.1-compatible gcloud launch validated. No secret was read or written.'
    return
}

$ApiKey = Read-Host 'Alpaca PAPER API key (input hidden)' -AsSecureString
$ApiSecret = Read-Host 'Alpaca PAPER API secret (input hidden)' -AsSecureString
$AccountId = Read-Host 'Expected new PAPER account number shown next to Paper Account (input hidden)' -AsSecureString
Add-SecretVersionWithoutEcho 'alphaledger-paper-api-key-20260828' $ApiKey
Add-SecretVersionWithoutEcho 'alphaledger-paper-api-secret-20260828' $ApiSecret
Add-SecretVersionWithoutEcho 'alphaledger-paper-account-id-20260828' $AccountId
Write-Output 'Three secret versions were added without printing their values.'
