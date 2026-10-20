# Offline Portfolio Demo

This directory contains a zero-dependency viewer for **recorded, sanitized** Agent traces.

The interface provides scenario switching, expandable tool-call details, real recorded dispatch-source and latency fields, Claim-to-Evidence highlighting, reliability/status boundaries, a benchmark panel and a copyable sanitized trace summary.

```powershell
python demo/app.py
```

Open `http://127.0.0.1:8765`. The server binds to localhost by default. It does not construct the Tool Registry, read the 26 GB dataset, load a model, or call DeepSeek.

For a terminal-only replay:

```powershell
python -m tomato_fertigation_agent.portfolio_demo list
python -m tomato_fertigation_agent.portfolio_demo show comprehensive
python -m tomato_fertigation_agent.portfolio_demo check
```

## Execution modes

| Mode | What runs | Data leaves the machine? |
|---|---|---:|
| Recorded Replay | Sanitized JSON only | No |
| Local Agent | Existing tools, models, RAG and case memory | No, unless an external provider is enabled |
| DeepSeek Online | Real provider plus bounded tool-calling loop | Yes; explicit configuration and consent required |

The included UI implements only Recorded Replay. See the root README for Local Agent and Online commands.

## GitHub Pages

The Pages workflow publishes only this directory. The site is static: it cannot store a provider key, execute Python tools, or call DeepSeek. Repository Pages must be enabled with **GitHub Actions** as its source after the first public push.
