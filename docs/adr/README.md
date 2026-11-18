# Architecture decision records

Why the system is shaped the way it is. Behaviour is specified in `openspec/specs/`; these records hold the reasons. New records use
`template.md` and the next free number; an accepted record is superseded, not rewritten.

| # | Decision | Status |
| - | - | - |
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | accepted |
| [0002](0002-conventional-commits-and-automated-releases.md) | Conventional Commits, squash merges, automated releases | accepted |
| [0003](0003-one-agent-instruction-file.md) | One agent instruction file for every agent | accepted |
| [0004](0004-specs-are-checked-in-ci.md) | Specs are checked in CI, and drift is checked by code first and a local model second | accepted |
| [0005](0005-apache-2-0-licence.md) | License the project under Apache-2.0 | accepted |
| [0006](0006-python-with-a-pure-core-and-hexagonal-layers.md) | Python, with a pure functional core in hexagonal layers | accepted |
| [0007](0007-a-python-only-web-ui.md) | Serve the web UI from Python, with HTMX and server-sent events | accepted |
| [0008](0008-the-public-site-design.md) | Build the public site as plain HTML and CSS with a field-and-type design | superseded by 0018 |
| [0009](0009-the-product-interface-design.md) | Design the product interface as a calm, dense app screen in the site's colours | accepted |
| [0010](0010-access-is-closed-by-default.md) | Access is closed by default | accepted |
| [0013](0013-let-a-run-go-on-without-a-person.md) | Let a run go on without a person | accepted |
| [0014](0014-guard-agents-with-warden-a-policy-engine-in-rust.md) | Guard agents with Warden, a policy engine in Rust | accepted |
| [0015](0015-read-the-guard-through-its-binary.md) | Read the guard through its binary | accepted |
| [0016](0016-results-land-where-the-repository-keeps-them.md) | Let the results of a run land where the repository keeps them | accepted |
| [0017](0017-let-agents-read-the-web-and-keep-downloads-limited.md) | Let agents read the web, and keep downloads limited | accepted |
| [0018](0018-show-the-product-on-the-public-site.md) | Show the product on the public site, in the product's own tokens | accepted |
| [0019](0019-run-each-step-in-an-isolated-environment.md) | Run each step in an isolated environment, with nothing less than today | proposed |
