# HoudiniMind Agent Codebase: Comprehensive Feature & Capability Overview

## Executive Summary

HoudiniMind is a sophisticated agentic AI framework for SideFX Houdini 21 that operates through a tool-using agent loop. The system follows a **Plan → Act → Observe** workflow with extensive safeguards, schema validation, and knowledge retrieval to enable natural language-driven procedural modeling and FX workflows.

**Key Stats:**
- 70+ tool functions across 16 specialized tool modules
- 32,768-token context window with adaptive compaction
- Hybrid RAG system (BM25 + vector embeddings) with 700+ SOP docs
- Real-time PySide6 UI with streaming responses
- MCP (Model Context Protocol) server integration
- Fully local-first via Ollama (qwen3.5:397b-cloud recommended)

---

## 1. CORE AGENT FEATURES

### 1.1 Agent Loop Architecture (`agent/loop.py`)

**Main Components:**
- **AgentLoop class**: Central orchestration engine managing the Plan→Act→Observe cycle
- **Multi-phase execution**: 
  - Planning phase (optional, adaptive based on query complexity)
  - Tool selection & validation
  - Tool execution with strict schema checking
  - Observation & scene analysis
  - Criticism/repair gate (blocks problematic tool calls)
  - Completion detection

**Advanced Features:**
- **Context management**: 32k token budget with sliding compaction for dense networks
- **LLM call instrumentation**: Per-phase logging with latency tracking
- **Model routing**: Task-aware model selection (planning, build, debug, quick, research, vex, semantic)
- **Tool caching**: Cache-hit/miss logging for efficient scene observations
- **Adaptive planning**: Skips planning for trivial queries (word count < 10)
- **Circuit breaker**: Aborts on consecutive LLM backend failures (HTTP 5xx)
- **Turn budget**: Wall-clock limits (240s default) + token budgets (200k input, 16k output)
- **Early exit**: Completion detection as early as round 4

**Key Imports & Dependencies:**
- `DebugLogger`: Comprehensive session logging
- `WorldModel`: Long-term memory management
- `TurnBudget`: Token/time budget enforcement
- `Clarifier`: Handles ambiguous user requests
- `RepairCritic`: Gates tool calls for safety
- `ReferenceProxyPlanner`: Manages forward references
- `AutoResearcher`: Autonomous knowledge base updates
- `SceneObserver`: Live scene introspection

### 1.2 Request Modes & Mode Detection

The system intelligently detects intent from natural language:

**Intent Patterns:**
- **BUILD intent**: "create", "add", "setup", "make", "build" → triggers node building
- **VEX intent**: "vex", "snippet", "wrangle", "code" → VEX compilation & validation
- **HDA intent**: "asset", "hda", "digital asset" → asset creation workflows
- **DEBUG intent**: "error", "fix", "broken", "not working" → error tracing
- **RESEARCH intent**: Iterative knowledge base enrichment

**Mode-specific Tool Filtering:**
- Tools are dynamically filtered per intent to reduce schema bloat
- Non-scene-mutating tools prioritized for read operations
- Failure blacklist prevents repeated tool errors (12-turn window)

### 1.3 Scene Reference Detection

**Scene Reference System:**
- Detects when queries reference specific nodes (e.g., "connect /obj/geo1/out to /obj/geo2/in")
- Validates node existence before planning
- Formats gate-block messages for invalid references
- Prevents building on non-existent paths

### 1.4 Semantic Scoring & Verification

**Optional multi-view verification:**
- Runs OpenGL renders from multiple camera angles (when enabled)
- Compares rendered output to user intent
- Scores alignment: color, geometry, lighting accuracy
- Gates completion on semantic threshold (0.72 default)

### 1.5 Task Contracts & Preconditions

**Task Contract System:**
- Defines scope, safety rules, and rollback procedures per task
- Validates preconditions before execution (e.g., "geo must exist")
- Maps RAG categories to task types
- Formats guidance prompts from contracts

### 1.6 Tool Validation & Argument Handling

**Safety Layer:**
- JSON Schema validation for every tool call
- Argument type checking & range validation
- Parameter resolution (fuzzy matching for parameter names)
- Vector coercion (supports "scale=1.5" → [1.5, 1.5, 1.5])
- Automatic mesh/vector type detection

---

## 2. TOOL CATEGORIES & CAPABILITIES

HoudiniMind provides **70+ tools** organized into 8 major categories:

### 2.1 Node Tools (`_node_tools.py`) - **20 tools**

**Core Node Operations:**
- `create_node()` - Creates nodes with auto-correction (locked HDA detection, parent context inference)
- `delete_node()` - Safe deletion with undo tracking
- `safe_set_parameter()` - Parameter setting with alias resolution and vector expansion
- `set_parameter()` - Direct literal value setting
- `connect_nodes()` - Wire nodes with input/output indexing
- `disconnect_node()` - Remove connections
- `bypass_node()` - Toggle bypass flag

**Expression & VEX:**
- `set_expression()` - HScript/Python expressions
- `set_expression_from_description()` - LLM-generated expressions from natural language
- `write_vex_code()` - VEX with compile validation
- `write_python_script()` - Python SOP code
- `execute_python()` - Arbitrary Python execution (with security checks)

**Advanced Node Features:**
- `verify_node_type()` - Pre-check node types against live Houdini
- `list_node_types()` - Browse available nodes per context
- `resolve_build_hints()` - Suggest fixes for parameter/type mismatches
- `get_bounding_box()` - Geometry bounds analysis
- `set_display_flag()` - Display/render flag management
- `finalize_sop_network()` - Auto-detect and wire terminal SOPs to output
- `set_relative_parameter()` - Parametric positioning (e.g., "position above another object")
- `set_multiparm_count()` - Multiparm block sizing
- `create_copy_to_points_setup()` - Specialized helper for copy-to-points workflows

**Context Awareness:**
- Detects locked HDAs and suggests unlocking
- Auto-corrects parent context (e.g., /obj vs /obj/geo)
- Validates node types against container context (SOP vs DOP vs LOP)
- Handles both singular parameter and tuple parameter coercion

### 2.2 Chain Tools (`_chain_tools.py`) - **12 tools**

**Multi-node Assembly:**
- `create_node_chain()` - **Two-pass builder**: creates all nodes, then wires inputs (resolves forward references)
  - Auto-inserts Volume Rasterize before Pyro Solver
  - Handles multiparm inputs correctly
  - Reports partial failures without rollback
  - Supports explicit input naming or auto-sequence wiring
  - Validates all node types before creation
  - Cook-error severity classification (expected input warnings vs fatal errors)

**Network Organization:**
- `create_subnet()` - Create subnet and move nodes inside
- `auto_connect_chain()` - Sequential wiring (0→1→2)
- `promote_parameter()` - Expose parameters up to parent subnet
- `set_node_color()` - Visual organization by type/role
- `set_node_comment()` - Annotate nodes inline
- `create_network_box()` - Labeled groups in network editor
- `layout_network()` - Auto-layout children
- `add_sticky_note()` - Documentation annotations
- `add_spare_parameters()` - Dynamic parameter creation (float, int, toggle, color, string)
- `create_bed_controls()` - Domain-specific control nulls

### 2.3 Advanced Tools (`_advanced_tools.py`) - **70+ tools**

This module handles complex scene operations:

**VDB & Volume Operations:**
- `analyze_vdb()` - Inspect VDB grids, resolution, bounds
- `list_vdb_grids()` - Enumerate grids in a VDB
- `get_packed_geo_info()` - Packed primitive introspection

**USD/Solaris:**
- `assign_usd_material()` - Material assignment in LOP networks
- `create_usd_light()` - Karma/USD light creation
- `get_usd_prim_attributes()` - Query USD prim data
- `validate_usd_stage()` - USD hierarchy validation
- `list_material_assignments()` - Scene material audit

**HDA (Digital Assets):**
- `convert_to_hda()` / `convert_network_to_hda()` - Create HDAs from networks
- `get_hda_parameters()` - Inspect published parameters
- `add_hda_parameters()` - Add new parameters to asset
- `reload_hda_definition()` - Update HDAs on disk
- `list_installed_hdas()` - Browse available assets
- `diff_hda_versions()` - Compare HDA revisions

**Animation & Timing:**
- `bake_expressions_to_keys()` - Convert expressions to keyframes
- `edit_animation_curve()` - Smooth/adjust FCurve
- `cook_network_range()` - Timeline cooking
- `get_cook_dependency_order()` - Execution order analysis

