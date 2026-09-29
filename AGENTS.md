# AGENTS.md - kgi-interop-monitor

## Project Overview

kgi-interop-monitor is a [nicescholia](https://github.com/WolfgangFahl/nicescholia)
based dashboard for the SPARQL endpoints of the
[KGI4NFDI](https://base4nfdi.de/projects/kgi4nfdi) registry. The page is
nicescholia's own - header, menu, footer, the endpoint grid with its columns and
its colour legend. This repository supplies the endpoint list.

- **GitHub**: https://github.com/KGI4NFDI/kgi-interop-monitor
- **Upstream**: [nicescholia](https://github.com/WolfgangFahl/nicescholia) - the
  dashboard, its widgets and its endpoint model all come from there
- **Upstream wiki**: https://wiki.bitplan.com/index.php/nicescholia
- **Agent rules**: `Agent/Guido/BITPlan` on BITPlan's media wiki - the canonical
  BITPlan Python conventions. media.bitplan.com does not resolve publicly
  (checked 2026-09-29), so the conventions this project follows are written out
  under [Conventions](#conventions) below.

## Boot

Agents working in this repository perform the mandatory boot sequence of the
`Agents` page on BITPlan's media wiki (wikipush wiki id `media`, not publicly
reachable): PLAN-AND-ASK, Document-First, DMAIC histogram, English-only.

**PLAN-AND-ASK is not optional here.** The scope of this project is agreed with
the maintainers before code is written; an agent that produces features which
were not asked for has failed, however good the code is. Put the plan in an
issue, get it agreed, then implement.

## Scope

Reduced feature set, in nicescholia's style. Start from nicescholia's endpoint
dashboard columns and add nothing that has not been agreed. Anything else
belongs in an issue first.

## Provenance

Agent-written content that makes a claim - an issue comment, a measurement, a
design note - carries the BITPlan provenance markers:

| marker | meaning |
|--------|---------|
| `✍️🤖 Agent/<name>` | written by the agent |
| `🗣️ <human> → 🤖 Agent/<name>` | said by the human, transcribed by the agent |
| `👁️🧑 <human> ✓` | read and approved by the human before posting |

Generated code is reviewed before it is merged; the `👁️🧑 ✓` marker is what
says a human stood behind it.

## Commands

| Command | Purpose |
|---------|---------|
| `scripts/install` | pip install . |
| `scripts/test` | run the unittest suite |
| `scripts/blackisort` | format code with isort + black - always before commit |
| `scripts/doc` | build API documentation |
| `scripts/release` | build and deploy the documentation, then commit and push |

## Project Structure

| Path | Purpose |
|------|---------|
| `src/kgi_interop_monitor/nicekgi.py` | `KgiWebserver` / `KgiSolution` / `Endpoints` - the NiceGUI page and the endpoint list |
| `src/kgi_interop_monitor/cmd.py` | `KgiCmd` command line entry point |
| `src/kgi_interop_monitor/__init__.py` | `__version__` - single source of the version |
| `tests/` | unittest based tests (`ngwidgets.webserver_test.WebserverTest`) |

`Endpoints.get_endpoints` is the whole customization surface: one
`lodstorage.query.Endpoint` per registry record, keyed by a short id.

## Conventions

- Build backend: **hatchling**; version lives in `src/kgi_interop_monitor/__init__.py` (`__version__`)
- Tests: **unittest** with `ngwidgets.webserver_test.WebserverTest`; no pytest
  fixtures, no conftest.py
- Formatting: black (88 cols) + isort via `scripts/blackisort`; no ruff/flake8/mypy
- Docstrings: Google style; module headers with creation date and `@author`
- Type hints on all public signatures; `Optional[X]` not `X | None`
- Named return variables; top-level imports only
- Dependencies: the nicescholia / ngwidgets / pyLoDStorage ecosystem - justify any
  new dependency. Prefer using what nicescholia already provides over
  reimplementing it here.
