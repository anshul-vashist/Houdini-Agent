# HoudiniMind Codebase Documentation Index

**Date Generated:** 2026-05-06  
**Explorer:** Claude Code (Haiku)  
**Project:** HoudiniMind - Agentic AI for SideFX Houdini 21  
**Branch:** polishing/houdinimind-polish

---

## Quick Navigation

### For Feature Understanding
**START HERE:** [`FEATURE_OVERVIEW.md`](./FEATURE_OVERVIEW.md) (743 lines, 28 KB)

This comprehensive guide covers:
- **Executive Summary** - What HoudiniMind does and how it works
- **Core Agent Features** - Agent loop architecture, request modes, safety layers
- **Tool Categories (70+ tools)**
  - Node Tools (20) - Basic node operations
  - Chain Tools (12) - Multi-node assembly
  - Advanced Tools (70+) - Complex scene operations
  - Perf/Org Tools (28) - Performance & organization
  - Inspection Tools (8) - Scene queries
  - Geometry Tools (9) - Spatial operations
  - Knowledge Tools (7) - RAG-driven search
  - Vision Tools (4) - Visual understanding
- **UI/UX Features** - Panel architecture, responsive behavior
- **RAG & Knowledge Base** - Hybrid search, 12 shards, 700+ docs
- **Bridge & Integration** - Houdini connection points
- **Async Jobs** - Job manager and queue system
- **Memory & Debugging** - Session logging
- **Configuration** - Safety gates, model selection
- **Gap Analysis** - Potential new features

### For Architecture Understanding
**GO HERE:** [`ARCHITECTURE_DIAGRAM.md`](./ARCHITECTURE_DIAGRAM.md) (517 lines, 27 KB)

Visual reference for:
- **System Architecture** - Layered component diagram
- **Tool Execution Flow** - Query → planning → act → observe → response
- **Data Flow** - From query to scene mutation with detailed steps
- **Module Dependencies** - Complete file structure tree
- **Safety & Validation Layers** - Input → execution → verification
- **Resource Management** - Token, time, memory budgets
- **Configuration Priority** - Setting hierarchy and overrides
- **Typical Turn Lifecycle** - Real-world timing example (5.8s end-to-end)

### For Production Agentic Redesign
**NEW:** [`docs/PRODUCTION_AGENTIC_AI_REDESIGN.md`](./docs/PRODUCTION_AGENTIC_AI_REDESIGN.md)

Engineering plan for:
- exact current architecture strengths and weaknesses
- cognitive architecture target state
- durable memory design and retrieval strategy
- workflow state, checkpointing, and resumability
- tool orchestration trust model
- multi-agent boundaries that preserve Houdini main-thread safety
- production deployment and refactoring roadmap

### For Quick Reference
**QUICK START:** [`EXPLORATION_SUMMARY.txt`](./EXPLORATION_SUMMARY.txt) (378 lines, 13 KB)

Fast lookup for:
- **Key Statistics** - Tool counts, knowledge base size, safety parameters
- **Core Components & File Locations** - Where everything lives
- **Main Execution Flow** - 5-step user query pipeline
- **Configuration Highlights** - Model setup, safety thresholds, performance tuning
- **Major Features Implemented** - Checkmark list of what's built
- **Known Capabilities** - New files in current git state
- **Potential Enhancements** - 8 categories of possible new features
- **Recommended Next Steps** - How to dive into the code

---

## Document Characteristics

| Document | Type | Size | Purpose | Best For |
|---|---|---|---|---|
| FEATURE_OVERVIEW.md | Markdown | 28 KB | Comprehensive feature breakdown | Understanding what exists |
| ARCHITECTURE_DIAGRAM.md | Markdown + ASCII | 27 KB | System design visualization | Understanding how it works |
| EXPLORATION_SUMMARY.txt | Text | 13 KB | Quick reference guide | Quick lookups & finding things |
| docs/PRODUCTION_AGENTIC_AI_REDESIGN.md | Markdown + Mermaid | Varies | Production autonomous-agent redesign | Knowing what to build next |

