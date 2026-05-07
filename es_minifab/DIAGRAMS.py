"""
System Architecture Diagrams
=============================

MiniFab Integrated Training System - Visual Overview
"""

# ============================================================
# 1. COMPLETE SYSTEM ARCHITECTURE
# ============================================================

SYSTEM_ARCHITECTURE = """
╔═══════════════════════════════════════════════════════════════════════╗
║           MiniFab Integrated Training System Architecture             ║
╚═══════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────┐
│                        integrated_training.py                           │
│                      (Main Orchestrator & UI)                           │
└──────────────────┬──────────────────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┬──────────────┬──────────────┐
        │                     │              │              │
        ▼                     ▼              ▼              ▼
   ┌─────────┐         ┌──────────┐   ┌─────────────┐ ┌──────────┐
   │   Ray   │         │    ES    │   │  Decision   │ │ Results  │
   │ Training│         │ Trainer  │   │  System     │ │ Manager  │
   └─────────┘         └──────────┘   └─────────────┘ └──────────┘
        │                     │              │              │
        │                     │              │              │
        ▼                     ▼              ▼              ▼
   ┌─────────────┐  ┌──────────────┐ ┌─────────────────┐ ┌──────────┐
   │ minifab_    │  │ minifab_     │ │minifab_decision │ │Checkpoint│
   │ray_trainer  │  │es_trainer    │ │_system          │ │s & Report│
   └─────────────┘  └──────────────┘ └─────────────────┘ └──────────┘
        │                     │              │              │
        │                     │              │              │
        └─────┬──────────────┬┴──────────────┼──────────────┘
              │              │               │
              ▼              ▼               ▼
         ┌─────────────┐ ┌────────┐   ┌──────────────┐
         │   MultiAgent│ │Features│   │  Event Loop  │
         │   MiniFab   │ │Extract │   │  & Scheduler │
         │    Env      │ │  (12D) │   │              │
         └─────────────┘ └────────┘   └──────────────┘
"""

# ============================================================
# 2. DECISION POINT EVENT FLOW
# ============================================================

DECISION_POINT_FLOW = """
╔═══════════════════════════════════════════════════════════════════════╗
║             Decision Point Event-Driven Flow                          ║
║              (When Machine Completes Processing)                      ║
╚═══════════════════════════════════════════════════════════════════════╝

Step 1: TRIGGER EVENT
┌──────────────────────────────────┐
│ Machine completes processing     │
│ Event: MACHINE_AVAILABLE         │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ Handle Trigger Event             │
│ - Mark machine as IDLE           │
│ - Release completed lot to queue │
│ - Update machine state           │
└──────────┬───────────────────────┘
           │
Step 2: FEATURE EXTRACTION
           ▼
┌──────────────────────────────────┐
│  Extract 12D Feature Vector      │
│                                  │
│  Machine Features (4):           │
│  ├─ utilization                  │
│  ├─ setup_count                  │
│  ├─ pending_lots                 │
│  └─ idle_time                    │
│                                  │
│  Queue Features (4):             │
│  ├─ length                       │
│  ├─ max_age                      │
│  ├─ product_variety              │
│  └─ downstream_buffer_util       │
│                                  │
│  Lot Features (4):               │
│  ├─ remaining_steps              │
│  ├─ wait_time                    │
│  ├─ product_type                 │
│  └─ batch_potential              │
└──────────┬───────────────────────┘
           │
Step 3: NEURAL NETWORK DECISION
           ▼
┌──────────────────────────────────┐
│  Neural Network Policy           │
│                                  │
│  Input:  12D Feature Vector      │
│          ────────────            │
│  Layer1: Dense(64) + ReLU        │
│  Layer2: Dense(4)  + Softmax     │
│  Output: Action Probabilities    │
│                                  │
│  Decision: argmax(probabilities) │
│  Result: Best Lot to Assign      │
└──────────┬───────────────────────┘
           │
Step 4: SCHEDULE FUTURE EVENT
           ▼
┌──────────────────────────────────┐
│ Register Future Event             │
│                                  │
│ 1. Look up processing time:      │
│    time = PROCESS_TIME[step]     │
│                                  │
│ 2. Calculate completion time:    │
│    future = now + time           │
│                                  │
│ 3. Register in event queue:      │
│    queue.append(                 │
│      Event(                      │
│        time=future,              │
│        type=MACHINE_AVAILABLE,   │
│        lot_id=assigned_lot       │
│      )                           │
│    )                             │
│                                  │
│ 4. Continue simulation:          │
│    Jump to next event time       │
└──────────┬───────────────────────┘
           │
           ▼
    SIMULATION CONTINUES...
    (Timeline advances to next event)
"""

