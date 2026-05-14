# Anti-Hardcoding Policy & Architecture Guidelines

## Core Philosophy
The core intelligence of HoudiniMind stems directly from the reasoning capabilities of the Large Language Model (LLM) and the dynamic knowledge provided by the RAG (Retrieval-Augmented Generation) system. 

**Under no circumstances should the agent's logic be constrained, guided, or overridden by rigid hardcoded rules.**

## 1. Zero Hardcoding Rule
- **No Hardcoded Node Types:** Do not write code that says `if user asks for X, create node type Y`. The LLM should decide the best procedural node type (e.g., `rbdmaterialfracture` vs `boolean` shatter) by reasoning about the task and querying the RAG system.
- **No Hardcoded Parameters:** Do not hardcode parameter values, channel names, or exact node paths in the agent's python logic. The LLM must dynamically inspect the scene via tools like `get_node_parameters` and infer what needs to be changed.
- **No Hardcoded Workflows:** Do not write procedural Python backend functions that execute a pre-defined set of nodes for a specific keyword (e.g., "build a table"). The LLM must dynamically plan the build, construct the geometry node-by-node, and evaluate its own work.

## 2. LLM and RAG First
- **Dynamic Reasoning for Verification:** The agent must evaluate network structures semantically. If a user asks to "fracture a geometry", the agent must not blindly check a hardcoded list for an `rbdmaterialfracture` node string. Instead, it must structurally review the network via the LLM to determine if the *intent* of the task was successfully achieved, regardless of the node names used.
- **Knowledge Retrieval:** All domain-specific Houdini knowledge (node names, VEX snippets, Python API quirks) must come from the RAG database or the agent's baseline intelligence, never from hardcoded mapping dictionaries hidden in the Python backend. 

## 3. Developer & Agent Guidelines
Whenever the agent (or a human developer) modifies this repository:
- **AVOID** adding `if/elif` chains that trigger on specific user prompts.
- **AVOID** maintaining lists of "required node strings" or "forbidden nodes" for specific validation tasks.
- **DO** build flexible, generic wrappers that pass raw context (like scene topology and node properties) directly to the LLM.
- **DO** empower the LLM. Trust the model to solve Houdini problems procedurally using its reasoning engine. 

By keeping the architecture free of brittle heuristics, we ensure the agent remains intelligent, adaptable, and robust against version changes in Houdini.
