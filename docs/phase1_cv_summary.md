# Phase 1 CV Summary

## One-line project description

Built a custom Isaac Lab peg-in-hole assembly environment with scripted and PPO baselines, remote Brev GPU training/evaluation workflows, and reproducible artifact export for contact-rich manipulation experiments.

## Resume-ready bullets

- Built a custom `peg-in-hole` task package in Isaac Lab for Franka relative-IK control, with task registration, reward design, fixed-step evaluation, and remote artifact capture.
- Implemented end-to-end remote experiment tooling on Brev for PPO training, checkpoint evaluation, checkpoint sweeps, cold-start runtime recovery, and reproducible log/checkpoint pullback to an external SSD.
- Drove the policy from coarse approach to near-insertion alignment; best continuation run reached `lateral=0.0105`, `axial=0.0092`, and `rot=0.6265` in fixed-step evaluation, then used failed late-stage curriculum variants to isolate the remaining rotational-convergence bottleneck.

## Short README / portfolio summary

This project focuses on a narrow but realistic contact-rich manipulation problem: peg-in-hole insertion in Isaac Lab. The first phase established a complete engineering loop for remote GPU training, evaluation, and artifact archival, rather than stopping at environment scaffolding. PPO learned reliable approach and near-socket alignment, and the strongest continuation run substantially reduced the remaining pose error, but true insertion success remained blocked by late-stage rotational convergence. That outcome is still useful: it demonstrates environment design, reward iteration, experiment management, and failure analysis in a robotics ML workflow.

## Interview framing

- Why this scope: a narrow contact-rich task was a better first milestone than a broad multi-skill system because it forced the project to close the sim/training/eval loop.
- What worked: task packaging, remote runtime recovery, reproducible training/evaluation, and learning a stable near-insertion policy.
- What did not: late-stage orientation polishing did not generalize across multiple curriculum variants.
- What the failure means: the remaining problem is not gross reachability; it is the final insertion regime under a proxy task setup.
- What would come next: replace the proxy insertion shell with explicit peg/socket geometry and contact-driven success logic, then revisit late-stage curriculum or imitation-based polishing.
