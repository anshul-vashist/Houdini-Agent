# HoudiniMind Architecture & Data Flow Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE LAYER                          │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  HoudiniMindPanel (PySide6 Qt Widget)                        │   │
│  │  ├─ PanelBackendMixin   (Ollama/Model Management)           │   │
│  │  ├─ PanelStateMixin     (Session State & History)           │   │
│  │  ├─ PanelLayoutMixin    (Chat UI, Streaming Display)        │   │
│  │  ├─ PanelDispatchMixin  (Message Routing)                   │   │
│  │  └─ PanelWorkflowMixin  (Job Management, AutoResearch)      │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      AGENT ORCHESTRATION LAYER                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  AgentLoop (Core Planning & Execution Engine)               │   │
│  │                                                              │   │
│  │  ┌────────────────────────────────────────────────────┐     │   │
│  │  │ PLAN PHASE (Adaptive, complexity-gated)            │     │   │
│  │  │ └─ Analyze query intent                            │     │   │
│  │  │ └─ Prefetch RAG results                            │     │   │
│  │  │ └─ Generate task contract                          │     │   │
│  │  │ └─ Select tool subset                              │     │   │
│  │  └────────────────────────────────────────────────────┘     │   │
│  │                         │                                   │   │
│  │  ┌────────────────────────────────────────────────────┐     │   │
│  │  │ ACT PHASE (Tool Execution Loop)                    │     │   │
│  │  │ └─ Validate tool arguments (JSON Schema)           │     │   │
│  │  │ └─ Resolve parameter aliases & forward refs        │     │   │
│  │  │ └─ Execute with timeout (90s scene-mutating)       │     │   │
│  │  │ └─ Capture scene state deltas                      │     │   │
│  │  │ └─ Retry on failure (exponential backoff 3x)       │     │   │
│  │  └────────────────────────────────────────────────────┘     │   │
│  │                         │                                   │   │
│  │  ┌────────────────────────────────────────────────────┐     │   │
│  │  │ OBSERVE PHASE (Scene Analysis & Verification)      │     │   │
│  │  │ └─ Screenshot viewport (vision-enabled)            │     │   │
│  │  │ └─ Analyze geometry changes                        │     │   │
│  │  │ └─ Semantic scoring (multi-view renders optional)  │     │   │
│  │  │ └─ Completion detection (early exit at round 4)    │     │   │
│  │  └────────────────────────────────────────────────────┘     │   │
│  │                         │                                   │   │
│  │  ┌────────────────────────────────────────────────────┐     │   │
│  │  │ CRITIC PHASE (Repair & Safety Gating)             │     │   │
│  │  │ └─ Analyze failures (blacklist for 12 turns)       │     │   │
│  │  │ └─ Attempt LLM repair of tool arguments            │     │   │
│  │  │ └─ Gate risky operations (confidence threshold)    │     │   │
│  │  └────────────────────────────────────────────────────┘     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Supporting Systems:                                         │   │
│  │  ├─ Clarifier       (Ambiguous query resolution)            │   │
│  │  ├─ TaskContracts   (Scope & safety rules per task)         │   │
│  │  ├─ ReferenceProxy  (Forward reference resolution)          │   │
│  │  ├─ TurnBudget      (240s wall-clock, 200k input tokens)    │   │
│  │  ├─ CircuitBreaker  (Abort on 4 consecutive LLM failures)   │   │
│  │  └─ DebugLogger     (Session.md + LLM trace)                │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                 ┌───────────────┼───────────────┐
                 ↓               ↓               ↓