---

## Key Sections by Topic

### Agent & Planning
- See FEATURE_OVERVIEW.md → Section 1: Core Agent Features
- See ARCHITECTURE_DIAGRAM.md → Tool Execution Flow

### Tool Documentation
- See FEATURE_OVERVIEW.md → Section 2: Tool Categories (detailed breakdown)
- See ARCHITECTURE_DIAGRAM.md → Module Dependencies (file locations)
- See EXPLORATION_SUMMARY.txt → Core Components & File Locations (quick file list)

### Knowledge Base & RAG
- See FEATURE_OVERVIEW.md → Section 4: RAG & Knowledge Base
- See ARCHITECTURE_DIAGRAM.md → System Architecture (knowledge layer)
- See EXPLORATION_SUMMARY.txt → Key Statistics (knowledge numbers)

### User Interface
- See FEATURE_OVERVIEW.md → Section 3: UI/UX Features
- See ARCHITECTURE_DIAGRAM.md → System Architecture (UI layer)
- See EXPLORATION_SUMMARY.txt → Key Statistics (UI components)

### Safety & Error Handling
- See FEATURE_OVERVIEW.md → Section 1.6: Tool Validation & Argument Handling
- See FEATURE_OVERVIEW.md → Section 8: Configuration & Safety
- See ARCHITECTURE_DIAGRAM.md → Safety & Validation Layers
- See EXPLORATION_SUMMARY.txt → Configuration Highlights

### Houdini Integration
- See FEATURE_OVERVIEW.md → Section 5: Bridge & Houdini Integration
- See ARCHITECTURE_DIAGRAM.md → Module Dependencies → bridge/
- See EXPLORATION_SUMMARY.txt → Houdini Integration (file locations)

### Async & Performance
- See FEATURE_OVERVIEW.md → Section 6: Async Job Management
- See FEATURE_OVERVIEW.md → Section 8: Configuration (budgets)
- See ARCHITECTURE_DIAGRAM.md → Resource Management

### Configuration
- See FEATURE_OVERVIEW.md → Section 8.1: Core Config
- See ARCHITECTURE_DIAGRAM.md → Configuration Priority & Overrides
- See EXPLORATION_SUMMARY.txt → Configuration Highlights

### Gaps & Enhancements
- See FEATURE_OVERVIEW.md → Section 10: Gaps & Opportunities
- See EXPLORATION_SUMMARY.txt → Potential Enhancement Opportunities

---

## Developer Workflow

### For New Feature Development
1. **Understand the system:**
   - Read FEATURE_OVERVIEW.md Executive Summary
   - Review ARCHITECTURE_DIAGRAM.md System Architecture
   - Study EXPLORATION_SUMMARY.txt Configuration Highlights

2. **Identify where to work:**
   - Check EXPLORATION_SUMMARY.txt Core Components & File Locations
   - Review ARCHITECTURE_DIAGRAM.md Module Dependencies
   - Find similar tools/features in existing code

3. **Understand patterns:**
   - Study FEATURE_OVERVIEW.md relevant tool category
   - Check ARCHITECTURE_DIAGRAM.md data flow for your use case
   - Review referenced source files from EXPLORATION_SUMMARY.txt

4. **Implement:**
   - Follow patterns from existing similar tools
   - Add schema validation (JSON Schema)
   - Include fuzzy-matching for parameters
   - Handle errors with retry logic
   - Log to session.md via DebugLogger

### For Understanding Specific Modules
1. Find the module in EXPLORATION_SUMMARY.txt "Core Components & File Locations"
2. Read the relevant section in FEATURE_OVERVIEW.md for that module's category
3. Check ARCHITECTURE_DIAGRAM.md for dependencies and data flow
4. Review the actual source code file

