[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectId = 'project-757198e6-df23-4e75-b08'

function Add-SecretVersionWithoutEcho {
    param([string]$SecretName, [SecureString]$SecureValue)
    $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        $PlainValue = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
        $StartInfo = [Diagnostics.ProcessStartInfo]::new()
        $StartInfo.FileName = 'gcloud'
        $StartInfo.ArgumentList.Add('secrets')
        $StartInfo.ArgumentList.Add('versions')
        $StartInfo.ArgumentList.Add('add')
        $StartInfo.ArgumentList.Add($SecretName)
        $StartInfo.ArgumentList.Add("--project=$ProjectId")
        $StartInfo.ArgumentList.Add('--data-file=-')
        $StartInfo.ArgumentList.Add('--quiet')
        $StartInfo.RedirectStandardInput = $true
        $StartInfo.RedirectStandardOutput = $true
        $StartInfo.RedirectStandardError = $true
        $StartInfo.UseShellExecute = $false
        $Process = [Diagnostics.Process]::Start($StartInfo)
        $Process.StandardInput.Write($PlainValue)
        $Process.StandardInput.Close()
        $Process.WaitForExit()
        if ($Process.ExitCode -ne 0) {
            throw "gcloud failed while adding a version to $SecretName"
        }
    }
    finally {
        if ($Pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
        }
        $PlainValue = $null
    }
}

$ApiKey = Read-Host 'Alpaca PAPER API key (input hidden)' -AsSecureString
$ApiSecret = Read-Host 'Alpaca PAPER API secret (input hidden)' -AsSecureString
$AccountId = Read-Host 'Expected new PAPER account ID (input hidden)' -AsSecureString
Add-SecretVersionWithoutEcho 'alphaledger-paper-api-key-20260828' $ApiKey
Add-SecretVersionWithoutEcho 'alphaledger-paper-api-secret-20260828' $ApiSecret
Add-SecretVersionWithoutEcho 'alphaledger-paper-account-id-20260828' $AccountId
Write-Output 'Three secret versions were added without printing their values.'