┌──────────────────────┐  ┌──────────────┐  ┌──────────────┐
│  KNOWLEDGE LAYER     │  │  TOOL LAYER  │  │  MEMORY      │
│  (RAG Engine)        │  │              │  │  (World Model)
│                      │  │  70+ Tools   │  │              │
│  ┌────────────────┐  │  │ 16 modules   │  │ ┌──────────┐ │
│  │ BM25 + Vector  │  │  │ Schema       │  │ │ Node     │ │
│  │ Search         │  │  │ validation   │  │ │ Reference│ │
│  └────────────────┘  │  │ Fuzzy match  │  │ │ Tracking │ │
│                      │  │              │  │ │ Workflow │ │
│  12 Shards:         │  │ Categories:   │  │ │ History  │ │
│  ├─ sop_nodes      │  │ ├─ Node       │  │ │ Error    │ │
│  ├─ dop_nodes      │  │ ├─ Chain      │  │ │ History  │ │
│  ├─ lop_nodes      │  │ ├─ Advanced   │  │ └──────────┘ │
│  ├─ recipes        │  │ ├─ Perf/Org   │  │              │
│  ├─ vex_reference  │  │ ├─ Inspection │  │ ┌──────────┐ │
│  ├─ python_ex      │  │ ├─ Geometry   │  │ │ Session  │ │
│  └─ ...            │  │ ├─ Knowledge  │  │ │ Metadata │ │
│                    │  │ ├─ Vision     │  │ │ Persistence
│  700+ docs         │  │ ├─ Simulation │  │ │          │ │
│  50+ recipes       │  │ └─ Material   │  │ └──────────┘ │
│  VEX snippets      │  │              │  │              │
└──────────────────────┘  └──────────────┘  └──────────────┘
```

---

## Tool Execution Flow

```
User Query
    │
    ├─→ [Intent Detection]
    │    ├─ BUILD: "create", "add", "setup"
    │    ├─ VEX: "vex", "snippet", "wrangle"
    │    ├─ HDA: "asset", "digital asset"
    │    ├─ DEBUG: "error", "fix", "broken"
    │    └─ RESEARCH: iterative KB enrichment
    │
    ├─→ [Scene Reference Detection]
    │    ├─ Parse node paths (e.g., "/obj/geo1")
    │    └─ Validate existence before planning
    │
    ├─→ [PLANNING PHASE] (if query is complex: word_count ≥ 10 OR technical terms)
    │    ├─ LLM generates task plan
    │    ├─ Prefetch RAG for relevant categories
    │    ├─ Select tool subset (reduce schema size)
    │    └─ Generate task contract
    │
    ├─→ [Preconditions Check]
    │    ├─ Validate scene state (e.g., "geo must exist")
    │    └─ Clarify ambiguous queries
    │
    ├─→ [TOOL SELECTION LOOP] (max 16 rounds)
    │    │
    │    ├─→ LLM selects next tool to call
    │    │
    │    ├─→ [Argument Validation]
    │    │    ├─ JSON Schema check
    │    │    ├─ Parameter name fuzzy-matching
    │    │    ├─ Vector coercion ("scale=1.5" → [1.5, 1.5, 1.5])
    │    │    ├─ Range validation
    │    │    └─ Type checking
    │    │
    │    ├─→ [Cache Lookup]
    │    │    └─ Return cached result if hit
    │    │
    │    ├─→ [Tool Execution] (with timeout)
    │    │    ├─ Execute Houdini operation
    │    │    ├─ Capture stdout/stderr
    │    │    └─ Record execution time
    │    │
    │    ├─→ [Error Handling]
    │    │    ├─ If failure:
    │    │    │  ├─ LLM attempts repair of args
    │    │    │  ├─ Retry with backoff (3x max)
    │    │    │  └─ Blacklist tool for 12 turns
    │    │    └─ Failure recorded to history
    │    │
    │    ├─→ [OBSERVE PHASE]
    │    │    ├─ Screenshot viewport (hash dedupe)
    │    │    ├─ Analyze geometry changes
    │    │    ├─ Collect scene errors/warnings
    │    │    ├─ Semantic scoring (if enabled)
    │    │    └─ Update world model
    │    │
    │    ├─→ [CRITIC PHASE]
    │    │    ├─ Analyze output safety
    │    │    ├─ Gate risky operations
    │    │    └─ Suggest rollback if needed
    │    │
    │    └─→ Loop until: completion detected OR budget exceeded OR max rounds reached
    │
    └─→ [Response Generation]
        ├─ Compile summary from observations
        ├─ Stream to UI in real-time
        └─ Save to session.md

