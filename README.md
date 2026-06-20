# Robot Contact Assembly

Robot assembly project built around a narrow Isaac Lab `peg-in-hole` workflow. Phase 1 closed the full remote training/evaluation/artifact loop with a proxy tip-to-socket task, and the current mainline runtime now upgrades that shell to a simple physical peg + guide-socket contact environment.

## Project snapshot

- Task: `peg-in-hole`
- Simulator stack: Isaac Sim + Isaac Lab
- Robot: Franka Panda
- Control: relative differential IK and joint-position contact-control variants
- Policy: PPO (`rsl_rl`) plus scripted and BC/IL baselines
- Execution model: local planning and artifact archive + remote Brev GPU runtime
- Current blocking status: the contact-physics fix is implemented locally, but not yet validated on a real Isaac runtime. Until `scripts/run_launchable_contact_physics_smoke.sh` passes, the pulled log is installed with `scripts/archive_contact_smoke_log.sh`, and `scripts/check_phase2_contact_gate.py` reports PASS, all older Phase 2 "true-contact", near-miss, BC, and reset-candidate metrics are diagnostic history only.
- Current runtime shell: dynamic peg rigid body welded to the hand, fixed guide-socket contact walls, wall-filtered contact-force observations, and physical socket-frame success logic

## Phase 1 Scope

Phase 1 was intentionally a proxy precursor, not a finished contact assembly task:

- peg tip was modeled as a fixed tool offset
- socket target was modeled as a commanded pose
- success was computed from pose thresholds instead of peg/socket geometry

Those limitations are important context for every Phase 1 metric in this repo. The current runtime code has now moved to a contact-guided shell, and the first contact-shell transfer eval has now been recorded separately from the archived proxy metrics.

## Highlights

- Custom Isaac Lab external task package that started as a proxy insertion task and now includes a contact-guided peg/socket shell
- Reproducible remote experiment workflow on Brev for training, evaluation, checkpoint sweep, and artifact pullback
- Structured failure analysis across multiple reward and curriculum variants instead of one-off PPO runs
- CV-ready Phase 1 and Phase 2 summaries with concrete metrics, limitations, and next-step technical direction

## Best results so far

The strongest published Phase 1 runs were:

- Base run `phase1_fix6_formal`
  - `lateral=0.0074`
  - `axial=0.0027`
  - `rot=0.7190`
  - `success=0.000`
- Continuation run `finetune_fix8_from_fix6`
  - `lateral=0.0105`
  - `axial=0.0092`
  - `rot=0.6265`
  - `success=0.000`

Interpretation:

- the policy reliably learns socket approach and near-insertion alignment
- those metrics were achieved under the archived proxy task, not the new contact shell
- under the proxy task design, late-stage reward retuning showed diminishing returns

See [experiments/2026-04-05_phase1_rl_baseline.md](experiments/2026-04-05_phase1_rl_baseline.md) for the full run history and [docs/phase1_cv_summary.md](docs/phase1_cv_summary.md) for the concise CV/interview framing.

Historical Phase 2 scripted result, now diagnostic only until regenerated under the validated contact-physics task:

- Run `2026-05-17T19-47-06Z`
  - `success_step=1538`
  - `lateral=0.0047`
  - `axial=0.0419`
  - `rot=0.1909`
  - `contact=0.6927`

At the time, this was treated as a shallow peg/socket contact-shell success under a deliberately shallow gate:

- `xy < 0.005 m`
- `z < 0.045 m`
- `rot < 0.20 rad`
- `contact >= 0.5`

The strict scripted gate still has no success. The closest force-aware retention run reached:

- Run `2026-05-17T23-32-18Z`
  - `step=1543`
  - `lateral=0.0052`
  - `axial=0.0413`
  - `rot=0.1812`
  - `contact=0.5298`

It missed the strict gate by about `0.20 mm` lateral error and `0.0012 rad` rotation error. See [experiments/2026-05-17_phase2_near_success_diagnosis.md](experiments/2026-05-17_phase2_near_success_diagnosis.md) and [docs/phase2_cv_summary.md](docs/phase2_cv_summary.md).

Important current caveat: the 2026-06-11 contact-physics audit invalidated these older Phase 2 contact metrics as proof of real wall reaction. Keep them for historical controller diagnosis, but do not cite them as completed contact-assembly success until a new trace is regenerated after the wall-reaction smoke passes.

The first learned-policy contact smokes are also complete:

- All-trace BC reset eval: `success_step=null`, `best_strict_miss_score=21.0692`
- Best-window staged BC handoff eval: `success_step=null`, `handoff_miss=0.0319`, `best_after_bc=0.1865`
- Near-contact residual-current staged BC eval: `success_step=null`, `near_contact_fraction=0.0175`, `best_after_bc=0.3157`, `final_miss=45.5874`

Interpretation: the BC dataset/checkpoint/evaluation path works, but the current one-step MLP BC policies do not stabilize final contact after handoff. The next learned-policy step should change the data/control formulation, not run another one-step BC variant on the same trace archive. See [experiments/2026-05-18_phase2_contact_bc_smoke.md](experiments/2026-05-18_phase2_contact_bc_smoke.md) and [docs/phase2_il_contact_policy_plan.md](docs/phase2_il_contact_policy_plan.md).

The latest local demonstration audit shows why the first BC policy was weak:

- Mainline `JointPos` traces audited: `18`
- Near-contact steps: `3227`
- Strict/target gate passing steps: `0`

Interpretation: the archive is useful for learning a near-contact stabilization prior, but it is not yet a successful insertion-demonstration dataset. A larger residual-current near-contact dataset with `3187` samples has now been trained and evaluated; it still does not stabilize the handoff.

Offline audit of the existing BC eval traces confirms the same issue:

- All-trace BC: `near_contact_fraction=0.0000`
- Staged best-window BC: `near_contact_fraction=0.0125`, `longest_near_contact_streak=5`, `final_vs_handoff_miss_delta=+8.3880`
- Staged near-contact residual-current BC: `near_contact_fraction=0.0175`, `longest_near_contact_streak=6`, `final_vs_handoff_miss_delta=+45.5555`

The first `current-joint` hold baseline has now run:

- `success_step=null`
- `near_contact_fraction=0.0000`
- `longest_near_contact_streak=0`
- `best_delta_vs_handoff=+0.4117`
- `final_delta_vs_handoff=+58.8510`

Interpretation: passive joint holding is worse than the staged BC variants and does not preserve contact. The near-success handoff needs active contact maintenance, not just a static hold.

The follow-up `last-preload-action` static baseline attempt did not produce a robotics result. The Brev instance `a8i77l2b3` stalled in `BUILDING / NOT READY`, the run was aborted before Isaac runtime bootstrap, and cleanup independently confirmed no visible instances afterward.

A deterministic post-handoff baseline has now run on the official AWS Isaac Launchable:

```bash
scripts/run_launchable_phase2_preload_direction.sh
```

It uses `--controller preload-direction`, which follows the final scripted joint-space direction with a small bounded stabilizing anchor. The Launchable runtime issue is fixed enough to run Isaac Lab headless: the 10-step smoke passes, and the four-case built-in/RCA diagnostic matrix passes. The first formal 400-step eval replayed the historical `2026-05-17T23-32-18Z` action trace, but that old joint-position trace did not reproduce its original near-success handoff under Isaac Lab 2.3:

