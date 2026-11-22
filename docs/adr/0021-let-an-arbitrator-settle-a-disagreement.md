# 0021. Let an arbitrator settle a disagreement between an author and a reviewer

- Status: proposed
- Date: 2026-11-22

## Context

A work stops and asks a person in four places: the spec approval, a failed step, the merge, and a **deadlock**: a reviewer and
its author that cannot settle (`ESCALATE`, a point that came back, or a loop that used its rounds). ADR 0013 lets the person
choose to go on past a deadlock of the two document reviews, with the open points posted on the pull request. Going on is not
settling: the point is still open, and the code review and the checks can never be passed.

Three works on a Spring test repository showed what a deadlock costs in practice:

- Work a797ac5d9579: the reviewer asked twice for a one-line reference fix in an ADR; the developer answered "not mine"; the
  work ended in a deadlock over one line.
- Work b9470ffce6c6: after one round the design reviewer's two remaining points were text-only (an ADR bullet and the work's
  spec still describing the design that was rejected). The work stopped with "A person is needed". The message was the
  reviewer's whole text, and it did not say what was asked of the person. The answer fitted in ten lines that a model could
  write from the same files.
- The stop asks a person to arbitrate, but gives neither the options nor a recommendation. A person who only sent a need to
  Shelf cannot be expected to judge a design dispute from a pasted review.

The goal is a run that copes alone, from a request to a pull request, almost every time. A person stays the one who merges;
the question is how often anyone else has to be asked before that.

## Decision

Add an **arbitrator**: an agent role, with a context of its own, that runs when a review deadlocks and ends the deadlock or
says precisely what only a person can decide.

### One question, four answers

The choices of ADR 0013 stay (spec approval, design review). The checkbox "stop at a deadlock" becomes one question,
**"When the reviewer and the author cannot agree"**, with four answers, also settable per repository
(`[policy] on_deadlock`) and stored with the work:

| Answer (`on_deadlock`) | What happens |
| - | - |
| `ask` | A person is asked, with the brief below. Today's default. |
| `arbitrate-ask` | The arbitrator decides. A person is asked only when it answers `ESCALATE`. **Recommended for a work that must go on alone.** |
| `arbitrate-go` | The arbitrator decides. On `ESCALATE` the work goes on and the open point is posted on the pull request, for the phases that may be passed (the two document reviews). Code review and checks still ask. |
| `go` | Nobody settles: the work goes on, the open points are posted (today's "do not stop at a deadlock"). |

`proceed_on_deadlock` of ADR 0013 is read as `go` when true and `ask` when false, so existing files and stored works keep their
meaning.

### What the arbitrator does

It runs once per deadlock, read-only on the repository, with a model of its own (`SHELF_MODEL_ARBITRATOR`; Opus is the
sensible choice, since a reviewer is usually Opus too). It reads the document under review, the reviewer's last review, the
author's last answer, the repository's specifications and decisions, and the decision log of the work. It ends with one line:

- `ARBITRATION: FIX`: the reviewer is right and the author did not do it. The arbitrator writes numbered, concrete
  instructions and the command that proves each (for example a `grep` that must find nothing). The author gets one more
  round with exactly that text, and must report the proof.
- `ARBITRATION: OVERRULE`: the reviewer's point is wrong, out of scope or already satisfied. The arbitrator gives the evidence
  for each point (file and line, or command output). The work goes on and the decision is recorded.
- `ARBITRATION: ESCALATE`: only a person can decide (a contradiction of the request, money, access, a real trade-off with a
  product consequence). It writes the question, the options with what each costs, and a recommendation.

Limits that keep it from being a rubber stamp:

- It never overrules a red CI, a contradiction with an existing specification or decision, or a point about secrets,
  permissions or money.
- It cites evidence for every point it decides; a point without one is `ESCALATE`.
- At most one arbitration per deadlocked phase. When the author fails after a `FIX`, or the reviewer repeats after an
  `OVERRULE`, the answer chosen above (`ask` or `go`) applies. There is no loop.
- Failed steps (the model unreachable, a tool that crashed) and the merge are not arbitrated: they are not disagreements.
  They still ask a person.

### What a person sees, and where

The point of the role is also to make the remaining human stops readable, and to put a person's attention where it is cheapest
and safest.

1. **The start form.** One group of four radio buttons instead of a checkbox, each with a plain sentence of what happens and
   what it costs; the chosen one is summarised under the group.
2. **The stop.** "A person is needed" becomes a decision card: the question in one line; "the reviewer says / the author says"
   in two or three lines each (full texts folded); the arbitrator's recommendation when there was one; buttons that do
   something: *Follow the recommendation* (sends the changes with its text), *Edit and send*, *Go on and note it on the pull
   request*, *Reject*. The comment on the pull request carries the same, short, with the `/shelf changes` text ready to copy.
3. **The conversation.** An arbitration is an entry of its own, with its verdict as a badge, so nobody has to find it in
   a block of text. A work that is being arbitrated shows it as its state.
4. **The merge.** The pull request description and the work page end with a **"Settled without you"** section: every
   arbitration (phase, verdict, one line of why, link), every open point passed on, every assumption. An `OVERRULE` and a passed
   deadlock are marked "check before merging". The merge is the one stop that always remains, so it is where the person's
   attention is concentrated.

### How it is built

A new role and prompt; a pure step in `domain/work.py` (`Arbitrate` command, `Arbitrated` event) chosen by the course; a new
protocol number so that work already running and its replays keep the behaviour they started with; the decision written in
`decisions.md` like a person's (protocol 7). Specified in `openspec/specs/work-item`, `steps` and `web`.

## Consequences

- A work asks a person for a disagreement far less often, and when it does, the person gets a decision, not a review.
- A wrong arbitration costs a pull request that carries a flaw, never a merge: the person still merges. The "Settled without
  you" section is what makes that review cheap.
- Each arbitration costs one more agent run (about a reviewer's cost) and about a minute.
- The arbitrator and the reviewers are models: a shared blind spot is possible. The evidence rule and the fixed limits
  narrow it; they do not remove it. The first works that use it must be read for it.
- What still asks a person: the merge, a failed step, and an `ESCALATE` that no answer above lets pass. That is the honest
  residue; "almost always alone" is a measure to watch (how many works ask, and why), not a promise.

## Alternatives considered

- **Raise the number of rounds.** The two works above did not lack rounds: the author did not do what was asked, or the
  reviewer's text was not executable. More rounds repeat that.
- **Let the reviewer decide when it repeats.** It is the party of the dispute.
- **Always go on past a deadlock (ADR 0013 `go`).** Cheap, and it leaves flaws on the pull request that nobody has settled.
  It stays as an answer, not as the answer.
- **A second reviewer.** It adds a second opinion and no decision.
- **Only improve the stop message.** It helps a person decide; it does not remove the need for one. It is part of this decision
  because the arbitrator's brief is the same message.