```

---

## Data Flow: From Query to Scene Mutation

```
                            User Input
                               │
                    ┌──────────┼──────────┐
                    │          │          │
                Text Query  Vision   Clipboard
                    │          │          │
                    └──────────┼──────────┘
                               ↓
                    [Query Preprocessing]
                    ├─ Tokenize & embed
                    ├─ Detect intent
                    └─ Identify scene refs
                               │
                ┌──────────────┼──────────────┐
                │                             │
         [PLANNING]                    [No Planning]
         (if complex)                  (if trivial)
         RAG Prefetch                  Direct to Act
                │                             │
                └──────────────┬──────────────┘
                               ↓
                    [LLM Tool Selection]
                    ├─ Available tools (20 max)
                    ├─ Task contract guidance
                    ├─ Available node types
                    └─ RAG context (4k tokens max)
                               │
                               ↓
                    [Tool Call Formatting]
                    {"tool": "create_node",
                     "args": {
                       "parent_path": "/obj/geo1",
                       "node_type": "scatter",
                       "name": "scatter1"
                     }}
                               │
                               ↓
                    [Schema Validation]
                    ├─ JSON Schema check ✓
                    ├─ Type validation ✓
                    ├─ Range check ✓
                    └─ Fuzzy-match params ✓
                               │
                               ↓
                    [Houdini Execution]
                    ├─ Timeout: 90s
                    ├─ Thread-safe HOM calls
                    ├─ Auto-cook on create
                    └─ Capture errors/warnings
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
    [Success]            [Transient Error]     [Permanent Failure]
         │                     │                     │
    ┌────┴────┐          ┌─────┴──────┐        ┌────┴────┐
    │ Observe │          │ Retry 3x   │        │ Blacklist
    │ Scene   │          │ Backoff    │        │ 12 turns
    └────┬────┘          └─────┬──────┘        └────┬────┘
         │                     │                     │
         ├─ Screenshot ────┐   │                     │
         ├─ Geometry    ┌──┼───┴─────────────────┐   │
         │   analysis   │  │                     │   │
         ├─ Error audit │  │                     │   │
         └─ Attributes  │  │                     │   │
                        ↓  ↓                     ↓
                    [Scene State Update]
                    ├─ World model refresh
                    ├─ Node tracking
                    └─ Error history
                               │
                               ↓
                    [Completion Check]
                    ├─ Goal achieved?
                    ├─ Errors cleared?
                    └─ Geometry valid?
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
            [DONE]                      [CONTINUE]
                 │                           │
                 ↓                           ↓
            [Response                  [Next Tool]
             Generation]               (Loop back)
                 │
                 ├─ Compile observations
                 ├─ Format explanation
                 └─ Stream to UI