- Run `2026-05-24T16-44-26Z_preload-direction`
  - `success_step=null`
  - source handoff at step `1543`: `lateral=0.0052`, `rot=0.1812`, `contact=0.5298`
  - `handoff_lateral=0.2508`
  - `final_lateral=0.1303`
  - `final_rot=2.5794`
  - `best_strict_miss_score=34.9912`
  - `near_contact_fraction=0.0000`

Interpretation: the official Launchable is now a viable short-run Isaac Lab path, but historical joint-position traces are not portable enough across the old runtime and Isaac Lab 2.3. Later fresh-trace Launchable runs showed that the scripted handoff generator still fails before post-handoff evaluation: first with the old full-quaternion objective, then with the axis-aware objective below.

Current mainline response:

- success / handoff `rot` is now the calibrated sign-invariant cylinder-axis error, not full quaternion distance;
- `scripts/scripted_agent.py` has `--orientation-target-mode axis-align-current`, which aligns the insertion axis while preserving the current irrelevant twist about the cylindrical peg;
- `scripts/scripted_agent.py` also has `--rotate-xy-retention` and `--descend-xy-retention`, which pause staged rotation/descent and recover XY if the latched approach state has drifted laterally;
- `scripts/run_launchable_phase2_fresh_preload_direction.sh` uses the axis-aware target plus both XY-retention gates by default.

The axis-aware Launchable validation ran on `2026-05-24` using `isaac-launchable-837c5c` / `e9v2t2tsw` on AWS `g6e.4xlarge` L40S. The 10-step smoke passed. The guarded fresh-preload run failed closed before post-handoff eval: selected handoff step `7`, `lateral=0.0082`, `axial=0.6031`, `rot=0.9302`, `strict_miss_score=63.6295`. A no-rotate-before-descend diagnostic improved individual depth/rotation minima (`best_axial=0.0611`, `best_rot=0.1868`) but lost XY badly (`final_lateral=0.4124`, worst drift near `1m`). Diagnostics are in `artifacts/launchable_logs/rca-launchable-diagnostics-e9v2t2tsw.tar.gz`; the instance was deleted and `brev ls` confirmed no remaining instances.

The XY-retention path was then remote-validated on `isaac-launchable-1e19c4` / `1cozht94s`. Smoke passed, but the guarded run still failed closed: selected handoff step `8`, `lateral=0.0065`, `axial=0.6025`, `rot=0.9335`, `strict_miss_score=63.4364`. Recovery gates triggered for most of the rollout (`rotate_xy_recovery_step_count=1767`, max lateral about `1.00m`; `descend_xy_recovery_step_count=122`), which proves the blocker is not missing recovery-state detection; the joint-IK branch still walks away under the current scripted handoff family. Two live-patched joint-step scaling diagnostics (`global` and `after-xy-global`) also failed before a useful handoff and were stopped early. Diagnostics are in `artifacts/launchable_logs/rca-launchable-diagnostics-1cozht94s.tar.gz` and `artifacts/launchable_logs/rca-host-diagnostics-1cozht94s.tar.gz`; the instance was deleted, SSH lookup failed afterward, and the Brev UI showed an empty environment list.

Historical metrics above still report the metric used at the time of those runs. They are not current proof of physical contact. Do not spend another paid run sweeping the current scripted handoff family. The next useful work is contact-physics validation first, then a new controller/policy formulation only after the validated task exists.

The Abs IK branch has now been smoke-tested on AWS Launchable (`isaac-launchable-4a2c79` / `ij912di64`). It is materially different from the failed joint-position / standalone JointIK route because it uses Isaac Lab's native absolute-pose IK action term. Smoke passed, but the scripted-only probe failed closed: selected handoff step `319`, `lateral=0.1112`, `axial=0.0171`, `rot=0.6220`, `contact=4.9495`, `strict_miss_score=15.0390`. The compact `probe_summary.json` shows depth/contact are ready (`z_ready_step_count=285`, `contact_ready_step_count=320`), but `xy_ready_step_count=0` and `rot_ready_step_count=0`; the run also stayed in `reach` phase for all 320 steps, with best lateral at the final step. Artifacts are in `artifacts/launchable_logs/rca-absik-probe-results-ij912di64.tar.gz`. Follow-up trace review found that the native 7D Abs IK path was writing world-frame absolute pose targets into Isaac Lab's root-frame action term. `scripts/scripted_agent.py` now defaults 7D MDP Abs IK to `--mdp-abs-action-frame root`, and `scripts/run_launchable_phase2_absik_handoff_probe.sh` explicitly uses that root-frame path with a 1200-step window.

The root-frame Abs IK probe was then run on AWS Launchable (`isaac-launchable-fdfaba` / `ez3iyhmlw`) with the latest bundle `artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T12-29-24Z.tar.gz`. Smoke passed, but the 1200-step root-frame probe also failed closed: selected handoff step `330`, `lateral=0.1110`, `axial=0.0172`, `rot=0.6225`, `contact=4.9089`, `strict_miss_score=15.0255`; final rollout metrics were `final_lateral=0.0578`, `final_axial=0.0286`, `final_rot=1.5049`, and `success_step=null`. The root-frame fix is therefore real but insufficient: the current native Abs IK scripted command still never reaches XY or rotation readiness. Artifacts are in `artifacts/launchable_logs/rca-root-absik-probe-results-ez3iyhmlw.tar.gz`; host diagnostics are in `artifacts/launchable_logs/rca-host-diagnostics-ez3iyhmlw.tar.gz`.

The same root-frame Abs IK probe was then run with `RCA_LAUNCHABLE_MDP_ABS_ORIENTATION_COMMAND_MODE=current` on `isaac-launchable-18d403` / `v8g5gmij4`, keeping the native 7D action interface but commanding the measured current quaternion to isolate position behavior. It also failed closed: selected handoff step `325`, `lateral=0.1111`, `axial=0.0172`, `rot=0.6251`, `strict_miss_score=15.0579`, `xy_ready_step_count=0`, `best_lateral=0.0578@638`, `final_lateral=0.0578`, `success_step=null`. This rules out full-pose orientation tracking as the main reason XY does not converge. Artifacts are in `artifacts/launchable_logs/rca-absik-current-probe-results-v8g5gmij4.tar.gz`; host diagnostics are in `artifacts/launchable_logs/rca-host-diagnostics-v8g5gmij4.tar.gz`.

After that result, `scripts/analyze_absik_probe_trace.py` was added and run on both root-frame artifacts. It shows the same fixed point in both traces: the inferred `abs_pos_step` is `0.0300m`, the tail-window `command_to_post_action_xy` remains about `0.0315m`, the tail `target_to_command_y` remains about `-0.027m`, and `post_action_step_delta_xy` is effectively zero. That means the waypoint command formulation is saturating/stalling before the native IK target reaches the socket XY target. `scripts/run_launchable_phase2_absik_handoff_probe.sh` now writes `tracking_analysis.json` and exposes `RCA_LAUNCHABLE_ABS_CONTROL_MODE`. `scripts/scripted_agent.py` also traces the seven Franka arm joint positions, velocities, and joint-limit margins for native MDP Abs IK rollouts.