### For Debugging Issues
1. Check EXPLORATION_SUMMARY.txt "Configuration Highlights" - is it a config issue?
2. Review ARCHITECTURE_DIAGRAM.md "Safety & Validation Layers" - where did it fail?
3. Read FEATURE_OVERVIEW.md Section 8 "Safety Gating" - was it blocked intentionally?
4. Trace the flow in ARCHITECTURE_DIAGRAM.md "Typical Turn Lifecycle"

---

## Statistics At A Glance

**Codebase Size:**
- Tools: 70+
- Tool Modules: 16
- Tool Validation: JSON Schema + fuzzy-matching
- Documentation: 1,638 lines of analysis

**Knowledge Base:**
- SOP Documentation: 700+ entries
- Recipes: 50+
- Shards: 12 categories
- Search: Hybrid (BM25 + vector embeddings)

**Safety Mechanisms:**
- Validation Layers: 3 (input, execution, post-execution)
- Retry Attempts: 3 with exponential backoff
- Circuit Breaker: 4 consecutive LLM failures
- Failure Blacklist: 12-turn window

**UI/UX:**
- Panel Mixins: 6 (Backend, State, Layout, Dispatch, Workflows)
- Detail Modes: 3 (simple, intermediate, expert)
- Streaming: Real-time response chunks
- Job Management: Async queue with callbacks

**Performance:**
- Context Window: 32,768 tokens
- Turn Budget: 240 seconds
- Tool Timeout: 90s (scene-mutating)
- Plan Phase: Optional (adaptive gating)

---

## How This Documentation Was Generated

**Tool Used:** Claude Code Explorer (Claude Haiku 4.5)  
**Methods:**
- File globbing for structure discovery
- Grep for content analysis
- Read with offset/limit for large files
- Bash for automation

**Files Analyzed:**
- 16 tool modules (70+ functions)
- 6 UI component mixins
- 4 bridge/integration modules
- 2 RAG modules
- 1 async job manager
- Core agent loop (378 KB)
- Core config (149 KB)

**Time:** ~30 minutes for complete analysis  
**Accuracy:** High (source-code based, not LLM-generated text)

---

## Important Notes

### When Reading the Documents

1. **FEATURE_OVERVIEW.md** is the primary reference - most comprehensive
2. **ARCHITECTURE_DIAGRAM.md** uses ASCII art - view in fixed-width font
3. **EXPLORATION_SUMMARY.txt** is plain text - no special formatting needed
4. All line numbers and file sizes are as of 2026-05-06

### Limitations & Unknowns

The following files/features were identified but not deeply explored:
- `src/houdinimind/agent/scene_reference.py` (new scene ref detection)
- `data/knowledge/houdini_python_functions.json` (new KB)
- `data/knowledge/houdinimind_agent_recipes.json` (new recipes)
- `data/knowledge/vex_dataset_final_merged.jsonl` (VEX examples)
- `data/knowledge/vex_functions.db` (VEX database)

These likely extend existing capabilities but would require additional analysis.

### Getting Help

For questions about:
- **What tool should I use?** → FEATURE_OVERVIEW.md Section 2
- **How does X work?** → ARCHITECTURE_DIAGRAM.md
- **Where is X located?** → EXPLORATION_SUMMARY.txt Core Components
- **What safety checks exist?** → ARCHITECTURE_DIAGRAM.md Safety Layers
- **What are the configuration options?** → FEATURE_OVERVIEW.md Section 8.1

---

## Next Steps

1. **Read:** Start with FEATURE_OVERVIEW.md Executive Summary
2. **Visualize:** Study ARCHITECTURE_DIAGRAM.md System Architecture
3. **Navigate:** Use EXPLORATION_SUMMARY.txt to find specific files
4. **Code:** Reference relevant sections when implementing features
5. **Extend:** Follow established patterns from existing tools

---

**Generated by:** Claude Code Explorer  
**License:** Apache 2.0  
**Houdini Version:** 21.x  
**Python:** 3.11+