**Scene Utilities:**
- `copy_paste_nodes()` - Node duplication with linking
- `collapse_to_subnet()` - Group & encapsulate
- `get_parm_expression_audit()` - Find all expressions in scene
- `list_all_file_references()` - Dependency tracking
- `scan_missing_files()` - Broken path detection
- `remap_file_paths()` - Batch path correction
- `lock_node()` - Read-only mode
- `create_documentation_snapshot()` - Node network docs export

**Rendering & Output:**
- `setup_render_output()` - ROP chain setup
- `setup_aov_passes()` - Multi-pass AOV configuration
- `submit_render()` - Render submission
- `set_viewport_camera()` - Camera navigation
- `set_viewport_display_mode()` - Shading mode control
- `set_object_visibility()` - Show/hide management

**Simulation Setups:**
- `setup_pyro_sim()` - Smoke/fire with rasterization
- `setup_grain_sim()` - Sand/granular materials
- `setup_feather_sim()` - Cloth/feather solver
- `setup_crowd_sim()` - Agent-based crowds
- `setup_wire_solver()` - Wire dynamics
- `setup_karma_material()` - PBR material creation

**Scene Management:**
- `create_take()` - Named scene variation
- `switch_take()` / `list_takes()` - Take management
- `eval_hscript()` - HScript expression evaluation
- `watch_node_events()` - SSE broadcaster for external tools
- `write_vop_network()` - VOP builder
- `get_memory_usage()` - Memory profiling
- `auto_color_by_type()` - Visual node classification

### 2.4 Performance & Organization (`_perf_org_tools.py`) - **28 tools**

**Performance Profiling:**
- `profile_network()` - Cook leaderboard (top N slowest nodes)
- `measure_cook_time()` - Per-node timing
- `get_node_cook_info()` - Cook state: dirty, time-dependent, locked, errors
- `suggest_optimization()` - Rule-based suggestions (merge counts, instancing opportunities)
- `deep_error_trace()` - Root cause analysis (walks upstream to error origin)
- `audit_spatial_layout()` - Detect overlapping nodes in network editor

**Node Operations:**
- `rename_node()` - Safe renaming
- `duplicate_node()` - Clone with optional new name
- `take_node_snapshot()` - State capture for debugging
- `compare_nodes()` - Parameter diff between two nodes

**Geometry I/O:**
- `load_geometry()` - File loading (.bgeo, .abc, .usd)
- `export_geometry()` - Frame-specific export
- `create_camera()` - Camera node with positioning helpers
- `remove_flat_copytopoints()` - Specialized cleanup (detects copy-to-points on flat sources)

**Timeline & Animation:**
- `go_to_frame()` - Frame navigation
- `set_frame_range()` - Playback range
- `set_keyframe()` - Keyframe creation with slope control
- `get_timeline_keyframes()` - Keyframe query per parameter
- `delete_keyframe()` - Keyframe removal

**Batch Operations:**
- `batch_set_parameters()` - Multi-node parameter assignment
- `find_and_replace_parameter()` - Search/replace across scene
- `beautify_network()` - Auto-organize with network boxes

**Domain-Specific:**
- `fix_furniture_legs()` - Procedural leg positioning (specialized for furniture modeling)
- `batch_align_to_support()` - Align multiple objects to support surface
- `get_stacking_offset()` - Vertical spacing calculation

### 2.5 Inspection Tools (`_inspection_tools.py`) - **8 tools**

**Scene Queries:**
- `get_scene_summary()` - Node tree overview (depth-limited)
- `get_all_errors()` - Scene-wide error/warning audit
- `find_nodes()` - Pattern search with type/error filtering
- `get_current_node_path()` - Active node context
- `inspect_display_output()` - Display node analysis

**Node Details:**
- `get_node_parameters()` - Parameter listing (compact mode: labels + current values)
- `get_node_inputs()` - Input port analysis
- `get_geometry_attributes()` - Point/prim/detail attribute enumeration

### 2.6 Geometry Tools (`_geometry_tools.py`) - **9 tools**

**Geometry Analysis:**
- `analyze_geometry()` - Comprehensive stats: point count, primitives, bounds, attribute summary
- `check_geometry_issues()` - Diagnostic checks (flipped normals, overlapping points, open mesh)
- `sample_geometry()` - Point sampling with attribute extraction
- `get_parameter_details()` - Parameter metadata (range, default, type)

**Spatial Operations:**
- `batch_align_to_support()` - Align multiple objects to support geometry
- `get_stacking_offset()` - Vertical spacing between objects
- `create_transformed_node()` - Node creation with support-relative positioning
- `audit_network_layout()` - Network editor collision detection