The target-command Abs IK diagnostic then ran on AWS `g6e.4xlarge` L40S via a plain Brev VM (`rca-absik-target-vm` / `6siwq7a2t`) because the Launchable CLI path still returned `lifecycle script is empty`. The VM manually cloned `isaac-sim/isaac-launchable`, brought up the official compose stack, passed the headless smoke, and ran `RCA_LAUNCHABLE_ABS_CONTROL_MODE=target` for 500 steps. It failed closed: selected handoff step `23`, `lateral=0.1067`, `axial=0.0110`, `rot=0.7833`, `strict_miss_score=16.2003`; final metrics were `final_lateral=0.0556`, `final_axial=0.0277`, `final_rot=1.5167`, `xy_ready_step_count=0`, `rot_ready_step_count=0`, `success_step=null`. `tracking_analysis.json` shows `target_to_command_xy=0.0`, but tail `command_to_post_action_xy≈0.0556m` and `post_action_step_delta_xy≈0`, so the command reaches the native IK target but the action-frame tip is physically/controller-stalled about 5.6cm away in XY. The trace now identifies the limiting joint: `panda_joint4` hit global minimum margin `-0.0002255` at step `103`, stayed within `1e-4` for all 500 samples, and was the tail limiting joint for all 50 tail samples. The next focused Abs IK diagnostic is an initial-posture / IK-branch test using `RCA_LAUNCHABLE_INITIAL_JOINT_POS=panda_joint4=-2.6`; do not rerun the previous target mode unchanged. Artifacts are in `artifacts/launchable_logs/rca-absik-target-probe-results-6siwq7a2t.tar.gz`; host diagnostics are in `artifacts/launchable_logs/rca-host-diagnostics-6siwq7a2t.tar.gz`. The instance was deleted and `brev ls instances --json --all` returned `{"workspaces": null}`.

That initial-posture diagnostic then ran on a new plain AWS Brev VM (`rca-absik-j4init-vm` / `v0w2i1mp2`) with bundle `artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T16-49-17Z.tar.gz`. Smoke passed, and the run used `RCA_LAUNCHABLE_ABS_CONTROL_MODE=target` plus `RCA_LAUNCHABLE_INITIAL_JOINT_POS=panda_joint4=-2.6` for 500 steps. It failed closed and was worse: selected handoff step `15`, `lateral=0.1334`, `axial=0.0350`, `rot=1.2837`, `strict_miss_score=23.8804`; final metrics were `final_lateral=0.1185`, `final_axial=0.0230`, `final_rot=1.4629`, `xy_ready_step_count=0`, `rot_ready_step_count=0`, `success_step=null`. The pre-step trace shows `panda_joint6` starts at its upper limit (`margin=0.0`), and the post-step trace shows `panda_joint4` immediately returns to the lower-limit plateau (`min margin=3.34e-6` at step `0`; tail limiting joint `panda_joint4` for all 50 tail samples). So this is not fixed by a one-joint initial elbow override; the target pose/native IK action drives the arm back into the same limiting posture. Artifacts are in `artifacts/launchable_logs/rca-absik-j4init-probe-results-v0w2i1mp2.tar.gz`; host diagnostics are in `artifacts/launchable_logs/rca-host-diagnostics-v0w2i1mp2.tar.gz`. The instance was deleted and `brev ls instances --json --all` returned `{"workspaces": null}`.

The guide-wall collision diagnostic then ran on the same AWS VM path (`rca-absik-nowall-vm` / `11ieede24`). The first run used `RCA_LAUNCHABLE_DISABLE_SOCKET_WALL_COLLISIONS=1`; after the trace showed unchanged contact forces, the diagnostic flag was strengthened to both disable collision properties and park all four guide-wall prims far away. The second run used bundle `artifacts/launchable/robot-contact-assembly-launchable-2026-05-25T18-20-21Z.tar.gz`, passed smoke, and still failed closed: selected handoff step `337`, `lateral=0.0957`, `axial=0.0086`, `rot=0.5281`, `strict_miss_score=12.5491`; final metrics were `final_lateral=0.0825`, `final_axial=0.0255`, `final_rot=0.7460`, `best_lateral=0.0704@129`, `xy_ready_step_count=0`, `rot_ready_step_count=0`, `success_step=null`. This is worse than the full target run's `5.6cm` tail residual, so guide-wall collision is not the main XY blocker. The persistent contact-force readings come from `ContactSensor.data.net_forces_w` on the peg, not a wall-only force channel, so do not use the current contact-force magnitude as proof of socket-wall blockage. Artifacts are in `artifacts/launchable_logs/rca-absik-nowall-parked-probe-results-11ieede24.tar.gz`. Cleanup was requested by both name and id; later `brev ls instances --json --all` returned `{"workspaces": null}`.

The target-offset Abs IK diagnostic then ran on a plain AWS Brev VM (`rca-absik-offset-vm` / `v2319sjd7`) with bundle `artifacts/launchable/robot-contact-assembly-launchable-target-offset-matrix-2026-05-25.tar.gz`. Smoke passed and the three 350-step cases all failed closed. Baseline remained best on true socket XY (`final_lateral=0.0556`, `tail command_to_post_action_xy≈0.0556`). `target_y_neg_04` changed the fixed point but worsened true XY (`final_lateral=0.0710`, true-tail `unbiased_target_action_to_post_action_xy≈0.0710`), and `target_y_pos_04` improved biased-target tracking while worsening true socket XY (`final_lateral=0.0778`, true-tail `≈0.0774`). All cases still had `xy_ready_step_count=0`, `rot_ready_step_count=0`, `success_step=null`, and tail limiting joint counts of `{panda_joint4: 50}`. Artifacts are in `artifacts/launchable_logs/rca-absik-target-offset-matrix-results-v2319sjd7.tar.gz`; host diagnostics are in `artifacts/launchable_logs/rca-host-diagnostics-v2319sjd7.txt`.

Interpretation: a simple world-frame target bias is not the fix. The follow-up IK solver-method matrix then ran on `rca-absik-ikmethod-vm` / `h9xqkqowr` using `artifacts/launchable/robot-contact-assembly-launchable-ik-method-matrix-2026-05-25.tar.gz`. Smoke passed, and all four 350-step solver cases failed closed. `dls` reproduced the baseline (`final_lateral=0.0556`, tail `command_to_post_action_xy≈0.0556`, tail limiting `{panda_joint4: 50}`). `pinv` and `svd` were effectively identical and only marginally different (`final_lateral=0.0554`, tail `≈0.0554`, same `panda_joint4` limit). `trans` improved rotation but was much worse on true XY (`final_lateral=0.1386`, tail `≈0.1386`, same limiting joint). Artifacts are in `artifacts/launchable_logs/rca-absik-ik-method-matrix-results-h9xqkqowr.tar.gz`; host diagnostics are in `artifacts/launchable_logs/rca-host-diagnostics-h9xqkqowr.txt`.

The native Abs IK solver-method sweep is therefore closed. The full-arm reset/posture matrix then ran on `rca-absik-posture-vm` / `5sjedqlea` using `artifacts/launchable/robot-contact-assembly-launchable-full-arm-posture-matrix-2026-05-25.tar.gz`. Smoke passed, and all five 350-step posture cases failed closed. `baseline` and `ready_mid` were identical and remained the best true socket XY fixed point (`final_lateral=0.0556`, tail residual `≈0.0556`, tail limiting `{panda_joint4: 50}`). `elbow_open` worsened to `final_lateral=0.2480` with tail limiting split across `panda_joint4` and `panda_joint7`; `yaw_pos` avoided negative joint-limit margin but still worsened true XY to `final_lateral=0.0818`; `yaw_neg` was unusable (`final_lateral=0.3091`, `final_axial=0.6677`). Artifacts are in `artifacts/launchable_logs/rca-absik-full-arm-posture-matrix-results-5sjedqlea.tar.gz`; host diagnostics are in `artifacts/launchable_logs/rca-host-diagnostics-5sjedqlea.txt`.

