[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RepositoryUrl,
    [Parameter(Mandatory = $true)][string]$RepositoryRef
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectId = 'project-757198e6-df23-4e75-b08'
$Zone = 'us-central1-a'
$Region = 'us-central1'
$VmName = 'alphaledger-hackathon-20260828'
$ServiceAccountName = 'alphaledger-hackathon'
$ServiceAccountEmail = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$FirewallName = 'alphaledger-demo-http-20260828'
$SshFirewallName = 'alphaledger-iap-ssh-20260828'
$NetworkName = 'alphaledger-net-20260828'
$SubnetName = 'alphaledger-subnet-20260828'
$Labels = 'owner=axiomweave,scope=alpaca-hackathon,created=20260828'
$Secrets = @(
    'alphaledger-paper-api-key-20260828',
    'alphaledger-paper-api-secret-20260828',
    'alphaledger-paper-account-id-20260828'
)

if ((gcloud config get-value project).Trim() -ne $ProjectId) {
    throw "Active gcloud project is not $ProjectId"
}
gcloud projects describe $ProjectId --format='value(projectId)' | Out-Null

$ExistingVm = gcloud compute instances list --project=$ProjectId --filter="name=$VmName" --format='value(name)'
if ($ExistingVm) { throw "VM $VmName already exists; refusing to modify it." }
$ExistingFirewall = gcloud compute firewall-rules list --project=$ProjectId --filter="name=$FirewallName" --format='value(name)'
if ($ExistingFirewall) { throw "Firewall $FirewallName already exists; refusing to modify it." }
$ExistingNetwork = gcloud compute networks list --project=$ProjectId --filter="name=$NetworkName" --format='value(name)'
if ($ExistingNetwork) { throw "Network $NetworkName already exists; refusing to modify it." }

gcloud services enable secretmanager.googleapis.com iam.googleapis.com iap.googleapis.com --project=$ProjectId --quiet

$ExistingSa = gcloud iam service-accounts list --project=$ProjectId --filter="email=$ServiceAccountEmail" --format='value(email)'
if (-not $ExistingSa) {
    gcloud iam service-accounts create $ServiceAccountName --project=$ProjectId --display-name='AlphaLedger Hackathon Runner' --quiet
}
else {
    throw "Service account $ServiceAccountEmail already exists; refusing to modify it."
}

foreach ($Secret in $Secrets) {
    $ExistingSecret = gcloud secrets list --project=$ProjectId --filter="name:$Secret" --format='value(name)'
    if ($ExistingSecret) { throw "Secret $Secret already exists; refusing to reuse it." }
    gcloud secrets create $Secret --project=$ProjectId --replication-policy=automatic --labels=$Labels --quiet
    gcloud secrets add-iam-policy-binding $Secret --project=$ProjectId --member="serviceAccount:$ServiceAccountEmail" --role='roles/secretmanager.secretAccessor' --quiet | Out-Null
}

gcloud compute networks create $NetworkName --project=$ProjectId --subnet-mode=custom --bgp-routing-mode=regional --quiet
gcloud compute networks subnets create $SubnetName --project=$ProjectId --network=$NetworkName --region=$Region --range=10.42.0.0/28 --enable-private-ip-google-access --quiet
gcloud compute firewall-rules create $FirewallName --project=$ProjectId --network=$NetworkName --direction=INGRESS --action=ALLOW --rules=tcp:80 --source-ranges=0.0.0.0/0 --target-tags=alphaledger-demo --description='Public HTTP only for AlphaLedger hackathon demo' --quiet
gcloud compute firewall-rules create $SshFirewallName --project=$ProjectId --network=$NetworkName --direction=INGRESS --action=ALLOW --rules=tcp:22 --source-ranges=35.235.240.0/20 --target-tags=alphaledger-iap --description='IAP TCP forwarding only for AlphaLedger administration' --quiet

gcloud compute instances create $VmName --project=$ProjectId --zone=$Zone --machine-type=e2-micro --image-family=debian-12 --image-project=debian-cloud --boot-disk-size=20GB --boot-disk-type=pd-standard --network-interface="network=$NetworkName,subnet=$SubnetName" --service-account=$ServiceAccountEmail --scopes=cloud-platform --tags=alphaledger-demo,alphaledger-iap --labels=$Labels --metadata="repo-url=$RepositoryUrl,repo-ref=$RepositoryRef" --metadata-from-file="startup-script=$PSScriptRoot\startup.sh" --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring --quiet

$Ip = gcloud compute instances describe $VmName --project=$ProjectId --zone=$Zone --format='value(networkInterfaces[0].accessConfigs[0].natIP)'
Write-Output "Created isolated VM: $VmName"
Write-Output "Demo URL after startup completes: http://$Ip"
Write-Output 'Runner remains disabled and no secret versions exist.'
