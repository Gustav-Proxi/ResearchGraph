# Agentic Blueprint

This project’s agentic layer is informed by the taxonomy in:

- Yuanchen Bei et al., *Graphs Meet AI Agents: Taxonomy, Progress, and Future Opportunities*, arXiv:2506.18019, submitted June 22, 2025 and revised July 4, 2025.

Paper link:

- https://arxiv.org/abs/2506.18019

## Taxonomy adopted

The paper organizes graph-empowered agents around four core functions:

1. planning
2. execution
3. memory
4. multi-agent coordination

ResearchGraph turns those into first-class system facets:

- `facet-planning`
- `facet-execution`
- `facet-memory`
- `facet-coordination`

## Future-opportunity directions adopted

The paper also highlights several forward-looking areas. ResearchGraph currently encodes three of them:

- graph foundation models
- Model Context Protocol (MCP)
- open agent networks

These appear as:

- `tech-gfm`
- `tech-mcp`
- `tech-oan`

## Where ResearchGraph is intentionally different

The paper is a survey. ResearchGraph is trying to become an operating system for research workflows, so it adds system-level objects the survey does not specify:

- `Reflexive Graph Memory`
  Stores failures, weak evidence chains, and reusable reasoning traces as graph memory.

- `Topology-Adaptive Agent Router`
  Treats communication layout as an optimization target, not a fixed chain or tree.

- `MCP-Native Context Graph`
  Unifies papers, tools, artifacts, and memory into one protocol-queryable context plane.

- `TurboQuant`
  A heuristic ranking layer that scores papers, graph nodes, and novelty opportunities using overlap and graph structure.

- `Experiment Graph`
  Treats baselines, ablations, and metrics as explicit graph structure rather than loose logs.

- `Report Graph`
  Treats report generation as a grounded dependency graph across evidence, planning, execution, and novelty.

## Resulting system picture

In ResearchGraph:

- papers form an evidence graph
- agents form a workflow graph
- experiments form an execution graph
- report sections form a writing graph
- technologies form a capability graph
- taxonomy facets form an agentic graph
- novelty hypotheses attach to the agentic graph

This gives the project a concrete path to evolve into:

- graph-grounded planning
- graph-native memory
- topology-aware multi-agent orchestration
- protocol-aware tool and data routing