```

---

## Module Dependencies

```
agent/
├── loop.py
│   ├─ clarification.py (Clarifier)
│   ├─ critic.py (RepairCritic)
│   ├─ task_contracts.py (TaskContract)
│   ├─ semantic_scoring.py (Verification)
│   ├─ proxy_reference.py (ForwardRefs)
│   ├─ request_modes.py (IntentDetection)
│   ├─ tool_models.py (Validation)
│   ├─ tool_retry.py (CircuitBreaker)
│   └─ budget.py (TurnBudget)
│
├── tools/ (16 modules)
│   ├─ _core.py (Shared helpers)
│   ├─ _node_tools.py (20 tools)
│   ├─ _chain_tools.py (12 tools)
│   ├─ _advanced_tools.py (70+ tools)
│   ├─ _perf_org_tools.py (28 tools)
│   ├─ _inspection_tools.py (8 tools)
│   ├─ _geometry_tools.py (9 tools)
│   ├─ _knowledge_tools.py (7 tools)
│   ├─ _vision_tools.py (4 tools)
│   ├─ _pdg_tools.py (6 tools)
│   ├─ _simulation_tools.py
│   ├─ _material_usd_tools.py (12+ tools)
│   ├─ _scene_tools.py (4 tools)
│   ├─ _repair.py (Sim repair)
│   └─ __init__.py (Tool registry)
│
├── ui/ (6 mixins + main panel)
│   ├─ _panel.py (HoudiniMindPanel)
│   ├─ _panel_backend.py (Ollama, Models)
│   ├─ _panel_state.py (Session state)
│   ├─ _panel_layout.py (Qt widgets)
│   ├─ _panel_dispatch.py (Message routing)
│   └─ _panel_workflows.py (Job manager)
│
├── rag/
│   ├─ retriever.py (BM25 + Vector)
│   ├─ kb_builder.py (Knowledge index)
│   ├─ injector.py (RAG integration)
│   └─ bm25.py (Tokenizer)
│
├── bridge/
│   ├─ viewport_capture.py (Screenshots)
│   ├─ scene_reader.py (Scene introspection)
│   ├─ event_hooks.py (SSE broadcaster)
│   └─ render_tools.py (ROP interface)
│
├── memory/
│   └─ world_model.py (Session memory)
│
└── async_jobs.py (Job queue)

data/
├── core_config.json (Agent settings)
├── knowledge/
│   ├─ knowledge_base.json (700+ docs)
│   ├─ houdinimind_agent_recipes.json
│   ├─ houdini_python_functions.json
│   ├─ vex_functions.db
│   └─ vex_dataset_final_merged.jsonl
└── db/
    ├─ failure_memory.json (Error history)
    └─ world_model.json (Session metadata)

```

---

## Safety & Validation Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    INPUT VALIDATION                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 1. Intent Detection (BUILD/VEX/HDA/DEBUG/RESEARCH)     │ │
│  │ 2. Scene Reference Validation (node paths exist?)      │ │
│  │ 3. Clarification (ambiguous queries)                   │ │
│  │ 4. Precondition Check (scene state valid?)             │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────┴──────────────────────────────────────────────┐
│               TOOL ARGUMENT VALIDATION                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 1. JSON Schema conformance                             │ │
│  │ 2. Parameter name fuzzy-matching & alias resolution    │ │
│  │ 3. Type coercion (int→float, string→vector)            │ │
│  │ 4. Range checking (min/max, step size)                 │ │
│  │ 5. Enum validation (node type, context)                │ │
│  │ 6. Forward reference resolution (proxy nodes)          │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────┴──────────────────────────────────────────────┐
│            EXECUTION & ERROR HANDLING                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 1. Scene backup (if requested)                         │ │
│  │ 2. Timeout enforcement (90s scene-mutating)            │ │
│  │ 3. Automatic retry with backoff (3 attempts)           │ │
│  │ 4. LLM-based argument repair                           │ │
│  │ 5. Failure blacklist (12-turn window)                  │ │
│  │ 6. Circuit breaker (4 consecutive LLM failures)        │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────┴──────────────────────────────────────────────┐
│           POST-EXECUTION VERIFICATION                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 1. Scene observation (geometry, errors)                │ │
│  │ 2. Screenshot analysis (vision-enabled)                │ │
│  │ 3. Semantic scoring (optional multi-view)              │ │
│  │ 4. Critic gate (safety assessment)                     │ │
│  │ 5. Rollback decision (if needed)                       │ │
│  │ 6. World model update                                  │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────┬──────────────────────────────────────────────┘
               │
               ↓
        [Continue or Complete]
```

---

## Resource Management