The full-arm reset/posture search is therefore also closed for these coarse candidates. Do not spend another paid run on unchanged native Abs IK target, target-offset, no-wall, single-joint-init, solver-method, or coarse initial-posture variants. The next useful implementation should be a local controller change with explicit joint-limit/nullspace behavior, or a non-native controller/action formulation.

That controller-side follow-up is now wired locally and has been validated once on AWS. `scripts/scripted_agent.py` has a default-off standalone JointPos IK nullspace bias (`--joint-limit-nullspace-gain`, activation margin, step, and damping) that projects joint-limit centering through the IK Jacobian nullspace before the existing joint target clamps. The AWS `g6e.xlarge` L40S plain Brev VM (`rca-jointpos-nullspace-vm` / `t28in7wiu`) passed the 10-step headless smoke, then ran the JointPos nullspace probe wrapper with 900 scripted steps:

```bash
scripts/run_launchable_phase2_jointpos_nullspace_probe.sh
```

The probe failed closed: selected handoff step `10`, `lateral=0.00898`, `axial=0.6344`, `rot=0.9471`, `strict_miss_score=67.0077`; final metrics were `final_lateral=0.0254`, `final_axial=0.8910`, `final_rot=1.3058`, `success_step=null`. Crucially, the nullspace correction never activated (`max_joint_limit_nullspace_delta_norm=0.0`) because the minimum joint-limit margin stayed at `0.3569`, outside the configured `0.25` activation margin. This means the unchanged JointPos nullspace gain matrix should not be run as the next paid step. The latest evidence points back to phase/target/action formulation: the run stayed in `align`, never reached depth or rotation readiness, and worsened axial tracking instead of testing a meaningful joint-limit escape.

Artifacts are in:

```text
artifacts/launchable_logs/rca-jointpos-nullspace-probe-results-t28in7wiu.tar.gz
artifacts/launchable_logs/rca-host-diagnostics-t28in7wiu.txt
```

The instance was deleted, and `brev ls instances --json --all` returned `{"workspaces": null}`.

The next local-first candidate was then implemented and paid-validated: `--rotate-descent-mode approach` for staged `rotate-before-descend`. The failed JointPos trace showed that, after XY alignment, the controller held the target Z near the high starting pose (`~0.824m`) while waiting for rotation readiness, even though the approach target was `~0.240m`; rotation never became ready, so descent never began. The new mode keeps the original default (`hold`) but allows a diagnostic run to rotate while commanding the approach-height pose. The wrapper isolates this phase change by setting nullspace gain to zero and enabling XY retention:

```bash
scripts/run_launchable_phase2_jointpos_rotate_descend_probe.sh
```

The AWS `g6e.xlarge` L40S plain Brev VM (`rca-jointpos-rotatedesc-vm` / `r2dvf19yi`) passed the 10-step smoke, then failed closed in both rotate-descend diagnostics. With XY retention enabled, the selected handoff was step `10`, phase `rotate-descend`, `lateral=0.00889`, `axial=0.6345`, `rot=0.9463`, `strict_miss_score=66.9987`; the final state was `lateral=0.1680`, `axial=0.8438`, `rot=1.4707`, and the rollout spent `877/900` steps in `rotate-xy-recover`. With XY retention disabled, rotate-descend executed continuously for `495/500` steps and moved somewhat farther down, but still failed closed: selected handoff step `11`, `lateral=0.00814`, `axial=0.6343`, `rot=0.9517`, `strict_miss_score=66.9568`; final `lateral=0.1328`, `axial=0.7083`, `rot=1.5511`. This closes the JointPos rotate-descend route in its current form.

The remote results were packaged on the VM as `/home/ubuntu/rca-jointpos-rotate-descend-results-r2dvf19yi.tar.gz` and `/home/ubuntu/rca-host-diagnostics-r2dvf19yi.txt`, but they were not pulled locally because the Brev CLI auth expired before copy/delete. Brev later reported credits exhausted and auto-stopped the environment. Do not add credits just to recover these artifacts, and do not open another paid Brev/AWS GPU run without an explicit new budget and a manual deletion path.

The local probe archive index is now generated by `scripts/summarize_launchable_probe_archives.py` and saved at `artifacts/analysis/launchable_probe_archive_summary_2026-05-26.md` / `.json`. It scans the downloaded Launchable/Brev tarballs; the current index found 20 probe summaries across 23 archives, all `fail_closed`. Use that table as the canonical local comparison before deciding on any future remote run.

The next local-first controller branch is now wired but not GPU-validated:

- `scripts/scripted_agent.py --reachable-approach`
- `scripts/select_reachable_approach_candidates.py`
- `scripts/run_launchable_phase2_jointpos_reachable_approach_probe.sh`

This branch starts from an outside XY waypoint and shrinks toward the socket only when the current offset target is reached with enough previous-step joint-limit margin. The offline selector found the best old candidates around `7.7cm` lateral with `0.15-0.17rad` joint margin, supporting an initial `0.060m` approach radius. Treat this as the only new short-probe candidate after explicit budget approval, not as a reason to reopen paid cloud runs now.

Prepared local bundle:

```text
artifacts/launchable/robot-contact-assembly-launchable-reachable-approach-2026-05-27.tar.gz
```

Latest bundle with this rotate-descend wiring:

```text
artifacts/launchable/robot-contact-assembly-launchable-jointpos-rotate-descend-2026-05-26.tar.gz
```

A temporal residual-current BC dataset is also prepared but not yet run:

```bash
scripts/run_phase2_contact_bc_temporal_residual_current_smoke_gate.sh
```

It uses the same `3187` near-contact samples as the latest residual-current BC run, but expands the observation from `37D` to `77D` by adding two previous-step snapshots of action, pose error, contact force, and insertion metrics.

## V1 scope

The first version is intentionally narrow:

- Task: `peg-in-hole`
- Robot: Isaac-provided arm
- Control: end-effector delta pose
- Training: single task, single workstation, single policy
- Output: reproducible baseline with scripted, RL, and evaluation flows

## Working split

Local machine:

- Cursor / Codex
- planning docs and configs
- lightweight control tools
- artifact archive on the external SSD

## Local storage policy

Keep all local project state on the external SSD under:

- `/Volumes/Extreme Pro/Projects/robot-contact-assembly`

This repository is intended to be the local source of truth for:

- source code
- pulled checkpoints
- pulled evaluation JSON and logs
- pulled videos
- experiment notes

Do not pull artifacts into `~/Downloads`, `~/Desktop`, or other paths on the system disk.

Remote Brev GPU VM:

- Isaac Sim / Isaac Lab runtime
- ROS 2 processes tied to the sim
- training jobs
- rendered videos and checkpoints before sync back

See [architecture.md](docs/architecture.md) and [task_breakdown.md](docs/task_breakdown.md).
For the shortest GPU-session workflow, use [phase1_gpu_session_runbook.md](docs/phase1_gpu_session_runbook.md).
Before creating any paid GPU instance, use [gpu_selection_policy.md](docs/gpu_selection_policy.md) to compare live Brev prices and choose the best-value instance for the specific job. The local Brev create wrappers now refuse paid instance creation unless `RCA_ALLOW_PAID_BREV_CREATE=1` is set after an explicit budget/deletion check, and they start `scripts/brev_paid_run_watchdog.sh` before `brev create` so every paid CLI run has a local TTL/cost-boundary ledger and cleanup monitor. For UI-created Launchables, run `scripts/start_brev_ui_launchable_watchdog.sh` before clicking Create, or start `scripts/brev_paid_run_watchdog.sh` against the generated instance name/id immediately after creation.

