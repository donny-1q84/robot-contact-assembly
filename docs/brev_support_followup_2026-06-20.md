# Brev Support Follow-up Draft - 2026-06-20

Gmail draft status:

```text
created: yes
sent: no
draft_id: r-7545863501805331854
message_id: 19ee2c7896acfa40
thread_id: 19e4e182e6100df1
created_utc: 2026-06-20T02:06:33Z
rechecked_utc: 2026-06-20T02:11:09Z
attachment: artifacts/brev_lifecycle_incidents/2026-06-20T02-01-55Z.tar.gz
```

Latest local evidence bundle after the user logged back in and the safety gates
were rechecked:

```text
created_utc: 2026-06-20T03:14:04Z
archive: artifacts/brev_lifecycle_incidents/2026-06-20T03-14-04Z.tar.gz
sha256: b926aff0547179db8a81d3b257be719cec921a50be37863064c7df5dfa069c22
contains: brev_paid_safety_status.txt, paid_preflight_hold_block.txt, local_quality_checks.txt
gmail_draft_attachment: still the earlier 2026-06-20T02-01-55Z bundle unless the draft is manually updated
```

Subject:

```text
Follow-up: AWS Isaac Launchable lifecycle failures before shell access in org NCA-57cf-29515
```

Draft:

```text
Hi Brev Support,

I am following up with two AWS Isaac Launchable lifecycle failures in org
NCA-57cf-29515. Both attempts used the official Isaac Launchable:

https://brev.nvidia.com/launchable/deploy/now?launchableID=env-35JP2ywERLgqtD0b0MIeK1HnF46

Attempt 1:
- Instance: isaac-launchable-b18cd5 / t7f0c8qh0
- Provider/type: AWS g6e.4xlarge L40S
- Approx. UI price: $3.61/hr
- Behavior: stayed at STARTING / BUILDING / NOT READY for about 10 minutes.
- Project workload: not run. No project bundle was uploaded and no shell access
  was reached.
- Cleanup: CLI delete, UI delete confirmation, stop, stop --all, and repeated
  delete attempts were needed while the workspace moved through
  UNHEALTHY/DELETING. Cleanup was eventually confirmed when `brev ls instances
  --json --all` returned `{"workspaces": null}`.

Attempt 2:
- Instance: isaac-launchable-7ccc42 / hqo1aftwz
- Provider/type: AWS g6e.4xlarge L40S
- Approx. UI price: $3.64-$3.65/hr
- Behavior: STARTING / BUILDING / NOT READY, then UNHEALTHY before shell access.
  The UI briefly showed Running with an IP address, but VM Mode and script were
  still Waiting and the CLI shell status was NOT READY.
- Project workload: not run. No project bundle was uploaded and no shell access
  was reached.
- Cleanup: CLI delete, stop, delete-by-id, and UI delete confirmation were
  issued. The workspace remained in DELETING / UNHEALTHY for several minutes,
  then cleanup was eventually confirmed when `brev ls instances --json --all`
  returned `{"workspaces": null}`.

Current state:
- `brev healthcheck` returned Healthy.
- `/Users/Shenghan/bin/brev ls instances --json --all` currently returns
  `{"workspaces": null}`.
- I have paused further paid Launchable retries locally because both attempts
  failed before shell access and before any Isaac/project command ran.
- Local incident evidence bundle:
  `artifacts/brev_lifecycle_incidents/2026-06-20T03-14-04Z.tar.gz`
  (`sha256=b926aff0547179db8a81d3b257be719cec921a50be37863064c7df5dfa069c22`).

Could you please check whether these two workspaces left any hidden billable
resources, and whether there is a known AWS Launchable provisioning issue for
this org/provider path?

Best regards,
Shenghan Gao
```

Local evidence commands already run:

```bash
/Users/Shenghan/bin/brev ls instances --json --all
/Users/Shenghan/bin/brev delete isaac-launchable-b18cd5 t7f0c8qh0
/Users/Shenghan/bin/brev stop isaac-launchable-b18cd5
/Users/Shenghan/bin/brev stop --all
/Users/Shenghan/bin/brev delete isaac-launchable-7ccc42 hqo1aftwz
/Users/Shenghan/bin/brev stop isaac-launchable-7ccc42
/Users/Shenghan/bin/brev delete hqo1aftwz
```

Local safety guard added after the incident:

```text
docs/brev_launchable_lifecycle_hold.md
scripts/paid_compute_preflight.sh blocks new paid creation while that hold file exists,
unless RCA_ACK_BREV_LIFECYCLE_RISK=1 is set deliberately.
scripts/check_brev_lifecycle_hold_clearance.sh confirms visible_instances=0 and
paid_preflight_hold_block=confirmed before any human considers clearing the hold.

After the user logged back in on 2026-06-20, the read-only Brev CLI check was
re-run at 2026-06-20T02:11:09Z and still returned `{"workspaces": null}`.
Local quality checks and hold-clearance checks both passed, but the lifecycle
hold remains active.
```

Latest local evidence bundle after the user logged back in, the Brev org was
rechecked as empty, and the budget-estimate/manual credit-verification guards
were validated:

```text
artifacts/brev_lifecycle_incidents/2026-06-20T03-14-04Z.tar.gz
sha256: b926aff0547179db8a81d3b257be719cec921a50be37863064c7df5dfa069c22
contains: brev_paid_safety_status.txt, paid_preflight_hold_block.txt, local_quality_checks.txt
```