```
[Token Budget]
├─ Input: 200k tokens max per turn
├─ Output: 16k tokens max per turn
├─ System prompt: ~2.5k tokens
├─ Tool schemas: ~6k tokens
├─ Scene context: ~5k tokens
└─ RAG context: 4k tokens max

[Time Budget]
├─ Turn wall-clock: 240s max
├─ Plan timeout: 90s
├─ Tool timeout: 90s (scene-mutating)
├─ Read timeout: 30s (read-only)
└─ Phase timeouts: Per-operation

[Memory Management]
├─ Embedding cache: 2048 entries (LRU)
├─ Session log: Line-buffered (survives crashes)
├─ Tool history: 80 progress entries max
├─ Stream log: 1200 entries max
└─ Scene snapshots: On-demand (viewport images)

[Streaming & Real-time]
├─ LLM response streaming: ~50ms chunks
├─ UI refresh: 22ms timer
├─ Panel state save: 400ms debounce
├─ Job progress: Multi-subscriber callbacks
└─ ASR: Partial + final transcription

```

---

## Configuration Priority & Overrides

```
core_config.json
    │
    ├─→ [Model Routing]
    │    ├─ planning: use lighter model (if set)
    │    ├─ build: use build model (if set)
    │    ├─ vex: use vex-optimized model (if set)
    │    ├─ semantic: use semantic model (if set)
    │    └─ embedding: always use nomic-embed-text (hardcoded)
    │
    ├─→ [Safety Overrides]
    │    ├─ auto_execute_confidence: 0.7 (70% required)
    │    ├─ enable_repair_critic: true
    │    ├─ tool_retry_enabled: true (3 attempts)
    │    ├─ circuit_breaker_threshold: 4 failures
    │    └─ failure_blacklist_window: 12 turns
    │
    ├─→ [RAG Configuration]
    │    ├─ rag_top_k: 5 results
    │    ├─ rag_hybrid_search: true (BM25 + vector)
    │    ├─ rag_max_context_tokens: 4000
    │    ├─ rag_max_shards_per_query: 5
    │    └─ prefetch_rag: true
    │
    ├─→ [Advanced Features]
    │    ├─ semantic_scoring_enabled: true
    │    ├─ semantic_multiview_enabled: false (resource intensive)
    │    ├─ plan_enabled: true (adaptive gating)
    │    ├─ proxy_generation_enabled: true
    │    └─ clarification_enabled: true
    │
    └─→ [UI State]
         ├─ stream_responses: true
         ├─ show_tool_calls: true
         ├─ detail_mode: "simple" (can change at runtime)
         └─ vision_enabled: true

```

---

## Typical Turn Lifecycle

```
Turn Start (t=0ms)
│
├─ [Receive Query] (t=10ms)
│  └─ Tokenize, detect intent, extract scene refs
│
├─ [PLANNING] (if complex) (t=50ms → 2500ms)
│  ├─ LLM generates plan
│  ├─ Prefetch RAG (5 shards, 4k tokens)
│  ├─ Create task contract
│  └─ Select tool subset
│
├─ [Tool Loop 1] (t=2500ms → 4000ms)
│  ├─ LLM tool selection (500ms)
│  ├─ Argument validation (100ms)
│  ├─ Tool execution (1000ms)
│  ├─ Scene observation (400ms)
│  └─ Cache results
│
├─ [Tool Loop 2] (t=4000ms → 5300ms)
│  ├─ LLM tool selection (500ms)
│  ├─ Argument validation (100ms)
│  ├─ Tool execution (600ms)
│  └─ Scene observation (100ms)
│
├─ [Completion Check] (t=5300ms)
│  └─ All goals achieved? → DONE
│
├─ [Response Generation] (t=5300ms → 5800ms)
│  ├─ Compile observations
│  ├─ Stream to UI (chunk every ~50ms)
│  └─ Log to session.md
│
└─ Turn Complete (t=5800ms)
   Total elapsed: 5.8s
   Tokens used: Input 8,432 | Output 1,247
   Tools called: 2
   Status: SUCCESS

```

---

Generated: 2026-05-06
