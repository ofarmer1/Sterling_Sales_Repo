# Fixes for Codex's review (Oct 6, 2026)

All changes have regression tests in `tests/test_codex_regressions.py`.
Full suite: 118 passed (fake AI and fake database; still no live OpenAI run).

| Problem Codex reproduced | Fix | Where |
|---|---|---|
| Retry skipped a company whose research worked but drafting failed, leaving it with no drafts | Batches now write missing drafts for researched companies without researching again. "Retry failed or missing drafts" includes these companies. | `batch.py` (`needs_drafts`, `needs_retry`), `find_view.py` |
| Revenue or sales team with only one known end was treated as exact | One-sided figures are open-ended: "at least $10M" is unknown for $1M to $30M, but "at least $40M" is still outside. | `qualification.py` `check_range`, `_describe` |
| An estimated non-tech classification became a firm rejection | Only a verified industry outside the preferences can reject. Estimates give "Needs review". | `qualification.py` `check_industry` |
| Changing preferred industries still checked "tech/software" | Matches the Settings industries as whole words against the researched industry and product. A "yes, tech" answer counts only when a tech-type term is preferred. The research and discovery prompts include the preferred industries. No preferred industries gives unknown, never a pass. | `qualification.py`, `research.py`, `discovery.py`, `settings_view.py` (label) |
| A failed research refresh removed "approved" status | If a company already has research, a failed refresh keeps its status and old research and only records the error. A company's first failed research is still marked "research failed". | `leads_store.py` `save_research_failure` |
| Source checks only prove the URL appeared in search, not that it supports the claim | Facts are now labelled "cited" (not "verified") in the app and the export, with a note to open the link before relying on it. | `leads_view.py`, `export.py`, `research.py` docstring, `docs/data-and-reliability.md` |

Still open (unchanged): live OpenAI research untested, mailbox draft saving
not built, hosting not tested. Next is one real company end to end, once the
OpenAI key is in.
