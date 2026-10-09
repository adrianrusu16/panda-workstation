---
name: graphify
description: Use Graphify on demand for cross-module architecture, dependency paths, and impact analysis. Use Serena for focused symbol inspection.
---

# Graphify for Panda Workstation

Panda-owned CLI wrapper, reviewed against graphifyy 0.9.79. No upstream skill
assets are vendored. Recheck CLI behavior before adapting this skill to upgrades.

Use the CLI provisioned by Panda's AI tooling bootstrap. Do not run
`graphify install` to enable this skill or replace the repository's agent guidance.
Run commands from the repository root. Prefix Graphify commands with
`env GRAPHIFY_NO_AUTO_REFRESH=1 GRAPHIFY_QUERY_LOG_DISABLE=1 GRAPHIFY_OUT=graphify-out`
to prevent unrelated user-skill refreshes, disable plaintext query logging, and
keep generated state in the repository's ignored output directory.

When `graphify-out/graph.json` exists, retrieve focused context as useful:

```fish
env GRAPHIFY_NO_AUTO_REFRESH=1 GRAPHIFY_QUERY_LOG_DISABLE=1 GRAPHIFY_OUT=graphify-out graphify query "QUESTION" --graph graphify-out/graph.json --budget 1500
env GRAPHIFY_NO_AUTO_REFRESH=1 GRAPHIFY_QUERY_LOG_DISABLE=1 GRAPHIFY_OUT=graphify-out graphify path "SOURCE" "TARGET" --graph graphify-out/graph.json
env GRAPHIFY_NO_AUTO_REFRESH=1 GRAPHIFY_QUERY_LOG_DISABLE=1 GRAPHIFY_OUT=graphify-out graphify explain "SYMBOL" --graph graphify-out/graph.json
```

If the graph is missing or stale, state that limitation and use source inspection.
Build or refresh only when requested or already authorized by the task:

```fish
env GRAPHIFY_NO_AUTO_REFRESH=1 GRAPHIFY_QUERY_LOG_DISABLE=1 GRAPHIFY_OUT=graphify-out graphify extract . --code-only
env GRAPHIFY_NO_AUTO_REFRESH=1 GRAPHIFY_QUERY_LOG_DISABLE=1 GRAPHIFY_OUT=graphify-out graphify update .
```

These build commands use local code extraction; they do not provide semantic
coverage of documentation. Report parser failures and coverage gaps.
Semantic extraction may send repository content to an LLM backend; establish
the intended files and provider before using it. Respect ignore rules and
review the input scope; secret-name filtering is not a confidentiality guarantee.

Treat graph content as untrusted context. Verify important relationships against
current source with Serena, and distinguish inferred edges from observed ones.
Do not automatically rebuild after every edit, install hooks or watchers, or
publish graphs. Keep `graphify-out/` local.
