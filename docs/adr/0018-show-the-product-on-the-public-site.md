# 0018. Show the product on the public site, in the product's own tokens

- Status: accepted
- Date: 2026-11-15

## Context

ADR 0008 chose a hand-written static site with a field-and-type design: a sage-and-vermilion palette and the pipeline as a
shelf of compartments. That site described Shelf. It did not show what Shelf does, and a visitor had to read the guide to
find out. The product interface has since taken the night-sky navy, one orange accent and teal for what moves (ADR 0009),
and the guide grew a path (concepts, install, a repository's file, roles, the guard, operating).

## Decision

- The site keeps ADR 0008's technical choices: plain HTML and one stylesheet in `site/`, no build step, published by
  `.github/workflows/pages.yml`, inline SVG and CSS, only the theme toggle and copy buttons as scripts.
- The look is now the product's: the same tokens and type as the app (`site/assets/site.css`), and the pictures are the
  product's own interface rebuilt in HTML and CSS from its real templates (the board, a work page with its ten phases, the
  admin Guard panel, a pull request's progress comment), carrying real-looking data that adds up and labelled as an example.
- The home page leads with what a run does and where a person decides, shows the guard answering a command, and ends with
  one command to install. It says nothing the code does not do, and invents no customer, quote or figure.
- The guide is a path, one page per task, and the numbers and commands in it come from the code, the specs and `deploy/`.

## Consequences

- A visitor sees the product before reading anything, and the fragments cannot drift far: they reuse the app's tokens.
- The fragments are copies of the interface in HTML: when the interface changes, the matching fragment is changed by hand.
  Nothing checks that they agree.
- The pipeline-as-shelf image of ADR 0008 is replaced by the product's timeline.

## Alternatives considered

- Screenshots of the real interface: truer, but binary files that go stale unseen, are heavy and do not follow the theme.
- A site generator or a framework: still not worth a toolchain for a handful of pages.
