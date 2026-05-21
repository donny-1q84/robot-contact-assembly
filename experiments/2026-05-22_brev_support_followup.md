# Brev Support Follow-Up

Date: 2026-05-22 local / 2026-05-21 UTC

## Summary

The org `NCA-57cf-29515` is still seeing Brev lifecycle failures even for probe-only instances. These runs did not install Isaac or run any robotics workload. They only attempted:

```text
create instance -> wait for SSH READY -> probe -> delete
```

Both recent probes failed before SSH.

## Incident 1: GCP L4 Probe

```text
run dir: artifacts/gpu_gate/2026-05-21T05-06-38Z_isaac-probe-only-l4
instance name: isaac-probe-only-l4
instance id: o9l5b7lcr
type: g2-standard-4:nvidia-l4:1
price observed: $0.85/hr
failure: create said Ready, but brev ls stayed RUNNING / BUILDING / NOT READY for 195s
cleanup: repeated delete by name/id, final no visible instances, JSON workspaces=null
```

## Incident 2: Nebius L40S Probe

```text
run dir: artifacts/gpu_gate/2026-05-21T22-21-15Z_isaac-probe-only-nebius-l40s
instance name: isaac-probe-only-nebius-l40s
instance id: f7yhguiy5
type: gpu-l40s-a.1gpu-8vcpu-32gb
price observed: $1.86/hr
failure: create said Ready, but brev ls stayed RUNNING / BUILDING / NOT READY for 248s
cleanup: repeated delete by name/id, final no visible instances, JSON workspaces=null
```

During Nebius cleanup, Brev also returned:

```text
rpc error: code = Internal desc = context deadline exceeded
rpc error: code = Internal desc = downstream duration timeout
```

and showed transient states:

```text
RUNNING / COMPLETED / READY
DELETING / COMPLETED / NOT READY
```

## Draft Email

Subject:

```text
Follow-up: repeated probe-only Brev lifecycle failures in org NCA-57cf-29515
```

Body:

```text
Hi Brev Support,

I am following up because the same lifecycle issue is still occurring in my org NCA-57cf-29515, even with probe-only runs that do not install Isaac or run any workload.

Recent probe-only incidents:

1. GCP L4
- Instance name: isaac-probe-only-l4
- Instance id: o9l5b7lcr
- Type: g2-standard-4:nvidia-l4:1
- Run timestamp: 2026-05-21T05-06-38Z
- Symptom: create reported Ready, but `brev ls instances --all` stayed RUNNING / BUILDING / NOT READY for 195 seconds.
- Cleanup: repeated delete by name/id eventually cleared it. Final checks showed no visible instances and JSON workspaces=null.

2. Nebius L40S
- Instance name: isaac-probe-only-nebius-l40s
- Instance id: f7yhguiy5
- Type: gpu-l40s-a.1gpu-8vcpu-32gb
- Run timestamp: 2026-05-21T22-21-15Z
- Symptom: create reported Ready, but `brev ls instances --all` stayed RUNNING / BUILDING / NOT READY for 248 seconds.
- During cleanup, Brev also showed rpc errors: "context deadline exceeded" and "downstream duration timeout".
- Cleanup: repeated delete by name/id eventually cleared it. Final checks showed no visible instances and JSON workspaces=null.

These were probe-only runs: create instance, wait for SSH readiness, probe nvidia-smi/disk, then delete. They never reached SSH, and no Isaac or robotics process was started.

Could you please investigate why the create path reports Ready while `brev ls instances --all` remains BUILDING / NOT READY, and why deletion can temporarily show RUNNING / COMPLETED / READY or get RPC timeouts? Please also confirm that no hidden workspace, deployment, volume, or other billable resource remains in org NCA-57cf-29515 from these attempts.

I am currently avoiding further Brev usage until this lifecycle issue is confirmed fixed.

Best regards,
Shenghan Gao
```
