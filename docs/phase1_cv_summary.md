# Phase 1 CV Summary

## One-line project description

Built a custom Isaac Lab peg-in-hole proxy environment with scripted and PPO baselines, remote Brev GPU training/evaluation workflows, and reproducible artifact export for a contact-task precursor.

## Resume-ready bullets

- Built a custom `peg-in-hole` task package in Isaac Lab for Franka relative-IK control, with task registration, reward design, fixed-step evaluation, and remote artifact capture.
- Implemented end-to-end remote experiment tooling on Brev for PPO training, checkpoint evaluation, checkpoint sweeps, cold-start runtime recovery, and reproducible log/checkpoint pullback to an external SSD.
- Drove a proxy insertion policy from coarse approach to near-insertion alignment; best continuation run reached `lateral=0.0105`, `axial=0.0092`, and `rot=0.6265` in fixed-step evaluation, then used failed late-stage curriculum variants to show the limit of reward tuning under a non-contact task shell.

## Short README / portfolio summary

This project focuses on a narrow peg-in-hole precursor in Isaac Lab. Phase 1 intentionally used a proxy task with a fixed peg-tip offset and a commanded socket pose so the project could first close the remote training/evaluation/artifact loop. PPO learned reliable approach and near-socket alignment, and the strongest continuation run substantially reduced the remaining pose error, but true contact-grounded insertion was still out of scope for that phase. That outcome is still useful: it demonstrates environment design, reward iteration, experiment management, and failure analysis in a robotics ML workflow without overstating what the Phase 1 task actually was.

## Interview framing

- Why this scope: a narrow proxy precursor was a better first milestone than a broad multi-skill system because it forced the project to close the sim/training/eval loop before adding contact geometry.
- What worked: task packaging, remote runtime recovery, reproducible training/evaluation, and learning a stable near-insertion policy.
- What did not: late-stage orientation polishing did not generalize across multiple curriculum variants.
- What the failure means: the remaining problem is not gross reachability; it is that the proxy task stopped short of real peg/socket contact.
- What would come next: replace the proxy insertion shell with explicit peg/socket geometry and contact-driven success logic, then revisit transfer, imitation, or RL polishing on the real task.