Every paid path now also has to pass:

```bash
RCA_BREV_LOGIN_EMAIL=<email> ./scripts/refresh_brev_login.sh

RCA_ALLOW_PAID_BREV_CREATE=1 \
RCA_BREV_CREDITS_VERIFIED=1 \
RCA_PAID_BUDGET_EUR=<explicit-budget> \
RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
RCA_PAID_MAX_MINUTES=<ttl-minutes> \
RCA_PAID_RUN_PURPOSE=contact_physics_smoke \
  ./scripts/paid_compute_preflight.sh
```

`scripts/refresh_brev_login.sh` refreshes Brev/NVIDIA CLI auth and then runs only the read-only `brev ls instances --json --all` verification. It does not create paid resources.

`scripts/brev_paid_safety_status.sh` is the read-only quick safety snapshot:
it checks Brev backend health, the active org, `brev ls instances --json --all`,
watchdog processes, watchdog ledgers, and the lifecycle hold file. Use it before
and after any paid/Brev work; when no paid job is intentionally running it must
show `visible_instances=0`.

Use `RCA_PAID_RUN_PURPOSE=contact_physics_smoke` only for the short Isaac contact-physics smoke before the Phase 2 gate passes. All other paid work defaults to `post_contact_gate` and is blocked until `python3 scripts/check_phase2_contact_gate.py` reports PASS. The preflight also fails closed when Brev CLI auth is expired, any active instance is visible, the manual credit-balance marker `RCA_BREV_CREDITS_VERIFIED=1` is missing, or the estimated max cost (`RCA_PAID_ESTIMATED_EUR_PER_HOUR * RCA_PAID_MAX_MINUTES / 60`) exceeds `RCA_PAID_BUDGET_EUR`; there is no supported phase-gate skip or nonempty-org override.

After the 2026-06-20 repeated AWS Launchable lifecycle failures, an active hold
file at `docs/brev_launchable_lifecycle_hold.md` also blocks paid creation by
default. A retry requires `RCA_ACK_BREV_LIFECYCLE_RISK=1` in addition to the
normal budget/TTL/auth/empty-org checks, and should only be used after Brev
cleanup is confirmed and the lifecycle risk is deliberately accepted.
Use `scripts/create_brev_lifecycle_incident_bundle.sh` to package support
evidence, and `scripts/check_brev_lifecycle_hold_clearance.sh` to confirm
`visible_instances=0` plus fail-closed preflight behavior before any human
review of the hold.
If a single contact-smoke retry is later deliberately considered, run
`./scripts/check_launchable_retry_readiness.sh` first. It is read-only and
stays blocked unless the lifecycle risk acknowledgement, budget, hourly
estimate, TTL, empty-org state, and bundle readiness all line up.

For the next Phase 2 contact-shell gate, use `scripts/run_guarded_phase2_gate.sh` so price capture, runtime install, artifact pullback, deletion, and final empty-org checks happen in one controlled flow.
After the repeated Brev create/delete lifecycle stalls, run a probe before any Isaac workload. The conservative default remains `scripts/run_brev_probe_only_gate.sh`: it creates the selected instance, waits for Brev list readiness, probes `nvidia-smi` / disk over SSH, and deletes it without installing Isaac or running evaluation. The first `2026-05-21` probe-only run failed before SSH on `g2-standard-4:nvidia-l4:1`; the explicit Nebius L40S probe also failed before SSH and required repeated cleanup. Brev support later confirmed there were no hidden billable resources and suggested the issue may involve the deployment / port workflow rather than a hidden instance. A newer direct-SSH probe, `scripts/run_brev_probe_direct_ssh_gate.sh`, then failed even earlier on `2026-05-24`: Brev's `CreateWorkspace` API returned `unexpected EOF` before SSH. Do not run full Isaac jobs through that Brev GCP CLI path until support confirms the create API issue is fixed. The official AWS Isaac Launchable path in `docs/aws_isaac_launchable_runbook.md` successfully brought up an L40S Launchable, passed the marker-checked headless smoke and diagnostic matrix after Isaac Lab 2.3 compatibility fixes, and ran the `preload-direction` eval. Use it only for short, explicit paid runs and delete the instance immediately afterward.

## Repository layout

- `configs/`: task and experiment configuration
- `docs/`: project and system design notes
- `experiments/`: run logs and experiment notes
- `scripts/`: local-to-remote workflow helpers
- `src/robot_contact_assembly/`: planning-side specs and lightweight local utilities
- `source/robot_contact_assembly_tasks/`: Isaac Lab external task package for runtime registration

## Current milestone

Phase 1 is closed. The current milestone is Phase 2 contact-physics validation:

1. Keep the physical peg/socket/contact task reproducible.
2. Treat the older shallow "true-contact" success as diagnostic history until regenerated after the wall-reaction smoke passes.
3. Stop adding scripted retention heuristics after the force-aware near miss.
4. Stop one-step BC retries on the current trace archive after the all-trace, best-window, and residual-current failures.
5. Keep all reported metrics explicit about whether they use the shallow gate or strict gate.
6. Move the next technical step to the contact-physics smoke gate before another paid controller/policy run; if it passes, regenerate a minimal scripted trace under the validated task before revisiting data/control/action-semantics reformulation.

Before any remote or paid step, run the local no-Isaac quality gate:

```bash
./scripts/run_local_quality_checks.sh
```

This also runs project structure checks through `scripts/check_project_structure.py`, contact-physics wiring checks through `scripts/check_contact_physics_wiring.py`, policy checks through `scripts/check_project_policy_compliance.py`, and offline gate behavior tests through `scripts/test_local_gates.py`; it does not call Brev or Isaac. It runs without writing Python bytecode and fails if generated cache or package metadata is present.

Then run the Phase 2 contact gate:

```bash
python3 scripts/check_phase2_contact_gate.py
```

If it reports `BLOCKED`, do not run controller sweeps, BC, RL, or broad paid GPU jobs. The only next paid action is a short Isaac runtime smoke using `./scripts/run_launchable_contact_physics_smoke.sh`, followed by log pullback, immediate instance deletion, and an empty-instance confirmation.

The archived smoke log must contain the marker set enforced by `scripts/check_phase2_contact_gate.py`: `phase free-space-settle: end`, `attach`, `free-space`, `phase local-guide-reanchor: end`, `local-guide reanchored`, `free-space-reanchored`, `phase press-hold: end`, `press-force`, `press-tracking`, `press-blocked`, `press-no-clip`, `phase retreat-hold: end`, `release`, `joint-integrity`, `phase-sequence: PASS`, and the wrapper completion marker. Its source evidence must include the current runtime `source_payload_sha256`; stale PASS logs from older runtime code do not unlock downstream work, but documentation-only commits should not force another paid smoke.

For a read-only current-state snapshot:

```bash
python3 scripts/project_status_report.py
```

When ready for the one allowed paid smoke, use the guarded preparation command:

```bash
RCA_PAID_BUDGET_EUR=<explicit-budget> \
RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour> \
RCA_BREV_CREDITS_VERIFIED=1 \
  ./scripts/prepare_contact_smoke_run.sh
```

It runs the local quality gate and paid preflight first, then creates a fresh contact-smoke Launchable bundle with the source manifest and prints the exact tarball path to upload. It does not create a Launchable by itself. Launchable bundles exclude generated caches plus local tool configuration such as `.claude/`; `source_payload_sha256` fingerprints the `runtime-v1` source scope that affects the contact smoke, not documentation-only bundle content.