### 2.7 Knowledge & Research (`_knowledge_tools.py`) - **7 tools**

**RAG-driven Search:**
- `search_knowledge()` - Full semantic/keyword hybrid search
- `explain_node_type()` - Node documentation retrieval
- `get_node_recipe()` - Workflow procedures from knowledge base
- `get_vex_snippet()` - Code templates for VEX patterns
- `get_error_fix()` - Error message → solution mapping
- `suggest_workflow()` - Goal → procedural workflow suggestion
- `get_python_example()` - Python HOM code samples

**Knowledge Management:**
- Uses BM25 + cosine vector similarity (Ollama embeddings)
- 700+ SOP node docs, 50+ recipes, VEX functions
- Query expansion (e.g., "sim" → "simulation", "solver", "dop")
- Context-aware shard routing (e.g., VEX queries prefer vex_reference shard)

### 2.8 Vision Tools (`_vision_tools.py`) - **4 tools**

**Visual Understanding:**
- `capture_viewport()` - Screenshot PNG for LLM vision
- `describe_network_editor()` - AST-like node graph description
- `measure_pixel_similarity()` - Compare render outputs
- `detect_viewport_content()` - Object/node identification from viewport

### 2.9 Simulation & Domain Tools

**Simulation Repair (`_repair.py`):**
- `suggest_node_repairs()` - Analyzes solver nodes (FLIP, Pyro, RBD, Vellum)
- Detects common issues: missing colliders, wrong attributes, unsupported modes
- Returns actionable fix suggestions

**PDG/TOP (`_pdg_tools.py`):**
- `create_top_network()` - Task graph setup
- `create_top_node()` - Node instantiation in TOP
- `create_python_script_top()` - Python task creation
- `create_file_cache_top()` - Cache node setup
- `submit_pdg_cook()` - Execute task graph
- `get_pdg_work_items()` - Task status query

**Material & USD (`_material_usd_tools.py`):**
- `create_material()` - Karma material builder
- `setup_fabric_lookdev()` - Fabric shader setup
- `setup_karma_material()` - PBR material chain
- `assign_material()` - Apply materials to groups
- `create_uv_seams()` - Auto/manual UV seaming
- `create_lop_node()` - Generic LOP node creation
- `get_usd_hierarchy()` - USD prim tree dump

### 2.10 Scene Tools (`_scene_tools.py`)

**Session Management:**
- `get_scene_summary()` - Tree overview
- `get_hip_info()` - Scene file metadata
- `get_all_errors()` - Error/warning audit
- `create_backup()` - Auto-backup creation

---

## 3. UI/UX FEATURES

### 3.1 Panel Architecture (`agent/ui/`)

**Modular Design** (6 component mixins):

1. **PanelBackendMixin** (`_panel_backend.py`)
   - Async backend initialization (RAG, MemoryManager, AgentLoop)
   - Ollama connection management
   - Model loading & switching
   - Settings persistence

2. **PanelStateMixin** (`_panel_state.py`)
   - Session state tracking
   - Turn history & outputs
   - Tool call history
   - Debug log management
   - Auto-save (400ms debounce)

3. **PanelLayoutMixin** (`_panel_layout.py`)
   - Chat bubbles (user/agent)
   - Input box with auto-expand
   - Response streaming display
   - Tool call visualization
   - Detail mode toggle (simple/intermediate/expert)
   - Focus mode (hide sidebar)

4. **PanelDispatchMixin** (`_panel_dispatch.py`)
   - Message routing
   - Streaming response chunks
   - Tool call intercept/display
   - Error handling & recovery

5. **PanelWorkflowMixin** (`_panel_workflows.py`)
   - Quick prompt templates
   - AutoResearch loop management
   - Async job monitoring
   - Job cancellation
   - Streaming job progress

6. **HoudiniMindPanel** (main composite)
   - Signal definitions (stream_chunk, response_done, tool_called, scene_error, etc.)
   - Event handling
   - Threading integration

**Key UI Features:**
- **Real-time streaming**: Response text streams as it's generated
- **Vision capture**: Button to send viewport screenshot with queries
- **Job monitor**: Active job progress display
- **Detail modes**: Simple (basic output) → Intermediate (tool calls) → Expert (full trace)
- **Quick prompts**: Pre-built templates for common tasks
- **Settings panel**: Model selection, temperature, context options
- **Failure inspector**: Shows last turn failures with fix suggestions
- **Turn status**: Elapsed time, token count, tool round indicator

