# Task Breakdown

## Phase 1

### Task contract

- Task name: `peg_in_hole`
- Success: peg inserted beyond a depth threshold with stable final pose
- Failure: timeout, object drop, excessive contact impulse, or unstable final pose

### Baselines

- Scripted baseline: deterministic approach-align-insert sequence
- RL baseline: single-policy contact task
- Repro baseline: fixed seed eval and video capture

### Deliverables

- task spec
- observation spec
- action spec
- reward spec
- reset rules
- evaluation metrics
- remote run workflow

## Phase 2

- observation noise
- actuation delay
- contact and friction randomization
- ROS 2 interface consistency

## Phase 3

- demonstrations
- IL hooks
- Mimic / SkillGen feasibility check

## Phase 4

- language-to-skill interface
- high-level planner
- failure explanation and retry policy