After the remote smoke finishes, pull and validate the only allowed pre-gate artifact with:

```bash
./scripts/pull_contact_smoke_log.sh <launchable-env-name> /workspace/robot-contact-assembly
```

Low-level helpers that operate on an already-running Brev environment now route through `scripts/remote_operation_preflight.sh`. While the contact gate is blocked, they refuse normal post-contact remote work; only `RCA_REMOTE_OPERATION_PURPOSE=contact_physics_smoke` is allowed. Remote preflight completion is not externally skippable. For the one allowed pre-gate pullback, use `scripts/pull_contact_smoke_log.sh`; it pulls only `artifacts/launchable_logs/contact_physics_smoke.log` and immediately runs `scripts/archive_contact_smoke_log.sh`.

Launchable workload scripts now also have a remote-side guard through `scripts/launchable_post_contact_gate.sh`. Inside the paid runtime, every non-contact-smoke Launchable evaluation/matrix/probe script must see a local `contact_physics_smoke.log` that passes `scripts/check_phase2_contact_gate.py` for the current runtime source payload before it runs.

The policy check also statically scans for direct `ssh`, `rsync`, `scp`, `sftp`, and `brev exec/copy/port-forward/shell/open` usage so new remote helpers cannot bypass the preflight silently.

## Current Runtime Scaffold

The current runnable Isaac Lab shell is still intentionally simple, but it now includes explicit contact geometry:

- Robot: Franka Panda
- Control: relative differential IK
- Task scope: physical peg rigid body + fixed guide socket walls
- Task IDs:
  - `RCA-PegInHole-Franka-IK-Rel-v0`
  - `RCA-PegInHole-Franka-IK-Rel-Play-v0`
  - `RCA-PegInHole-Franka-IK-Rel-Polish-v0`
  - `RCA-PegInHole-Franka-IK-Rel-Contact-v0`
  - `RCA-PegInHole-Franka-IK-Rel-Contact-Play-v0`
  - `RCA-PegInHole-Franka-IK-Abs-Contact-v0`
  - `RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0`
  - `RCA-PegInHole-Franka-JointPos-Contact-v0`
  - `RCA-PegInHole-Franka-JointPos-Contact-Play-v0`

The policy observation contract is still kept Phase-1 compatible so the best proxy checkpoint can be evaluated zero-shot in the new contact shell before adding force terms to the actor.

The new `Contact` task IDs are the first force-aware training path. They preserve the same core pose observations as `v0`, but add:

- peg contact force vector in the socket frame
- peg contact force magnitude

The direct-contact training path now also uses a contact-specific baseline setup:

- lower relative-IK action scale
- tighter reset around the nominal start posture
- observation corruption disabled for the first direct-contact baseline
- a dedicated PPO runner with lower exploration noise and a smaller learning rate

Keep using `RCA-PegInHole-Franka-IK-Rel-v0` for transfer/regression. Use `RCA-PegInHole-Franka-IK-Rel-Contact-v0` for the first direct contact-training baseline.

## Current Limitation

The current task is no longer a pure proxy shell, but it is still not a final industrial socket model:

- the socket is a simple fixed guide built from collision walls, not a CAD-accurate round hole with chamfer
- the first zero-shot transfer eval from `phase1_fix6_formal/model_50.pt` failed with `success=0.000`, `final_lateral=0.5667`, `final_axial=0.4202`, and `final_rot=1.9165`
- force/contact sensing is present at the scene level, but the default policy observation width is still frozen for checkpoint compatibility

This is enough to turn the project back into a real contact problem without taking on grasping, CAD assets, or sim-to-real scope yet.

## First Contact-Shell Validation

The first contact-shell validation was run on `2026-04-19` against the upgraded peg + guide-wall scene.

- smoke suite: passed
- scripted baseline on the play task: unstable under contact, ending at `final_lateral=0.6042`, `final_axial=0.1477`, `final_rot=0.3168`, `success=0.000`
- zero-shot transfer from `phase1_fix6_formal/model_50.pt`: failed, ending at `final_lateral=0.5667`, `final_axial=0.4202`, `final_rot=1.9165`, `success=0.000`
- scripted viewport recording: timed out at `240s`, so the first contact-shell validation currently has logs and JSON metrics but no stable mp4 artifact

See [experiments/2026-04-19_phase2_contact_shell_validation.md](experiments/2026-04-19_phase2_contact_shell_validation.md) for the exact commands, artifact paths, and interpretation.

## First Force-Aware Contact Smoke

The first direct contact-training smoke run was also completed on `2026-04-19` using:

- task: `RCA-PegInHole-Franka-IK-Rel-Contact-v0`
- observations: `42` dims (`38` Phase-1-compatible pose terms + `4` contact-force terms)
- run: `phase2_contact_force_smoke`
- training budget: `64 envs`, `5` PPO iterations

What it proved:

- the new force-aware task boots and trains end-to-end on GPU
- the actor/critic resize cleanly to the `42`-dim observation contract
- the workflow now produces contact-task checkpoints and eval artifacts without additional infrastructure work

What it did **not** prove:

- the resulting `model_4.pt` is not yet useful
- short eval on the smoke checkpoint ended at `final_lateral=0.6005`, `final_axial=0.6296`, `final_rot=2.4156`, `success=0.000`

Interpretation:

- Phase 2 has crossed the tooling threshold from "contact shell exists" to "direct contact training path is alive"
- the next meaningful step is a longer direct contact-baseline run, not more proxy transfer experiments

## First Direct Contact Baseline

The first longer direct-contact PPO baseline was completed on `2026-04-26` after switching the remote runtime to a headless-only Brev path:

- instance type: `massedcompute_L40S`
- task: `RCA-PegInHole-Franka-IK-Rel-Contact-v0`
- run: `phase2_contact_baseline_v2`
- training budget: `64 envs`, `100` PPO iterations, seed `42`
- best saved checkpoint from the run: `model_99.pt`

Fixed-step eval on `model_99.pt` with `16` envs and `400` steps produced:

- `final_success_rate=0.000`
- `best_success_rate=0.000`
- `final_lateral=0.4725`
- `final_axial=0.4217`
- `final_rot=1.9343`

Interpretation:

- the direct contact-training path now works end-to-end on a fresh GPU instance
- reward increased during training, but `insertion_progress` and `insertion_success` stayed at zero
- the current contact task is therefore still not learning insertion; the next useful work is local task/reward diagnosis before spending more GPU time

See [experiments/2026-04-26_phase2_direct_contact_baseline.md](experiments/2026-04-26_phase2_direct_contact_baseline.md) for the exact commands, runtime workaround, artifacts, and next decision.

## Contact Frame Fix Validated

After the first direct-contact baseline, the main local diagnosis found a frame-consistency bug rather than a pure PPO/reward problem:

- the remote Isaac Lab develop / Isaac Sim 6 runtime uses `XYZW` quaternion ordering, while parts of the project still used legacy `WXYZ` constants and helper math
- the relative-IK action offset used only position, so the controller frame and physical peg-tip frame were not guaranteed to match
- scripted/live controllers were compensating for the old hand-frame target instead of commanding the socket frame directly

The code aligns the physical peg, IK action offset, and scripted controller around the same calibrated peg-tip frame. The cheap L4 scripted gate on 2026-05-15 validated the primary invariant:

- `best_action_tip_alignment=0.0`
- `final_action_tip_alignment=0.0`
- `final_success_rate=0.0`