### 3.2 Responsive Behavior

- **Non-blocking UI**: Async job execution via threading prevents Houdini freeze
- **Live updates**: 22ms refresh timer drains live stream queue
- **State persistence**: Panel state saved to disk after 400ms idle
- **ASR support**: Speech-to-text with partial/final transcription
- **Vision on-demand**: User can toggle vision for specific messages

---

## 4. RAG & KNOWLEDGE BASE

### 4.1 Knowledge Base Architecture (`rag/`)

**Hybrid Search System:**
- **BM25 keyword matching**: Fast exact-match retrieval
- **Cosine similarity**: Semantic vector search via Ollama embeddings (nomic-embed-text)
- **Configurable blend**: `hybrid_weight` parameter (default: 0.5)
- **Graceful degradation**: Falls back to BM25-only if embeddings unavailable

**Data Organization:**
- **Shards**: Categorized knowledge repositories
  - `sop_nodes` - SOP node documentation (700+ docs)
  - `dop_nodes` - Dynamics documentation
  - `lop_nodes` - Solaris/USD documentation
  - `recipes` - 50+ procedural workflows
  - `vex_reference` - VEX functions & idioms
  - `python_examples` - HOM code samples
  - `troubleshooting` - Common issues & fixes
  - `simulation` - FX solver setups
  - `usd_workflows` - USD/Solaris patterns
  - `asset_workflows` - HDA best practices
  - `hda_examples` - Asset case studies
  - `general_reference` - Miscellaneous docs

**Query Features:**
- **Query expansion**: e.g., "sim" → "simulation", "solver", "dop"
- **Context-aware routing**: VEX queries prioritize vex_reference shard
- **Keyword synonym matching**: Low-weight expansions (move→translate, fix→solve)
- **Node title prefix filtering**: Extracts "sop node: box" from docs
- **Entry size capping**: 20k char limit per entry (prevents distortion from large OBJ rig docs)

**Retrieval Configuration:**
- `rag_top_k`: 5 results per query (default)
- `rag_min_score`: 0.1 minimum score threshold
- `rag_max_context_tokens`: 4000 tokens max context per turn
- `rag_hybrid_search`: true (BM25 + vector)
- `rag_max_shards_per_query`: 5 shards searched
- `prefetch_rag`: true (pre-fetch during planning)

**Knowledge Base Files:**
```
data/knowledge/
├── knowledge_base.json         # Main index (700+ entries)
├── houdinimind_agent_recipes.json  # Workflow procedures
├── houdini_python_functions.json   # HOM API docs
├── vex_functions.db            # VEX reference
└── vex_dataset_final_merged.jsonl # VEX code examples
```

### 4.2 RAG Pipeline Integration

- **Planning phase prefetch**: RAG runs during planning for relevant categories
- **Category mapping**: Task type → RAG shard routing
- **Logging & metrics**: RAG queries logged to debug sessions
- **Embedding cache**: Up to 2048 cached embeddings (LRU eviction)
- **Vector storage**: Embedding vectors stored alongside KB entries (sidecar JSON)

---

## 5. BRIDGE & HOUDINI INTEGRATION

### 5.1 Viewport & Scene Capture (`bridge/viewport_capture.py`)

**Screenshot Capabilities:**
- Tries hou.ui.paneTabOfType to locate viewer
- Falls back to full Houdini window capture
- Supports multiple pane types (viewport, network editor, etc.)
- Converts to base64 PNG for LLM vision
- Hash-based deduplication (prevents sending identical images)

**Use Cases:**
- Vision-enabled understanding of current viewport
- Network editor layout analysis
- Geometry inspection from rendered viewport

### 5.2 Scene Reading (`bridge/scene_reader.py`)

**Live Scene Introspection:**
- Read-only node tree traversal
- Parameter extraction (names, types, ranges, defaults)
- Geometry statistics (point/prim counts, bounds)
- Error/warning collection
- Attribute enumeration

### 5.3 Event Hooks (`bridge/event_hooks.py`)

**Server-Sent Events (SSE):**
- Optional real-time event broadcaster on port 9877
- Tracks node creation, parameter changes
- External tools (Cursor with MCP) can subscribe
- Keepalive heartbeat every 15s

