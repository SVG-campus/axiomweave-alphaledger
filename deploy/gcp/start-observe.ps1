$ErrorActionPreference = 'Stop'
$ProjectId = 'project-757198e6-df23-4e75-b08'
$Zone = 'us-central1-a'
$VmName = 'alphaledger-hackathon-20260828'
$Command = 'sudo rm -f /etc/alphaledger/paper-enabled && sudo /usr/local/sbin/alphaledger-load-secrets && sudo systemctl enable --now alphaledger-runner && sudo systemctl --no-pager --full status alphaledger-runner'
gcloud compute ssh $VmName --project=$ProjectId --zone=$Zone --tunnel-through-iap --command=$Command