The frame bug is fixed for the calibrated task convention. A 2026-05-24 AWS Launchable diagnostic showed that naively migrating the calibrated constants/helpers to WXYZ makes the gate worse; do not change that convention without a full remote re-calibration. The latest handoff change keeps that calibrated convention and changes the task/controller objective instead: cylindrical insertion now gates on sign-invariant peg/socket axis alignment, while the scripted controller can preserve twist with `--orientation-target-mode axis-align-current`.

See [experiments/2026-04-26_phase2_contact_frame_fix.md](experiments/2026-04-26_phase2_contact_frame_fix.md) for the diagnosis, local checks, and next GPU gate.

## Latest Phase 2 Scripted Gate Status

Pre-audit guarded L4 scripted gates were completed on `2026-05-17` against the then-current contact shell. After the 2026-06-11 contact-physics audit, treat these as historical controller diagnostics, not as proof of physical peg-wall insertion:

- Shallow contact success:
  - run `2026-05-17T19-47-06Z`
  - `success_step=1538`
  - gate: `xy<5mm`, `z<45mm`, `rot<0.20rad`, `contact>=0.5`
- Early contact-retention strict gate:
  - closest step missed strict rotation by `0.0042 rad`
  - lateral, axial, and contact were inside gate at that step
- XY-hold contact-retention strict gate:
  - closest step passed axial, rotation, and contact
  - missed lateral by about `1.07 mm`
- Force-aware contact-retention strict gate:
  - closest step passed axial and contact
  - missed lateral by about `0.20 mm` and rotation by `0.0012 rad`

Interpretation:

- The guarded Brev runtime, artifact pullback, and cleanup checks were useful.
- The older contact-force metric is not current proof of wall reaction.
- Strict success was not achieved, and the older near-seat labels must be regenerated under the validated dynamic-peg task before they can drive BC, RL, or reset-candidate work.
- Continuing to add scripted retention heuristics or one-step BC variants is low-value before the contact-physics smoke passes.

Current decision:

- Stop paid GPU runs on the scripted-controller branch.
- Do not preserve the older shallow success as a Phase 2 demonstration milestone until it is regenerated after the wall-reaction smoke passes.
- Preserve the strict-gate failures as diagnosis evidence.
- Move the next implementation step to contact-physics smoke validation, not IL/RL preparation, another one-off heuristic, or unchanged one-step BC run.
- Do not re-run `scripts/run_phase2_contact_handoff_hold_gate.sh` unchanged; the `current-joint` hold baseline has already failed.
- Use `scripts/run_phase2_contact_bc_temporal_residual_current_smoke_gate.sh` only after deciding that the next paid learned-policy run should test temporal context.

See [experiments/2026-05-14_phase2_guarded_gate_attempt.md](experiments/2026-05-14_phase2_guarded_gate_attempt.md) for the guarded-gate sequence and artifact paths. See [experiments/2026-05-17_phase2_near_success_diagnosis.md](experiments/2026-05-17_phase2_near_success_diagnosis.md) for the final scripted near-success diagnosis.

## First Contact Validation

This older remote validation sequence is retained for historical runtime context. The current first validation is `./scripts/run_launchable_contact_physics_smoke.sh`; do not run transfer eval, scripted gates, BC, or RL before that wall-reaction smoke passes.

Historical validation sequence:

1. Run the remote smoke suite:
   - `./scripts/run_remote_smoke_test.sh`
2. Run the zero-shot transfer eval from the best Phase 1 proxy checkpoint:
   - `./scripts/run_remote_contact_transfer_eval.sh`
3. Pull the resulting artifacts back to the local archive:
   - `./scripts/pull_artifacts.sh`

What those commands do:

- `run_remote_smoke_test.sh` now syncs the repo first, then runs compose health, env listing, zero-action rollout, random-action rollout, and scripted baseline sanity on the play task.
- `run_remote_contact_transfer_eval.sh` runs both fixed-step policy eval and an optional recorded video for the default transfer target:
  - run pattern: `.*phase1_fix6_formal.*`
  - checkpoint: `model_50.pt`
  - task: `RCA-PegInHole-Franka-IK-Rel-v0`
- the video stage now defaults to `RCA_VIDEO_BACKEND=viewport`
- the viewport path auto-injects the minimal rendering extensions with `--kit_args "--enable omni.replicator.core --enable omni.kit.material.library --enable omni.kit.viewport.rtx"` when no custom `--kit_args` are provided
- `RCA_VIDEO_BACKEND=camera` is still available for explicit sensor debugging, but it is not the stable path on the current Brev setup
- by default the wrapper keeps the eval artifacts even if the video step times out
- `run_remote_record_video.sh` now force-kills lingering recorder jobs after the grace period with `RCA_VIDEO_TIMEOUT_KILL_SECONDS` so failed probes do not leave orphaned Isaac processes behind

Useful overrides:

- use a different play-task smoke target:
  - `./scripts/run_remote_smoke_test.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Play-v0 5 10 120`
- evaluate a different checkpoint:
  - `./scripts/run_remote_contact_transfer_eval.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 32 400 42 '.*phase1_fix6_formal.*' model_50.pt 400`
- make the video step optional and cap its runtime:
  - `RCA_VIDEO_REQUIRED=0 RCA_VIDEO_TIMEOUT_SECONDS=60 ./scripts/run_remote_contact_transfer_eval.sh`
- shorten the hard-kill grace period when debugging stuck video jobs:
  - `RCA_VIDEO_TIMEOUT_SECONDS=60 RCA_VIDEO_TIMEOUT_KILL_SECONDS=10 ./scripts/run_remote_record_video.sh`
- force explicit camera-sensor recording for debugging:
  - `RCA_VIDEO_BACKEND=camera ./scripts/run_remote_contact_transfer_eval.sh`
- force the wrapper to fail when video recording fails:
  - `RCA_VIDEO_REQUIRED=1 ./scripts/run_remote_contact_transfer_eval.sh`

## Remote workflow

1. Bootstrap the Brev workspace:
   - `./scripts/bootstrap_brev_workspace.sh`
2. Sync the repo:
   - `./scripts/sync_to_brev.sh`
3. Clone or refresh Isaac Lab on the remote VM:
   - `./scripts/setup_remote_isaaclab.sh`
4. Mount the project and Isaac Lab into the running Isaac Sim container, then install the required Isaac Lab packages into the container's Python runtime:
   - `./scripts/install_remote_isaaclab_runtime.sh`
5. Run the first smoke test:
   - `./scripts/run_remote_smoke_test.sh`

## Day-1 commands

Once the runtime is bootstrapped, the shortest useful commands are:

- Inspect remote runtime health:
  - `./scripts/check_remote_runtime.sh`
- Full smoke suite for the contact shell:
  - `./scripts/run_remote_smoke_test.sh`
- Headless zero-action rollout:
  - `./scripts/run_remote_zero_agent.sh`
- Headless random-action rollout:
  - `./scripts/run_remote_random_agent.sh`
- Headless scripted baseline:
  - `./scripts/run_remote_scripted_baseline.sh`
- Fixed-seed scripted baseline sweep with per-seed JSON summaries:
  - `./scripts/run_remote_scripted_eval.sh`
- Same-instance scripted reachability sweep for controller tuning:
  - `./scripts/run_remote_scripted_reach_sweep.sh`
- PPO training wrapper for the custom peg-in-hole task package:
  - `./scripts/run_remote_train_ppo.sh`
- Short contact-baseline smoke run:
  - `./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-v0 64 5 42 phase2_contact_smoke`
