# 0009. Design the product interface as a calm, dense app screen in the site's colours

- Status: accepted
- Date: 2026-11-08

## Context

The web interface (ADR 0007) worked but was unstyled. People use it all day to see what needs them, start work and decide at gates, so it is an app screen, not a landing page: denser, calmer, and quick to scan. It should still look like the same project as the public site (ADR 0008). A self-hosted instance must make no request to any third party, so nothing may be loaded from a CDN or a font service.

## Decision

**Brand continuity, adapted for density.** The same tokens as the site: a pale sage ground, near-black green ink, one vermilion accent, a deep green field, surfaces told apart by a step in tone, square corners, light and dark themes. Display type is smaller (the page title is 2 to 3rem, not 7rem), and the accent is rationed: it marks only what needs a person (the waiting state, the primary button, the count of waiting items). Everything else is ink, green and tone.

**Fonts.** No web font is loaded or vendored. The stack is `"Schibsted Grotesk", ui-sans-serif, system-ui, ...`: the grotesque is used when the reader has it installed, and the system sans otherwise. A vendored woff2 would be allowed by the typeface's open font licence, but it would add a binary to a repository that has no build step, for a screen where system type already reads well. Revisit if the fallback look proves too far from the site. Monospace is used only for the agents' text output.

**Theme.** Follows `prefers-color-scheme`, with a toggle stored in `localStorage` (every access guarded by try/catch). A tiny blocking `theme.js` applies the remembered choice before first paint, so there is no flash.

**The board** groups work by what it asks of the person: Needs you first (largest heading, accent edge and chip), then Running, then Finished (quiet, outlined). Within Needs you, work waiting for a person comes before work waiting for a merge. Each row carries a status chip and a ten-cell strip of the pipeline with the phase named beside it. Filters (All, Needs you, Running, Finished) are a progressive enhancement: the filter lives on `#board` itself, which live updates never replace, so it survives them. The strip needs the phase order, which is repeated in `_macros.html` next to the labels in `views.py`; keep the two in step.

**The pipeline timeline** is the signature element: the ten phases as compartments in two shelves of five, as on the site. States are never colour alone: each has a glyph and a word. Done is a tone step with a check; in progress is deep green with a pulsing dot; waiting is the accent with a pause mark; stopped is hatched with a cross; not yet is dashed. The current step carries `aria-current="step"`.

**The decision panel** shows the primary action (Approve, or Resume) alone and full width in the accent. Request changes is secondary and sits with the note field, the only button that needs one, so the field appears only where there is such a button. Reject and Abort are separated under "Stop this work", tinted as danger, and ask for confirmation first.

**The start form** shows entry points as a selectable list with help text. A preview shows which phases the chosen entry goes through. The pull request number appears only for "Review my pull request", with CSS `:has`; where `:has` is unsupported, the field is simply always shown.

**Small behaviours in `static/app.js`** (loaded with `defer`, vanilla): theme toggle, board filter and counts, confirmation before a destructive decision, and three fixes for the self-refreshing panel: it is not refreshed while someone is typing a note, an identical refresh is not swapped in (so focus is kept and nothing flickers), and the 403 answer to a refused decision is swapped in so its message is shown.

**Accessibility.** Skip link, landmarks, one `h1` per page, visible focus, targets of at least 44px, contrast of at least 4.5:1 for text and 3:1 for control edges in both themes (measured), `aria-live="polite"` on the board and the panel, reduced motion respected, layout checked down to 360px.

**What stays.** Every `hx-*` and `sse-*` attribute, the ids `board` and `panel`, the form field names (`repo`, `entry`, `text`, `pull_request`, `note`, `kind`) and all URLs are unchanged. No Python changed.

## Consequences

- The interface looks like the site and stays quiet until something needs a person.
- No third-party request of any kind; no build step; two small scripts.
- The look depends on the reader's installed fonts; layout does not.
- The phase order exists in two places (`views.py` and `_macros.html`).
- The hatch pattern for the stopped state is the only gradient, kept because it carries meaning without colour.

## Alternatives considered

- A vendored woff2 of Schibsted Grotesk: matches the site exactly, but adds a binary and a licence file to maintain; deferred.
- A sidebar layout with a dashboard of totals: two destinations do not need it, and totals say less than "what needs me".
- A kanban board by pipeline phase: ten columns do not fit, and what matters is who must act, not which phase.
- A component library or utility CSS framework: needs a build step or a CDN.