# ============================================================
# 3. EVOLUTION STRATEGIES PROCESS
# ============================================================

ES_PROCESS = """
╔═══════════════════════════════════════════════════════════════════════╗
║             Evolution Strategies (ES) Training Process               ║
║              (Peer Comparison, No Ground Truth)                      ║
╚═══════════════════════════════════════════════════════════════════════╝

Generation t:

┌─────────────────────────────────────────────────────────────────┐
│ Population P = {p1, p2, ..., p20}                              │
│ (20 strategies with different policies)                        │
└────────┬────────────────────────────────────────────────────────┘
         │
Phase 1: EVALUATION (Peer Comparison)
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ For each strategy:                                              │
│   Battle vs all other strategies (19 opponents)                 │
│   For each battle:                                              │
│     1. Run MiniFab environment                                  │
│     2. Measure final reward                                     │
│     3. Compare: who won?                                        │
│                                                                 │
│ Calculate Fitness:                                              │
│   Fitness = Win_Rate + Mean_Reward                              │
│                                                                 │
│ Result: Each strategy has fitness score                         │
└────────┬────────────────────────────────────────────────────────┘
         │
Phase 2: SELECTION (Elite Preservation)
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Sort by fitness:                                                │
│   p1 (fitness=125) ← Elite 1 (Top 4)                            │
│   p5 (fitness=118) ← Elite 2                                    │
│   p9 (fitness=112) ← Elite 3                                    │
│  p14 (fitness=108) ← Elite 4                                    │
│  p2 (fitness=98)                                                │
│  ...                                                            │
│  p19 (fitness=45)  ← Worst                                      │
│                                                                 │
│ Keep: Top 4 elite (direct to next generation)                   │
│ Discard: Bottom 16 (will be replaced by mutations)              │
└────────┬────────────────────────────────────────────────────────┘
         │
Phase 3: EVOLUTION (Mutation & Reproduction)
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ New Generation P' = Elite + Mutants                             │
│                                                                 │
│ Elite (4 strategies):                                           │
│   p1', p5', p9', p14'  ← Direct copy                            │
│                                                                 │
│ Mutants (16 offspring):                                         │
│   For i = 1 to 16:                                              │
│     1. Select random elite as parent                            │
│     2. Mutate weights: w' = w + noise * mutation_std            │
│     3. Adaptive mutation:                                       │
│        - Good parent: lower mutation (conservative)             │
│        - Poor parent: higher mutation (exploratory)             │
│     4. Add to new generation                                    │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
Generation t+1: P' = {p1', p5', p9', p14', mutations...}
                │
                └─→ Repeat from Generation t+1
                    (Continue for 10 generations)

Result: Best_Fitness improves over time
   ▲ Fitness
   │    ╱╱╱
   │  ╱╱╱╱╱
   │╱╱╱╱╱╱╱
   └────────→ Generations
     0  5  10
"""

# ============================================================
# 4. RAY PARALLEL EXECUTION
# ============================================================