### 5.4 Rendering Integration (`bridge/render_tools.py`)

**Render Operations:**
- ROP path validation
- AOV pass setup
- Render submission & tracking
- Output file resolution

---

## 6. ASYNC JOB MANAGEMENT

### 6.1 Job Manager (`agent/async_jobs.py`)

**Job State Machine:**
```
queued → running → completed (or failed/cancelled)
```

**Components:**
- **AgentJobState**: Dataclass tracking job metadata
- **AsyncJobManager**: Thread-safe job queue with callbacks

**Features:**
- Job submission with custom runner function
- Stream callbacks (chunk-by-chunk progress)
- Done callbacks (completion notification)
- Configurable log size limits (max 80 progress entries, 1200 stream entries)
- Progress message extraction (filters control characters)
- Runtime status recording (substate, checkpoint, metadata)
- Latency tracking (started_at, finished_at)
- Multi-subscriber support per job

**Usage Pattern:**
```python
job_id = job_manager.submit(
    kind="build",
    runner=lambda progress_fn, status_fn: agent.run(query),
    stream_callback=lambda chunk: ui.append_chunk(chunk),
    done_callback=lambda result: ui.show_result(result)
)
```

---

## 7. MEMORY & DEBUGGING

### 7.1 World Model (`memory/world_model.py`)

**Long-term Memory:**
- Session metadata storage
- Node reference tracking
- Workflow history
- Error history (for fallback suggestions)

### 7.2 Debug Logger (`debug.py`)

**Comprehensive Logging:**
- LLM call tracing (prompts, responses, latency)
- Tool execution log (arguments, outputs, errors)
- RAG query log (search terms, results, scores)
- Phase transitions & timing
- Cache hit/miss events
- Turn-by-turn session.md file (line-buffered, survives crashes)

**Session Output Example:**
```
Turn 1: Query received
  [PLANNING] ... selected tools: [create_node, safe_set_parameter]
  [RAG] Searched for 'scatter points' → 5 results
  [TOOL] create_node(parent="/obj/geo1", type="scatter")
  [TOOL] safe_set_parameter(node="/obj/geo1/scatter1", parm="npts", value=100)
  [OBSERVE] Geometry now has 100 points
  [CRITIC] Output passes safety checks
Turn 1 completed in 2.3s
```

---

## 8. CONFIGURATION & SAFETY

### 8.1 Core Config (`data/core_config.json`)

**Model Selection:**
- `model`: "gemma4:31b-cloud" (main)
- `vision_model`: "gemma4:31b-cloud"
- `embed_model`: "nomic-embed-text"
- `model_routing`: Per-task overrides (planning, build, debug, vex, semantic, etc.)

**Houdini Integration:**
- `tool_timeout_s`: 90s (scene-mutating ops)
- `read_hou_call_timeout_s`: 30s (read-only ops)
- `fast_write_hou_call_timeout_s`: 90s
- `context_window`: 32768 tokens
- `max_tool_rounds`: 16 rounds per turn

**Safety Gates:**
- `auto_execute_confidence`: 0.7 (require 70%+ confidence to auto-execute)
- `enable_repair_critic`: true (gates risky tool calls)
- `tool_retry_enabled`: true (retry failed tools 3x with backoff)
- `circuit_breaker_threshold`: 4 consecutive LLM failures → abort
- `failure_blacklist_enabled`: true (prevent repeating failed tools)
- `turn_budget_enabled`: true (wall-clock + token limits)

**Knowledge Base:**
- `rag_top_k`: 5
- `rag_hybrid_search`: true
- `rag_max_context_tokens`: 4000
- `prefetch_rag`: true

**UI:**
- `stream_responses`: true
- `show_tool_calls`: true
- `show_llm_trace_history`: true
- `detail_mode`: "simple" (can switch to intermediate/expert)

**Advanced Features:**
- `semantic_scoring_enabled`: true (verify outputs match intent)
- `semantic_multiview_enabled`: false (multi-angle renders — resource intensive)
- `plan_enabled`: true (but gated by query complexity)
- `proxy_generation_enabled`: true (forward-reference resolution)
- `clarification_enabled`: true (ask for ambiguous queries)
- `preconditions_enabled`: true (validate scene state before building)

---

## 9. INTEGRATION PATTERNS

### 9.1 MCP Server Integration

