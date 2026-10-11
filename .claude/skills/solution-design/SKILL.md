---
name: solution-design
description: Draft a design for an open technical question as an iacs requirement/solution tree, commit it into the target project's own manifest, and publish it as an artifact for the user's sign-off. Use whenever the user asks to "design", "draft a design", or work through a design decision for a GitHub issue/epic checklist item -- not for implementation work itself, only the decision-making step that precedes it.
---

# Solution design process

A repeatable way to work through an open design question (a GitHub issue's
"design:" checklist item, an ambiguous architecture decision, a choice
between competing implementations) so the reasoning itself -- not just the
eventual code -- is captured, reviewable, and reusable.

## Steps

1. **Research first, summarize before drafting.** Read the actual code,
   git history (`git log`/`git show` on the commits that shaped current
   behavior, not just the current diff), and any linked issues/docs before
   writing a single line of design. Give the user a succinct written
   summary of what you found and confirm you're solving the right problem
   before moving to step 2 -- don't skip straight to solutioning.

2. **Draft the design as a requirement/solution tree**, using the target
   project's own iacs/emc2p vocabulary (`requirement`/`requirement_priority`,
   `solution`/`solution of`, `selected: true`, `pro:`/`con:` bare tags,
   `work_state`). Match the conventions already used in that project's own
   manifest file (e.g. `docs/manifest/<project>.yaml`) rather than inventing
   a new shape -- read a few existing entries there first. Structure:
   - One root requirement per open design question.
   - Nested sub-requirements for each distinct decision the question breaks
     into.
   - Candidate solutions under each requirement, each with `pro`/`con`
     points -- not just the winning option, so a rejected alternative and
     *why* it lost stays visible, not silently dropped.
   - Exactly one `selected: true` solution per requirement (or none, if the
     question is being raised but not yet decided).
   - `work_state: new` on every candidate until the user signs off (see
     Definition of done below) -- selection is a draft opinion, not a
     commitment, until then.

3. **Commit the tree into the project's repo immediately**, in its own
   manifest file, following that repo's own "commit immediately, don't
   batch" convention. Commit message should say plainly that this is a
   draft awaiting sign-off, not a finished decision.

4. **Publish a solution document as an artifact** rendering the same tree
   for human review: the question, each requirement, selected vs. rejected
   solutions with their pro/con points, and an explicit bottom-line
   recommendation. This is the actual review surface -- the YAML is the
   durable record, the artifact is what the user reads to decide.

## Definition of done

**The design is not finished when the tree is committed or the artifact is
published -- only when the user explicitly signs off on the solution
document.** Committing the draft and publishing the artifact are how the
design gets *in front of* the user for review, not evidence that review
happened. Concretely:

- Don't treat `selected: true` entries as settled, don't start implementation
  work that depends on the decision, and don't advance `work_state` past
  `new`, until the user has said so explicitly (approval, requested changes,
  or "needs another pass" -- any of these counts as a real response; silence
  or moving on to another topic does not).
- If the user asks for changes, revise the tree and the artifact and
  re-commit/re-publish (same file paths -- redeploy in place, don't create a
  new artifact) rather than starting a fresh round from scratch.
- Once approved, say so plainly and update the artifact/manifest entry to
  reflect that (e.g. drop the "awaiting sign-off" status, note the approval)
  before treating any dependent checklist item as unblocked.