RAY_PARALLEL = """
╔═══════════════════════════════════════════════════════════════════════╗
║         Ray Distributed Parallel Execution                           ║
║              (4 Actors, 4x Speedup)                                  ║
╚═══════════════════════════════════════════════════════════════════════╝

Task: Evaluate 20 strategies × 3 episodes = 60 environment steps

┌─────────────────────────────────────────────────────────────────┐
│ SEQUENTIAL (Without Ray)                                        │
│                                                                 │
│ P1-Ep1 ▓▓▓                                                      │
│ P1-Ep2 ▓▓▓                                                      │
│ P1-Ep3 ▓▓▓                                                      │
│ P2-Ep1 ▓▓▓                                                      │
│ ...    ...                                                      │
│ P20-Ep3 ▓▓▓                                                     │
│         ═══════════════════════════════════════════             │
│         Total Time: 60 time units                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ PARALLEL (With Ray - 4 Actors)                                  │
│                                                                 │
│ Actor 1: P1-Ep1 ▓▓▓ P1-Ep2 ▓▓▓ P1-Ep3 ▓▓▓ P5-Ep1 ▓▓▓ ...     │
│ Actor 2: P2-Ep1 ▓▓▓ P2-Ep2 ▓▓▓ P2-Ep3 ▓▓▓ P6-Ep1 ▓▓▓ ...     │
│ Actor 3: P3-Ep1 ▓▓▓ P3-Ep2 ▓▓▓ P3-Ep3 ▓▓▓ P7-Ep1 ▓▓▓ ...     │
│ Actor 4: P4-Ep1 ▓▓▓ P4-Ep2 ▓▓▓ P4-Ep3 ▓▓▓ P8-Ep1 ▓▓▓ ...     │
│         ════════════════════════════════════════════════         │
│         Total Time: 15 time units (4x faster!)                  │
│                                                                 │
│ Speedup = 60 / 15 = 4x ✅                                       │
└─────────────────────────────────────────────────────────────────┘

Master Thread:
  ┌─ Dispatch tasks to Actor pool
  ├─ Wait for completion
  ├─ Aggregate results
  └─ Calculate fitness

Actor 1          Actor 2          Actor 3          Actor 4
  │                │                │                │
  ├─ Run Env    ├─ Run Env    ├─ Run Env    ├─ Run Env
  ├─ Get Reward ├─ Get Reward ├─ Get Reward ├─ Get Reward
  └─ Return     └─ Return     └─ Return     └─ Return
     Results       Results       Results       Results
        │            │              │            │
        └────────────┴──────────────┴────────────┘
                      │
                      ▼
                Aggregation
                   │
                   ├─ Mean Reward
                   ├─ Mean Makespan
                   ├─ Mean Setup Count
                   └─ Other Metrics
"""

# ============================================================
# 5. COMPLETE TRAINING LOOP
# ============================================================

COMPLETE_LOOP = """
╔═══════════════════════════════════════════════════════════════════════╗
║        Complete Training Loop (10 Generations)                       ║
╚═══════════════════════════════════════════════════════════════════════╝

Start
  │
  ▼
Initialize
  ├─ Ray cluster (4 actors)
  ├─ ES population (20 random strategies)
  └─ Event scheduler

  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│ FOR EACH GENERATION (0 to 9):                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ 1. Evaluate Population                                          │
│    ├─ ES: 20 strategies battle each other                       │
│    ├─ Ray: 4 actors evaluate in parallel                        │
│    └─ Result: Fitness for each strategy                         │
│                                                                 │
│ 2. Distributed Rollout                                          │
│    ├─ Select best strategy                                      │
│    ├─ Ray: 4 actors run 3 episodes each                         │
│    ├─ Features automatically extracted                          │
│    ├─ Events automatically scheduled                            │
│    └─ Result: Performance metrics (Makespan, Setup...)          │
│                                                                 │
│ 3. Evolve Population                                            │
│    ├─ Elite preservation (top 4)                                │
│    ├─ Mutate offspring (16 new strategies)                      │
│    └─ Result: New population P'                                 │
│                                                                 │
│ 4. Save Checkpoint                                              │
│    ├─ Every 5 generations                                       │
│    ├─ Save: Population, stats, metadata                         │
│    └─ File: gen_{n}_checkpoint.json                             │
│                                                                 │
│ Progress: Gen X/10, Fitness: Y, Makespan: Z min                │
└─────────────────────────────────────────────────────────────────┘
  │
  └─ Next Generation

  │
  ▼
Final Report
  ├─ Best fitness reached
  ├─ Performance improvement
  ├─ Final policy weights
  ├─ Training history
  └─ Output: training_report.json

  │
  ▼
End (Results saved)
"""

# ============================================================
# 6. DATA FLOW DIAGRAM
# ============================================================

