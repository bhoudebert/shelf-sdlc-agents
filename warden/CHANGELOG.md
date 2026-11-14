# Changelog

## 0.1.0 (2026-11-14)


### Features

* **warden:** an operator's locked policy and a settable session folder ([#97](https://github.com/bhoudebert/shelf-sdlc-agents/issues/97)) ([39ccecb](https://github.com/bhoudebert/shelf-sdlc-agents/commit/39ccecb519df406c7e527df3b10e1f77ddc2fa7c))
* **warden:** guard Codex, Copilot and OpenCode as well as Claude Code ([#103](https://github.com/bhoudebert/shelf-sdlc-agents/issues/103)) ([eff3a4e](https://github.com/bhoudebert/shelf-sdlc-agents/commit/eff3a4e86410485cb2706ed0c13b81b4d11dd480))
* **warden:** install from a release with a verified checksum ([#102](https://github.com/bhoudebert/shelf-sdlc-agents/issues/102)) ([427f34f](https://github.com/bhoudebert/shelf-sdlc-agents/commit/427f34f64ed2cf55209ce8939dcb0cf837bcb768))
* **warden:** judge Claude Code's tool calls with warden hook ([#95](https://github.com/bhoudebert/shelf-sdlc-agents/issues/95)) ([7701c32](https://github.com/bhoudebert/shelf-sdlc-agents/commit/7701c322642390c6bff2c340054221ca77d59a24))
* **warden:** judge shell commands against a layered policy ([#92](https://github.com/bhoudebert/shelf-sdlc-agents/issues/92)) ([4eca8c1](https://github.com/bhoudebert/shelf-sdlc-agents/commit/4eca8c1caddb6d3ee6d28f1bbff0954d3ce85e26))
* **warden:** keep a hash-chained audit log and show it ([#93](https://github.com/bhoudebert/shelf-sdlc-agents/issues/93)) ([35007a6](https://github.com/bhoudebert/shelf-sdlc-agents/commit/35007a620b5738d07601824eebb2d70b0fc6fdc3))
* **warden:** look at a recent period with --since ([#119](https://github.com/bhoudebert/shelf-sdlc-agents/issues/119)) ([0ddd632](https://github.com/bhoudebert/shelf-sdlc-agents/commit/0ddd632d8b5dbf2ba39bb7141762e06d81888f34))
* **warden:** print the report as JSON for a program ([#107](https://github.com/bhoudebert/shelf-sdlc-agents/issues/107)) ([794c0b9](https://github.com/bhoudebert/shelf-sdlc-agents/commit/794c0b9425ef8a5f1b2ab69609149135d5ad3e84))
* **warden:** recognise eighteen more provider credentials ([#109](https://github.com/bhoudebert/shelf-sdlc-agents/issues/109)) ([622356d](https://github.com/bhoudebert/shelf-sdlc-agents/commit/622356d2375ab7d163a33e96e2662d4606d032a4))
* **warden:** redact secrets and personal data, and run commands through it ([#94](https://github.com/bhoudebert/shelf-sdlc-agents/issues/94)) ([ed97928](https://github.com/bhoudebert/shelf-sdlc-agents/commit/ed97928d20e5574bbcc88f41286516285b87c614))
* **warden:** report what a stricter profile would have stopped ([#105](https://github.com/bhoudebert/shelf-sdlc-agents/issues/105)) ([bfd97ad](https://github.com/bhoudebert/shelf-sdlc-agents/commit/bfd97ad703241cd0fe3e55a6a469934e04d3d112))
* **warden:** wire Claude Code with init, take it out and check it ([#96](https://github.com/bhoudebert/shelf-sdlc-agents/issues/96)) ([9a79cb8](https://github.com/bhoudebert/shelf-sdlc-agents/commit/9a79cb89a971b9f3f7b4fa4165bb9069ba56ce9a))


### Bug fixes

* **warden:** check the Codex guard against the real Codex and refuse what it cannot ask ([#124](https://github.com/bhoudebert/shelf-sdlc-agents/issues/124)) ([f41b663](https://github.com/bhoudebert/shelf-sdlc-agents/commit/f41b663ca6529cc02b17cf4129ec6a22f0bddeca))
* **warden:** classify hosted deletions, database drops and reverse shells ([#106](https://github.com/bhoudebert/shelf-sdlc-agents/issues/106)) ([a1c5ee0](https://github.com/bhoudebert/shelf-sdlc-agents/commit/a1c5ee02d8cba11b6265473aa207a4728629bc18))
* **warden:** guard more credential files from being read ([#111](https://github.com/bhoudebert/shelf-sdlc-agents/issues/111)) ([bfd64ea](https://github.com/bhoudebert/shelf-sdlc-agents/commit/bfd64ead3927bda428ac130b28a022fa80870142))
* **warden:** keep unattended agents off the default branch ([#115](https://github.com/bhoudebert/shelf-sdlc-agents/issues/115)) ([26c2c24](https://github.com/bhoudebert/shelf-sdlc-agents/commit/26c2c244ea0b2ffb0736f4b746911cbcdbe53ff7))
* **warden:** spool audit records from the sandbox and stay quiet about its own trouble ([#100](https://github.com/bhoudebert/shelf-sdlc-agents/issues/100)) ([ddc375b](https://github.com/bhoudebert/shelf-sdlc-agents/commit/ddc375b977242b04427ea57396bb75f911e714f3))
* **warden:** treat tunnels, address pushes and metadata endpoints as exfiltration ([#112](https://github.com/bhoudebert/shelf-sdlc-agents/issues/112)) ([e792c83](https://github.com/bhoudebert/shelf-sdlc-agents/commit/e792c83b97236d9c77f02eb6c4b727961449c38d))


### Documentation

* **warden:** bring the readme up to date and list what each profile decides ([#123](https://github.com/bhoudebert/shelf-sdlc-agents/issues/123)) ([c800e58](https://github.com/bhoudebert/shelf-sdlc-agents/commit/c800e58d8ee0df85e674ec8898134a62d3365c6e))


### Build and tooling

* **deps:** bump sha2 from 0.10.9 to 0.11.0 in /warden ([#129](https://github.com/bhoudebert/shelf-sdlc-agents/issues/129)) ([5bb8374](https://github.com/bhoudebert/shelf-sdlc-agents/commit/5bb8374a023e42cf3f928083c9d0ab9d1ef54c2d))
* **warden:** decide on a Rust guard for agents and scaffold it ([#91](https://github.com/bhoudebert/shelf-sdlc-agents/issues/91)) ([9304abe](https://github.com/bhoudebert/shelf-sdlc-agents/commit/9304abed36ed5872dced8b65bb6aabfbea286990))
