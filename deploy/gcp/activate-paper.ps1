$ErrorActionPreference = 'Stop'
$ProjectId = 'project-757198e6-df23-4e75-b08'
$Zone = 'us-central1-a'
$VmName = 'alphaledger-hackathon-20260828'

Write-Output 'THIS CHANGES THE REMOTE CONTROLLER FROM READ-ONLY OBSERVATION TO ALPACA PAPER ORDER SUBMISSION.'
$Confirmation = Read-Host 'Type I_UNDERSTAND_THIS_SUBMITS_A_PAPER_ORDER to continue'
if ($Confirmation -cne 'I_UNDERSTAND_THIS_SUBMITS_A_PAPER_ORDER') {
    throw 'Exact paper-order acknowledgement was not supplied.'
}
$Command = 'sudo /usr/local/sbin/alphaledger-load-secrets && sudo touch /etc/alphaledger/paper-enabled && sudo chmod 0640 /etc/alphaledger/paper-enabled && sudo systemctl restart alphaledger-runner && sudo systemctl --no-pager --full status alphaledger-runner'
gcloud compute ssh $VmName --project=$ProjectId --zone=$Zone --tunnel-through-iap --command=$Command