HoudiniMind exposes an MCP server on port 9875, enabling external editors (Cursor, VSCode) to:
- Send prompts to the agent
- Subscribe to tool calls
- Monitor job progress
- Receive streaming responses
- Query knowledge base directly

### 9.2 Tool Validator System

**SafeArgumentCall Pattern:**
```python
# Before execution:
1. Validate arguments against JSON Schema
2. Resolve parameter aliases (fuzzy matching)
3. Type-check vectors, numbers, strings
4. Range validation for parameters
5. Create backup of scene state
# Execute tool
# If error, attempt repair or rollback
```

### 9.3 Error Recovery

**Multi-layer recovery:**
1. **Automatic repair**: LLM attempts to fix tool arguments
2. **Retry with backoff**: 0.4s → 4.0s exponential backoff (3 attempts)
3. **Failure blacklist**: Don't retry same tool/node combo for 12 turns
4. **Circuit breaker**: Stop on 4 consecutive LLM backend failures
5. **Manual intervention**: Fail gracefully with actionable error messages

---

## 10. GAPS & OPPORTUNITIES FOR NEW FEATURES

Based on the comprehensive feature set, here are potential areas for enhancement:

### 10.1 Collaborative Features
- **Multi-user sessions**: Support multiple agents in same scene (requires node locking)
- **Undo/redo integration**: Track agent actions in Houdini undo stack
- **Conflict detection**: Warn when agent modifies nodes user is editing

### 10.2 Advanced Simulation
- **Constraint authoring**: Interactive constraint setup UI
- **Solver parameter auto-tuning**: Machine learning-based CFL/substep optimization
- **Sim data visualization**: Direct rendering of sim data (velocities, forces)

### 10.3 Rendering & Lookdev
- **Interactive material editing**: Real-time material tweaking with live preview
- **Light placement automation**: AI-driven lighting layout
- **Render farm integration**: Distributed render submission & monitoring

### 10.4 Data Management
- **Asset library**: Searchable HDA library with tagging
- **Cache management**: Intelligent geo/sim cache lifecycle
- **Version control**: Scene diff/merge utilities

### 10.5 Knowledge Improvements
- **Auto-learning from mistakes**: Fallback workflow capture
- **Custom recipes**: User-created workflow templates
- **Houdini version-specific docs**: Version-aware knowledge base

### 10.6 Procedural Generation
- **Animation curves**: Keyframe interpolation & animation helpers
- **Geometry synthesis**: ML-based geometry generation
- **Instancing optimization**: Automated packed prim conversion

### 10.7 Advanced Debugging
- **Breakpoint system**: Pause execution at problem nodes
- **Attribute inspector**: Real-time attribute graphing
- **Cook profile visualization**: Network cook timing heatmap

### 10.8 Performance Features
- **Incremental cooking**: Only cook changed nodes
- **GPU acceleration**: Delegate operations to GPU nodes
- **Distributed execution**: Multi-machine TOP support

---

## Summary Table

| Category | Count | Key Tools |
|---|---|---|
| **Node Tools** | 20 | create_node, safe_set_parameter, write_vex_code, set_expression |
| **Chain Tools** | 12 | create_node_chain, promote_parameter, create_network_box |
| **Advanced Tools** | 70+ | convert_to_hda, setup_pyro_sim, setup_karma_material, get_parm_expression_audit |
| **Perf/Org Tools** | 28 | profile_network, suggest_optimization, batch_set_parameters |
| **Inspection Tools** | 8 | analyze_geometry, get_node_parameters, check_geometry_issues |
| **Geometry Tools** | 9 | batch_align_to_support, get_stacking_offset, audit_spatial_layout |
| **Knowledge Tools** | 7 | search_knowledge, explain_node_type, get_vex_snippet |
| **Vision Tools** | 4 | capture_viewport, describe_network_editor |
| **Simulation/PDG** | 15+ | setup_grain_sim, submit_pdg_cook, suggest_node_repairs |
| **UI Components** | 6 | Panel, Backend, State, Layout, Dispatch, Workflows |
| **RAG Shards** | 12 | sop_nodes, dop_nodes, recipes, vex_reference, etc. |

**Total Capabilities:** 70+ tools, 12 RAG shards, 6 UI component mixins, 10+ agent phases/gates

---

Generated: 2026-05-06
Model: Claude Haiku
Context: /Users/anshulvashist/Downloads/HoudiniMind - Copy (2)