- Short force-aware contact smoke run:
  - `./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Contact-v0 64 5 42 phase2_contact_force_smoke`
- First direct contact baseline:
  - `./scripts/run_remote_train_ppo.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Contact-v0 64 100 42 phase2_contact_baseline_v2`
- End-to-end polish cycle wrapper:
  - `./scripts/run_remote_polish_cycle.sh`
- Cold-start Brev reprovision + polish cycle:
  - `./scripts/recreate_brev_and_run_polish.sh`
- Fixed-step policy evaluation with JSON summary export:
  - `./scripts/run_remote_eval_policy.sh`
- Zero-shot Phase-1-to-contact transfer eval + video wrapper:
  - `./scripts/run_remote_contact_transfer_eval.sh`
- One-instance socket-pose sweep for the next Phase 2 contact gate:
  - `./scripts/run_phase2_workspace_socket_sweep_gate.sh`
- Summarize pulled socket-sweep JSON files:
  - `python3 scripts/summarize_socket_sweep_results.py --since 2026-05-17T00-00-00Z`
- Fixed-step checkpoint sweep over a matched run:
  - `./scripts/run_remote_eval_checkpoint_sweep.sh`
- One-shot policy video recording:
  - `./scripts/run_remote_record_video.sh`
- Capture a runtime manifest for reproducibility:
  - `./scripts/capture_remote_runtime_manifest.sh`
- Start the local live-app code port forward:
  - `bash ./scripts/start_live_code_port_forward.sh`
- Load the play environment into the currently running streamed Isaac Sim app:
  - `bash ./scripts/show_live_play_env.sh`
- Run the first scripted live baseline:
  - `bash ./scripts/run_live_scripted_baseline.sh`

Default target is `isaac-l40s`. Optional positional arguments are:

- `ENV_NAME`
- `REMOTE_ROOT`
- `REMOTE_COMPOSE_ROOT`
- `TASK_NAME`
- `NUM_ENVS`
- `STEPS`

Example:

- `./scripts/run_remote_random_agent.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Play-v0 1 20`
- `./scripts/run_remote_polish_cycle.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 50 42 phase1_polish '.*phase1_fix6_formal.*' model_50.pt 400 0`
- `./scripts/recreate_brev_and_run_polish.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 50 42 phase1_polish_v2 '.*phase1_fix6_formal.*' model_50.pt 400 0`
- `./scripts/run_remote_eval_checkpoint_sweep.sh isaac-l40s /home/ubuntu/projects/robot-contact-assembly /home/ubuntu/isaac-compose RCA-PegInHole-Franka-IK-Rel-Polish-v0 32 400 42 '.*phase1_polish.*' 'model_.*\.pt' 0`

After pulling artifacts, summarize a sweep locally with:

- `python3 scripts/summarize_eval_sweep.py --checkpoint-substring phase1_polish`

## Current remote runtime decision

The Brev host currently runs the streamed Isaac Sim stack via Docker. Because of that, the executable path for V1 is:

- Streaming stack: `isaac-sim` container for WebRTC / viewer services
- Task execution runtime: `/isaac-sim/python.sh` inside the `isaac-runner` container
- Isaac Lab repo: mounted at `/workspace/IsaacLab`
- Project repo: mounted from `/home/ubuntu/projects/robot-contact-assembly/repo/robot-contact-assembly`

This avoids relying on the Brev host's system Python, which is not the right runtime for Isaac Lab + Isaac Sim, and avoids running evaluation or training scripts inside the long-lived streaming container.

## Current validated state

Validated on `2026-03-29` for the original proxy-task runtime:

- remote `isaac-sim` container healthy
- env registry works
- `RCA-PegInHole-Franka-IK-Rel-Play-v0` launches in headless mode
- zero-action smoke passes
- random-action smoke passes

Current contact-task work uses a split runtime:

- `isaac-sim`: streaming / viewer service
- `isaac-runner`: smoke, eval, and training execution target

The RL stack is not yet treated as stable. Do not assume `rsl_rl` installation is reproducible until the runtime is pinned more tightly.

## Final Phase 1 status

Validated through the `2026-04-05` experiment series:

- A complete remote training/evaluation/artifact loop is in place for PPO baseline runs.
- The strongest base run was `phase1_fix6_formal`, which reached:
  - `lateral=0.0074`
  - `axial=0.0027`
  - `rot=0.7190`
  - `success=0.000`
- The strongest continuation run was `finetune_fix8_from_fix6`, which improved rotation while preserving near-socket alignment:
  - `lateral=0.0105`
  - `axial=0.0092`
  - `rot=0.6265`
  - `success=0.000`
- Three dedicated late-stage `Polish` variants (`v2`, `v3`, and scheduled curriculum) ran successfully but did not beat the continuation baseline.

Phase 1 therefore closes with a clear technical conclusion:

- the policy can reliably learn socket approach and near-insertion alignment
- the remaining gap is late-stage rotational convergence under the current proxy task design
- further reward retuning was stopped after the scheduled curriculum failed to beat `finetune_fix8_from_fix6`

For the concise CV-facing summary and interview framing, see [phase1_cv_summary.md](docs/phase1_cv_summary.md).

## What comes next

The proxy-to-contact migration is not complete until the dynamic-peg contact smoke passes on Isaac runtime. The next meaningful technical step is not another GPU burn on the same hand-coded polish controller.

The recommended next phase is:

- run and archive the contact-physics smoke gate
- regenerate one short scripted trace under the validated contact shell
- only then decide whether to generate demonstrations, train a learned final-contact policy, or use reset/initialization curricula
- evaluate against both the shallow gate and the strict gate only after the metric source is verified
- only reopen paid GPU runs when the next experiment has a single measurable pass/fail condition and cleanup watchdog

Before committing to a learned policy action space, run the one-at-a-time control-mode comparison in [phase2_control_mode_comparison_plan.md](docs/phase2_control_mode_comparison_plan.md):

- current `JointPos + standalone joint-IK` baseline
- native relative Cartesian IK action
- native absolute Cartesian IK action

The comparison should answer whether Cartesian end-effector control actually improves the final contact phase, or whether the blocker is policy learning rather than action-space expression.

The main next implementation track is documented in [phase2_il_contact_policy_plan.md](docs/phase2_il_contact_policy_plan.md). The local-first flow is:

- audit demonstration coverage with `scripts/analyze_contact_demo_coverage.py`
- extract contact-phase samples from existing scripted traces with `scripts/extract_contact_demo_dataset.py`
- train a small BC smoke policy with `scripts/train_contact_bc_policy.py`
- evaluate the BC checkpoint with `scripts/evaluate_contact_bc_policy.py`, including near-contact fraction and post-handoff degradation
- only then open GPU for a short learned-policy evaluation or additional demonstration collection

Prepared next learned-policy wrapper:

```bash
RCA_GATE_PROFILE=cheap scripts/run_phase2_contact_bc_near_contact_residual_current_smoke_gate.sh
```

## Phase-1 reproducibility additions

- `scripts/capture_remote_runtime_manifest.sh`
  - snapshots compose status, key package versions, registered envs, and git state into `experiments/runtime_manifests/`
- `scripts/run_remote_scripted_eval.sh`
  - runs the scripted peg-in-hole baseline over a fixed seed sweep and writes one JSON summary per seed under `/workspace/artifacts/evaluations/scripted/`
- `scripts/scripted_agent.py --seed --summary-json`
  - supports deterministic replay and machine-readable summaries for evaluation
