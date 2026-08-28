# Isolated GCP deployment

Target project: `project-757198e6-df23-4e75-b08`. The read-only inventory on 2026-08-28 found no
Compute Engine VMs, Cloud Run was disabled, Secret Manager was disabled, and only the default
Compute service account existed. The scripts use only new `alphaledger-*` names.

Current deployment: `alphaledger-hackathon-20260828` is serving the credential-free demo at
<http://34.27.11.180> from public commit
`5a97562ee4f710e7fa7d9a9f15033fe1c1d3f6af`. The runner is active in GET-only `observe` mode
after successful reconciliation of the fresh $100,000 Level-3 account with zero positions and
orders. The paper-enable flag is absent, and each of the three secret containers has exactly one
enabled version.

## Architecture

- One non-preemptible `e2-micro` in `us-central1-a`, 20 GB standard disk.
- A new custom `alphaledger-net-*` VPC/subnet; no existing network or firewall is modified.
- Public Nginx → local Streamlit demo. The demo service has no broker environment variables.
- The public demo service is network-isolated to localhost, blocking metadata and external egress;
  only Nginx can reach its local Streamlit listener.
- Separate non-login runner user and systemd service.
- Three new Secret Manager secrets, scoped to one dedicated service account.
- Official Alpaca CLI v0.0.14 pinned by SHA-256.
- Administrative SSH is limited to Google's IAP TCP-forwarding range.
- Runner default: disabled, then read-only `observe`; `paper` requires the exact interactive ACK.
- No live environment variable or live endpoint is permitted.

Google currently lists one eligible non-preemptible `e2-micro` in `us-central1` plus up to 30 GB
standard disk in its Free Tier. Eligibility depends on the billing account and other usage; the
on-demand VM rate is about $0.00838/hour before disk/network, so the four-day event remains below
the frozen $10 soft budget even without the VM-hours benefit, barring unusual egress.

## Order of operations

1. Publish and freeze a public repository commit. Do not deploy a moving branch.
2. Run `provision.ps1 -RepositoryUrl <public-url> -RepositoryRef <commit-sha>`.
3. Verify the public demo from a signed-out browser.
4. Run `set-paper-secrets.ps1` locally. Never paste keys into chat.
5. Run `start-observe.ps1`. Inspect redacted logs and prove the user-visible `PA...` paper account
   number is the pinned fresh $100,000 Level-3 paper account with no positions/orders. Alpaca's API
   `id` is a separate internal UUID and is not the LabLab/dashboard account reference.
6. Only after explicit paper-order authorization, run `activate-paper.ps1`. It may be run over the
   weekend: the competition clock remains pre-window until Monday 09:30 ET and entries remain
   disabled until 10:20 ET.

The activation script is intentionally not automated from this repository. A human must type the
exact acknowledgement at action time. Do not run it for a live account.
