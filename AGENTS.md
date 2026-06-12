# AGENTS.md

## Project Hard Gate
- This repository is currently blocked on contact-physics validity.
- As of the 2026-06-11 audit, the Phase 2 peg/socket contact metrics are not trustworthy: the peg and socket walls are kinematic, `sync_peg_to_hand` teleports the peg each step, and the recorded contact force is not proven to be peg-vs-wall socket reaction.
- Do not run paid GPU/Brev/AWS work, controller sweeps, BC training/evaluation, or RL training until the environment has real peg-wall collision response and a wall-reaction smoke test passes.

## Required Next Technical Step
- Fix the environment so the peg can experience real PhysX contact: use either a dynamic peg rigidly attached to the hand through a physical joint or model the peg as part of the robot articulation.
- Remove per-step peg teleportation during contact phases; a teleported kinematic peg cannot receive meaningful wall reaction forces.
- Keep the socket guide walls as real colliders against the dynamic peg.
- Route success-gate contact through a peg-vs-wall filtered contact signal, not an unqualified peg net-force metric.
- Add a contact-physics smoke test that commands the peg into a wall and asserts both nonzero wall reaction and blocked motion.

## Experiment Rules
- Before trusting a metric, trace it to the exact code/data/sensor source.
- Before any expensive run, execute a semantic smoke test and at least one negative control.
- If moving or disabling the wall does not change the contact metric, stop and debug the task definition before any controller or policy work.
- Treat existing "true-contact", strict near-miss, near-contact BC, and final-contact candidate artifacts as diagnostic history only until regenerated under a physically valid contact model.

## Paid Compute Guard
- Paid compute requires an explicit budget, timeout, artifact pullback plan, and deletion/cleanup monitor.
- If Brev CLI auth is expired or instance state cannot be verified, do not create or continue paid work.
