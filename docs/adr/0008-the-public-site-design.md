# 0008. Build the public site as plain HTML and CSS with a field-and-type design

- Status: accepted
- Date: 2026-11-08

## Context

The project needs a public site: a landing page and documentation for people who will self-host it. The audience is developers and operators. The project is in early development, so the site must be honest about what exists. The repository has no Node toolchain and should not gain one for a site.

## Decision

The site lives in `site/` as hand-written static HTML and one shared stylesheet, published to GitHub Pages by `.github/workflows/pages.yml` with no build step. Small vanilla scripts handle only the theme toggle and copy buttons.

The art direction is flat fields and large type. One grotesque typeface (Schibsted Grotesk, optional from Google Fonts, with a system fallback) and the system monospace for real code only. Colour is one ground, one ink and one vermilion accent, plus a deep green field for the pipeline and the status sections; light and dark themes follow `prefers-color-scheme` with a manual toggle. Surfaces are separated by steps in tone, not by borders, gradients or shadows. The pipeline is the central image: the eight steps as a shelf of compartments, with the entry points filled in the accent colour. Diagrams and icons are inline SVG or CSS, so the page makes no request other than the optional font.

## Consequences

- Nothing to install or build; any contributor can edit a page by hand.
- Navigation and the page frame are repeated in each HTML file; a change to them touches every page.
- The look is distinctive but depends on the font being available; the fallback keeps layout intact.
- Accessibility is built in: semantic landmarks, visible focus, contrast checked in both themes, reduced-motion respected.

## Alternatives considered

- A static site generator (Hugo, Astro, MkDocs): less repetition, but adds a toolchain and a build step to a repository that has neither.
- A stock documentation theme: fast, but it would look like every other project and would not carry the pipeline idea.
- Only the README: too thin for a self-hosting guide and the security model.
