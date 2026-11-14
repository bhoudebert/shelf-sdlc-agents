# 0013. Let a run go on without a person

- Status: accepted
- Date: 2026-11-14

## Context

A run asks a person in four places: the spec approval gate, an escalation (a reviewer cannot decide, or a loop used its
rounds), a failed step, and the merge. Someone who starts work in the evening and wants a pull request in the morning is
stopped at the first of them: a spec writer and a spec reviewer that disagree three times leave the work waiting for hours.

Two of the stops can already be switched off per repository (`spec_approval` and `design_review` in `.shelf/config.toml`).
They are not the same kind of thing: the spec approval is a person, the design review is an agent. Neither helps with the
deadlock, which is the stop that really costs the night.

## Decision

Three choices shape how much a run may do without a person. Each has a default per repository (`[policy]`) and is shown, with
its default, on the start form, so the person chooses for this piece of work and sees what the choice costs:

- `spec_approval`: wait for a person to approve the spec (existing).
- `design_review`: an agent reviews the design before the plan (existing).
- `proceed_on_deadlock` (new, off by default): when the **spec review** or the **design review** cannot settle (it answers
  `ESCALATE`, or the loop used its rounds), the work goes on instead of waiting, and the points that stayed open are posted
  on the pull request for the person to read later.

What stays, in every combination: the spec review, the code review, the repository's own checks and the human merge. A red
check, or a code review that cannot decide, still waits for a person; letting those pass is where an unattended night does
harm. Only the two reviews of documents may be passed on.

Agents of a work that proceeds on deadlock are told that nobody will answer: they pick the most reasonable reading of an open
point instead of stopping to ask, and write each such choice under an `Assumptions` heading of their document.

The start form shows the three choices as checkboxes, preset from the repository, under a clear statement of the trade:
more autonomy, less control and potentially less quality. The choice is stored with the work, so a later edit of the
repository's file never changes work already running.

## Consequences

- A night run can reach a pull request with spec or design points still open. They are written on the pull request, but a
  person must read them: the merge remains the control.
- Quality drops when review is passed over. The mitigation is what stays (code review, checks, the merge), the assumptions
  being written down, and the loop limit still bounding what a deadlocked night can spend.
- The decider gains one behaviour, gated on a flag that is false for every history recorded before: those replay unchanged.
- No new role or credential, and nothing about the isolation of agents changes.

## Alternatives considered

- **One switch named "night mode" that turns everything off.** Hides what is lost. Three visible choices say what is lost.
- **Skipping every reviewer.** A review of the code is the last automatic line before the person; removing it makes a bad
  night expensive. Rejected.
- **Letting a failed check or a code review deadlock pass too.** Rejected for the same reason: the harm of an unattended run
  is concentrated there.
- **Asking a person only once at the end for all the open points.** That is what this does: the merge is the single question.
