---
name: review-triage
description: >-
  Runs a structured, four-phase review workflow (notate, clarify,
  investigate, implement) for processing a batch of feedback on a PR, diff,
  design doc, or any other body of work, using the task tracker
  (TaskCreate/TaskList/TaskUpdate/TaskGet) to hold each item as it moves
  through the pipeline. Use this whenever the user is about to review
  something and narrate reactions one at a time (phrases like "let's go
  through this PR", "I'm going to respond to these point by point", "I'll
  give you my comments as I read"), or explicitly invokes it as
  /review-triage. The defining trait to watch for is the user reacting to a
  series of items and wanting each one tracked and addressed systematically,
  not answered inline as they go. Do not silently start implementing fixes
  as soon as a reaction sounds like an obvious fix, since that defeats the
  whole point of this skill.
---

# Review triage

A structured way to process a batch of feedback -- PR review comments, reactions
to a diff, notes on a design doc, or a user's live narration of what they think
of some body of work -- without losing items, without debating them one at a
time in isolation, and without jumping to code before the full picture is
clear.

## Why this exists

When someone is reviewing something substantial, their first reaction to any
one point is rarely their final word on it. A comment that sounds like a
one-line fix sometimes turns out to be a symptom of something bigger once two
or three more comments come in. A comment that sounds like an open question
sometimes has an answer sitting in the code already. Racing to fix each item
the moment it's raised throws away the chance to notice these connections --
and worse, it means acting on a decision before the reviewer has actually
finished deciding.

This skill separates four kinds of work that are easy to blur together:
capturing what was said, agreeing on what it means, finding out what's true,
and changing something. Doing them out of order is the single biggest way
review sessions go sideways -- an "obvious" fix implemented in phase 1 that
gets contradicted by phase 3's investigation is wasted work and a harder
conversation than if it had just waited.

## The four phases

Work through these in order. They can loop back on each other (see "Phases
aren't strictly sequential" below), but never skip ahead to IMPLEMENT for an
item that hasn't been through CLARIFY and, if needed, INVESTIGATE.

### Phase 1 -- NOTATE

The user narrates their reactions to whatever they're reviewing, one at a
time. Your job here is purely to **capture**, not to act or even to fully
resolve ambiguity yet.

For each reaction:
1. Create a task with `TaskCreate` whose description captures the substance
   of what they said -- in enough detail that you (or a future session) could
   pick it back up cold, without needing to re-read this conversation.
2. If what they said reveals a design fork, a half-finished thought, or an
   open question even as they're saying it, capture that nuance in the task
   description too. Don't quietly resolve it in your own head and record only
   the resolution -- record the fork itself if it's still open.
3. Confirm briefly (a task number and a one-line label is enough) and move on.

Do **not**, in this phase:
- Start editing files, even for a one-line change that seems obviously right.
- Ask clarifying questions unless you genuinely cannot record the task at all
  without one -- most clarification belongs in phase 2, not interleaved into
  every single item.
- Skip recording something because you think you already know how it'll be
  resolved. Your job is to write down what they said, not what you predict
  they'll conclude.

If the user is narrating quickly (e.g. dictating through a list), keep your
responses to a task number and short label per item -- don't editorialize on
each one. Save substantive engagement for phase 2.

### Phase 2 -- CLARIFY

Once the user signals they're done narrating for now -- or you sense a natural
pause -- show the current task list back (`TaskList`) so both of you can see
the whole picture at once.

From there, work through ambiguity together:
- If a task is vague or could mean two different things, ask what's needed --
  concretely, referencing the specific fork, not a generic "can you clarify?"
- If one narrated reaction actually contains several distinct action items,
  split it into separate tasks (`TaskCreate` for the new ones, update or
  delete the original).
- If two tasks turn out to be the same concern from two angles, merge them
  (fold one's content into the other via `TaskUpdate`, delete the redundant
  one).
- If the user directly answers a question inline while narrating (this
  happens naturally and is fine), record that resolution in the task via
  `TaskUpdate` rather than leaving the original ambiguous text sitting there.

This phase and phase 1 interleave freely in practice -- a user often narrates
a few more reactions, circles back to clarify an earlier one, then keeps
going. That's expected. What matters is that by the time you leave this phase
for a given task, either its meaning is settled or it's been explicitly
flagged as needing investigation (phase 3).

### Phase 3 -- INVESTIGATE

Some tasks aren't fixes waiting to be applied -- they're questions. "Is this
actually true?" "Does something like this already exist somewhere?" "Why is
this happening?" These need real investigation before anyone, including you,
should propose what to do about them.

For each task that's genuinely an open question:
1. Actually go find out -- read the relevant code, run something, check
   history, reproduce the behavior. Don't reason from assumptions about what
   the codebase probably does; check.
2. Record what you found in the task (`TaskUpdate`), concisely, with enough
   specifics (file paths, line numbers, exact behavior observed) that the
   finding is verifiable, not just asserted.
3. If you have a clear recommendation, state it plainly as a recommendation --
   but if the question is a genuine design decision with real tradeoffs (a
   choice between architectures, anything touching a shared API other code
   depends on, anything hard to reverse), surface it as a question for the
   user rather than deciding it yourself. The line to watch for: "I found the
   facts, here's what I'd do" is fine; "I decided this for you" on something
   that was genuinely theirs to decide is not.
4. A task only graduates out of this phase once its open question has an
   answer -- either a settled fact, or an explicit decision from the user.

It's fine for a task to bounce between phase 2 and phase 3 -- clarifying a
question sometimes reveals it needs investigation, and investigation findings
sometimes need the user's input to interpret.

### Phase 4 -- IMPLEMENT

By this point every remaining task should be a clear implementation item --
either it always was, or clarification/investigation turned it into one. Now
work through them.

**Two gates before writing or editing anything for a task, no exceptions:**

- **Explicit per-task go-ahead.** A task's design being fully settled (clarify
  and investigate both closed) is not the same as being authorized to build
  it. Don't start Phase 4 work for a task -- not even one that looks small or
  obviously correct -- until the user has said something that actually means
  "go" for that task specifically (or for a batch that clearly includes it,
  e.g. "implement everything that's ready"). Adding a task to the queue (see
  "The task queue" below) counts as this go-ahead -- naming a task for the
  queue already is the user's "go," however far through the remaining phases
  it needs to travel to get there. A settled design sitting in
  CLARIFY/INVESTIGATE limbo and not queued is a normal, stable state, not an
  oversight to fix by starting the build yourself. This was learned the hard
  way: mid-investigation on one task, the assistant slid into re-implementing
  a design decision without pausing to ask, duplicating work that already
  existed elsewhere -- see the next gate.
- **Duplicate-work check.** Before implementing, check whether the work (or
  something covering the same ground) already exists somewhere you haven't
  looked yet -- an open PR, another branch, a prior session's already-applied
  change -- rather than assuming "not present on my current branch/file"
  means "not done yet." A quick search (open PRs on the relevant repo,
  `git log --all`, asking the user "has this been started elsewhere?") is
  cheap; redoing real work, or worse, landing a second copy of it, is not.
  This applies even -- especially -- when a task's own history says it was
  already completed once: a task marked `completed` can still be wrong, and
  is worth a fast sanity check before treating its state as ground truth if
  something about it seems off.

For each task, once both gates are cleared:
1. Mark it `in_progress` if you're tracking that state, and do the work.
2. Verify before marking `completed` -- run the tests, check the behavior,
   confirm the fix actually holds. "I made the edit" is not the same as
   "I verified it's done." A task with failing tests or an unconfirmed fix
   stays open, with the blocker noted.
3. Some tasks legitimately resolve to "no change needed" -- record the
   reasoning in the task description and mark it completed. That's a valid
   outcome, not a cop-out, as long as the reasoning is real.
4. If implementing one task reveals a new issue, don't just fix it silently --
   create a new task for it (even mid-implementation) so it's visible, then
   decide whether it needs to go back through clarify/investigate or can be
   implemented immediately as part of the same fix.
5. When you finish a batch, show the task list again so the user can see
   what's done, what's still open, and why.

## The task queue

The task list (`TaskList`) is the whole backlog -- everything ever notated,
whatever phase it's actually in. The queue is a narrower, separate thing:
which tasks you should be actively driving forward *right now*, as opposed
to sitting settled (or half-settled) and waiting, which is most of them,
most of the time.

Queue membership is plain task metadata, nothing more -- deliberately not a
second phase-tracking field alongside the tracker's own `status`
(`pending`/`in_progress`/`completed`), which already says enough. Mark it
via `TaskUpdate`'s `metadata` with `queued: true`; clear it (`queued: null`)
once the task reaches `completed`, or if the user explicitly pulls it back
out of active work.

**Adding to the queue.** The user names a task and says to queue it -- "add
task 45 to the queue" is enough on its own; there's no separate stage to
specify. This is also where Phase 4's "explicit per-task go-ahead" gate gets
satisfied: naming a task for the queue already is the user's "go" for it,
however far through the remaining phases it needs to travel to get there,
implementation included.

**Working the queue is its own explicit step, separate from queuing.** Being
in the queue does not by itself mean act now -- most of a session is spent
narrating, clarifying, and investigating without ever touching what's
queued. Only start actually advancing queued tasks (moving each to
`status: in_progress` while you work it -- whatever its next phase is --
and pausing to ask if a genuine ambiguity or an unmet gate blocks it) when
the user explicitly says something like "work the queue" or "process the
queue." That instruction is the mode switch this exists for: narrating/
notating versus actually doing the labor-intensive work of driving tasks
forward.

## Phases aren't strictly sequential

In a real session this looks less like four clean stages and more like a
conversation that keeps returning to the task list as its shared source of
truth. The ordering that matters isn't "finish phase 1 entirely before
starting phase 2" -- it's per-task: no task skips from a raw, unclarified
reaction straight to code changes. The task list itself (via `TaskList`) is
what keeps everyone oriented about where each item actually is, especially
across a long session or one that gets interrupted and resumed.

## Getting started

When this skill is invoked, check `TaskList` first -- there may already be
relevant tasks from earlier in the session worth continuing rather than
starting fresh. Then tell the user briefly that you're ready for phase 1 and
invite them to start narrating, rather than assuming silently. Don't start
working anything sitting in the queue on your own initiative, even if items
are already marked `queued` from earlier -- wait for the explicit "work the
queue" instruction described above.