DATA_FLOW = """
╔═══════════════════════════════════════════════════════════════════════╗
║              Data Flow in Decision Point                              ║
╚═══════════════════════════════════════════════════════════════════════╝

Environment State
    │
    ├─ Machine states
    ├─ Queue contents
    ├─ Lot positions
    └─ Current time
    │
    ▼
Feature Extractor
    │
    ├─ Input: Environment state
    │
    ├─ Calculate:
    │  ├─ Machine utilization = busy_time / total_time
    │  ├─ Setup count = # of setup events
    │  ├─ Queue length = # of lots waiting
    │  ├─ Max wait time = now - min(ready_time)
    │  ├─ Product variety = # unique products / queue size
    │  ├─ Downstream util = queue[next_cell] / buffer_capacity
    │  ├─ Remaining steps = len(flow) - step_index
    │  ├─ Lot wait time = now - lot.ready_time
    │  ├─ Product type = encode(product)
    │  └─ Batch potential = # compatible lots / 3
    │
    └─ Output: 12D feature vector [0.5, 0.0, 1.0, ..., 0.8]
        │
        ▼
    Policy Network (Neural Network)
        │
        ├─ Input layer: 12 features
        │  w1: (12, 64) matrix
        │  b1: (64,) vector
        │
        ├─ Hidden layer: z = ReLU(features @ w1 + b1)
        │
        ├─ Output layer: logits = z @ w2 + b2
        │  w2: (64, 4) matrix
        │  b2: (4,) vector
        │
        ├─ Softmax: probs = softmax(logits)
        │  Output: [0.15, 0.35, 0.40, 0.10]
        │           (probabilities for 4 actions)
        │
        └─ Decision: action = argmax(probs)
            Result: Action 2 (index with highest prob)
        │
        ▼
    Event Scheduler
        │
        ├─ Input: selected action (action 2)
        │
        ├─ Determine:
        │  ├─ Target machine
        │  ├─ Processing time = PROCESS_TIME[current_step]
        │  └─ Completion time = now + processing_time
        │
        └─ Register event:
            Event {
              time: completion_time,
              type: MACHINE_AVAILABLE,
              machine: machine_name,
              lot: lot_id
            }
        │
        ▼
    Continue Simulation
    (Time advances to next event)
"""

# ============================================================
# PRINTER FUNCTION
# ============================================================

def print_all_diagrams():
    """Print all diagrams"""
    diagrams = [
        ("SYSTEM ARCHITECTURE", SYSTEM_ARCHITECTURE),
        ("DECISION POINT FLOW", DECISION_POINT_FLOW),
        ("EVOLUTION STRATEGIES", ES_PROCESS),
        ("RAY PARALLEL EXECUTION", RAY_PARALLEL),
        ("COMPLETE TRAINING LOOP", COMPLETE_LOOP),
        ("DATA FLOW", DATA_FLOW),
    ]
    
    for title, diagram in diagrams:
        print("\n" + "="*80)
        print(f"  {title}")
        print("="*80)
        print(diagram)
        print("\n[Press Enter to continue...]")
        input()


if __name__ == "__main__":
    print("MiniFab System Architecture Diagrams")
    print("=====================================\n")
    
    import sys
    if len(sys.argv) > 1:
        # Print specific diagram
        diagram_name = sys.argv[1].upper()
        print(f"\nShowing: {diagram_name}\n")
        
        diagrams = {
            "ARCHITECTURE": SYSTEM_ARCHITECTURE,
            "DECISION": DECISION_POINT_FLOW,
            "ES": ES_PROCESS,
            "RAY": RAY_PARALLEL,
            "LOOP": COMPLETE_LOOP,
            "FLOW": DATA_FLOW,
        }
        
        if diagram_name in diagrams:
            print(diagrams[diagram_name])
        else:
            print("Available: ARCHITECTURE, DECISION, ES, RAY, LOOP, FLOW")
    else:
        # Interactive menu
        print("Available diagrams:")
        print("  1. ARCHITECTURE    - Complete system architecture")
        print("  2. DECISION        - Decision point event flow")
        print("  3. ES              - Evolution strategies process")
        print("  4. RAY             - Ray parallel execution")
        print("  5. LOOP            - Complete training loop")
        print("  6. FLOW            - Data flow diagram")
        print("  7. ALL             - Show all diagrams")
        print("\nUsage: python DIAGRAMS.py [diagram_name]")
        print("Example: python DIAGRAMS.py ARCHITECTURE")
