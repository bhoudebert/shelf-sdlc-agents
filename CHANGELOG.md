# Changelog

## 0.1.0 (2026-11-09)


### Features

* add access rules, roles, ports and the work use cases ([#6](https://github.com/bhoudebert/shelf-sdlc-agents/issues/6)) ([c17229a](https://github.com/bhoudebert/shelf-sdlc-agents/commit/c17229a6ac84de0838e0765c76d1e1fbd86753b2))
* add the entry points and the Docker Compose deployment ([#14](https://github.com/bhoudebert/shelf-sdlc-agents/issues/14)) ([2ce42c9](https://github.com/bhoudebert/shelf-sdlc-agents/commit/2ce42c99ad3c8c4de101073ac082d76fad09d224))
* add the GitHub App adapter ([#8](https://github.com/bhoudebert/shelf-sdlc-agents/issues/8)) ([557daff](https://github.com/bhoudebert/shelf-sdlc-agents/commit/557dafffdd25117df05d8c68e3df9608efa0a602))
* add the pull-request adapter and the /shelf commands ([#11](https://github.com/bhoudebert/shelf-sdlc-agents/issues/11)) ([43e4a46](https://github.com/bhoudebert/shelf-sdlc-agents/commit/43e4a46d34e0fd896f6044aec2abeebc50f75722))
* add the pure work-item state machine ([#5](https://github.com/bhoudebert/shelf-sdlc-agents/issues/5)) ([597ebc0](https://github.com/bhoudebert/shelf-sdlc-agents/commit/597ebc0124bb1f5c1f004b8dee622fb79e6489e0))
* add the step runner, git workspace and Claude backend ([#12](https://github.com/bhoudebert/shelf-sdlc-agents/issues/12)) ([f00f556](https://github.com/bhoudebert/shelf-sdlc-agents/commit/f00f5568f6d576864ebf2a343227d5f3fc67505b))
* add the Temporal work runner and TOML configuration ([#9](https://github.com/bhoudebert/shelf-sdlc-agents/issues/9)) ([4103898](https://github.com/bhoudebert/shelf-sdlc-agents/commit/410389833dcb602c717765131943b82972cbdcdf))
* add the Temporal workflow that interprets the work-item state machine ([#7](https://github.com/bhoudebert/shelf-sdlc-agents/issues/7)) ([9576f94](https://github.com/bhoudebert/shelf-sdlc-agents/commit/9576f94aa9f7ea1eda220b59b021400db695cc85))
* add the web adapter ([#13](https://github.com/bhoudebert/shelf-sdlc-agents/issues/13)) ([ad7291c](https://github.com/bhoudebert/shelf-sdlc-agents/commit/ad7291c915d1e3eb2fa1aaf7dc7504fc366c86e7))
* admin page, agents blind to secrets, PR type from intent, faster net ([#34](https://github.com/bhoudebert/shelf-sdlc-agents/issues/34)) ([95e44f2](https://github.com/bhoudebert/shelf-sdlc-agents/commit/95e44f240216b108a9fc10e34fa121e35f0c30cf))
* administrators see every run and reach Temporal behind the sign-in ([#25](https://github.com/bhoudebert/shelf-sdlc-agents/issues/25)) ([8b63e9a](https://github.com/bhoudebert/shelf-sdlc-agents/commit/8b63e9a1ee0e806ba849a695d8b7f2e24ba6aa59))
* agents speak on the pull request as a team, with a living progress comment ([#29](https://github.com/bhoudebert/shelf-sdlc-agents/issues/29)) ([0ba7c48](https://github.com/bhoudebert/shelf-sdlc-agents/commit/0ba7c4878fa1831905d95d9b1ab2d2ac9accab9b))
* **deploy:** add a script that fixes an Ubuntu host for the agents' sandbox ([#39](https://github.com/bhoudebert/shelf-sdlc-agents/issues/39)) ([d33dafd](https://github.com/bhoudebert/shelf-sdlc-agents/commit/d33dafd49312d1022bb4ab6ec64a234697571101))
* **deployment:** add shelf-diagnose, and refuse a review of a pull request the repository lacks ([#57](https://github.com/bhoudebert/shelf-sdlc-agents/issues/57)) ([0b92063](https://github.com/bhoudebert/shelf-sdlc-agents/commit/0b920630899fea80795ea64691a7042766542fae))
* **deployment:** catch install mistakes before building and let the operator bind the port ([#63](https://github.com/bhoudebert/shelf-sdlc-agents/issues/63)) ([1588df6](https://github.com/bhoudebert/shelf-sdlc-agents/commit/1588df695ae4d01bba41af8f1ac50bb0f67c97d2))
* design the product interface ([#15](https://github.com/bhoudebert/shelf-sdlc-agents/issues/15)) ([d0127bb](https://github.com/bhoudebert/shelf-sdlc-agents/commit/d0127bb5ef7ea19a0629b77c05202ad2ccba7b1e))
* **github-app:** check the App's setup on GitHub from the admin page ([#43](https://github.com/bhoudebert/shelf-sdlc-agents/issues/43)) ([cd2304c](https://github.com/bhoudebert/shelf-sdlc-agents/commit/cd2304c3e81bde4d3003785f760a19b7dec23207))
* **github-app:** register the App public, with a description, and explain the 404 ([#55](https://github.com/bhoudebert/shelf-sdlc-agents/issues/55)) ([7bc7cee](https://github.com/bhoudebert/shelf-sdlc-agents/commit/7bc7cee729c62efd796daa34e89564c0eeda6997))
* open the draft pull request early and report every step on it ([#27](https://github.com/bhoudebert/shelf-sdlc-agents/issues/27)) ([7356229](https://github.com/bhoudebert/shelf-sdlc-agents/commit/7356229fa11a988945ea758dbf34c528b050a489))
* **pull-requests:** mark superseded comments outdated when the flow circles back ([#65](https://github.com/bhoudebert/shelf-sdlc-agents/issues/65)) ([b0ee830](https://github.com/bhoudebert/shelf-sdlc-agents/commit/b0ee830f73840ca496f3e74f72e38d343f91be34))
* show administrators whether GitHub webhooks arrive ([#33](https://github.com/bhoudebert/shelf-sdlc-agents/issues/33)) ([181b844](https://github.com/bhoudebert/shelf-sdlc-agents/commit/181b844c493b8a12aab174730c6e9e96733a94cc))
* show the documents on the work page and fix the refresh that ate clicks ([#28](https://github.com/bhoudebert/shelf-sdlc-agents/issues/28)) ([92f7477](https://github.com/bhoudebert/shelf-sdlc-agents/commit/92f7477fde456cb04fc85be361d7146d938b62f0))
* **steps:** block the work on the repository's CI, not only on local commands ([#47](https://github.com/bhoudebert/shelf-sdlc-agents/issues/47)) ([3694a82](https://github.com/bhoudebert/shelf-sdlc-agents/commit/3694a8216a2097882928e75cd2e09c4aea80d052))
* **steps:** give agents the tools a repository declares, with caches of its own ([#44](https://github.com/bhoudebert/shelf-sdlc-agents/issues/44)) ([e618e58](https://github.com/bhoudebert/shelf-sdlc-agents/commit/e618e587438d6f3f8d3db7ac4cabe38f4b98af46))
* **steps:** give the developer the CI state and the log of a failing job ([#50](https://github.com/bhoudebert/shelf-sdlc-agents/issues/50)) ([c603622](https://github.com/bhoudebert/shelf-sdlc-agents/commit/c603622642c61f0a4096751d5efdb6fc864ef161))
* take the GitHub App private key as a mounted file ([#23](https://github.com/bhoudebert/shelf-sdlc-agents/issues/23)) ([9a14374](https://github.com/bhoudebert/shelf-sdlc-agents/commit/9a143744dc69a6901bb7b6537c14e7a5c5365eed))
* **web:** cosmic design proposal ([#70](https://github.com/bhoudebert/shelf-sdlc-agents/issues/70)) ([2961fc6](https://github.com/bhoudebert/shelf-sdlc-agents/commit/2961fc68dcd30f2b2f11c9cffc330ab106e8916c))
* **web:** dark by default, and a roomy box for saying what should change ([#71](https://github.com/bhoudebert/shelf-sdlc-agents/issues/71)) ([f166945](https://github.com/bhoudebert/shelf-sdlc-agents/commit/f1669450bf1d7f8dabc4e742ca6fd2c7a967dc89))
* **web:** fold the conversation, newest first, and never serve an old stylesheet ([#54](https://github.com/bhoudebert/shelf-sdlc-agents/issues/54)) ([2786fef](https://github.com/bhoudebert/shelf-sdlc-agents/commit/2786fef0157f52d9eb1ebb05f2b55f1bfb3e41d0))
* **web:** link to add a repository on GitHub, and README badges ([#69](https://github.com/bhoudebert/shelf-sdlc-agents/issues/69)) ([899bfea](https://github.com/bhoudebert/shelf-sdlc-agents/commit/899bfea538a969c951e584e5b03ae1b9d04ddd07))
* **web:** put the time of every step on the progress comment, the board and the timeline ([#52](https://github.com/bhoudebert/shelf-sdlc-agents/issues/52)) ([9468be5](https://github.com/bhoudebert/shelf-sdlc-agents/commit/9468be598c3368c326bf4c124343c68a7cb3d946))
* **web:** say on the board and the work page what each work is, with its pull request ([#48](https://github.com/bhoudebert/shelf-sdlc-agents/issues/48)) ([d643066](https://github.com/bhoudebert/shelf-sdlc-agents/commit/d64306615b1acb8cacbbf3fa72f3b8fef79f8d1a))
* **web:** show the pull request's conversation on the work page, read only ([#53](https://github.com/bhoudebert/shelf-sdlc-agents/issues/53)) ([3551ccd](https://github.com/bhoudebert/shelf-sdlc-agents/commit/3551ccd446f11bc0fab84b1a56b6ef9b59c12f9e))
* **work-item:** a review of someone else's pull request asks a person ([#41](https://github.com/bhoudebert/shelf-sdlc-agents/issues/41)) ([243a923](https://github.com/bhoudebert/shelf-sdlc-agents/commit/243a923c8ef285793dcecab84fef995bc5e49c45))
* **work-item:** accepting an escalated review also approves the gate after it ([#68](https://github.com/bhoudebert/shelf-sdlc-agents/issues/68)) ([89932a9](https://github.com/bhoudebert/shelf-sdlc-agents/commit/89932a97e8f847b3d0f1cab581e30487e9804642))
* **work-item:** work on my pull request: rebase, fix and verify its own branch ([#58](https://github.com/bhoudebert/shelf-sdlc-agents/issues/58)) ([f1fb5f6](https://github.com/bhoudebert/shelf-sdlc-agents/commit/f1fb5f60e62a8fb66db096c642eb30bf8d32e28b))
* **work-requests:** read public repositories linked in the request as reference, never run ([#67](https://github.com/bhoudebert/shelf-sdlc-agents/issues/67)) ([a9306c3](https://github.com/bhoudebert/shelf-sdlc-agents/commit/a9306c334d32898fbf7d8071615573714dd39dac))
* **work-requests:** start from an issue, a pull request or a file, always optionally ([#64](https://github.com/bhoudebert/shelf-sdlc-agents/issues/64)) ([0504d47](https://github.com/bhoudebert/shelf-sdlc-agents/commit/0504d476cb62689bdeaeb0fa5752207fb77b852a))


### Bug fixes

* **access:** close the instance by default and apply the list to GitHub commands ([#35](https://github.com/bhoudebert/shelf-sdlc-agents/issues/35)) ([4029aa2](https://github.com/bhoudebert/shelf-sdlc-agents/commit/4029aa2792c4d4119eda244b42ed784835753dd0))
* agents run like Claude Code locally, follow the repository, name PRs properly ([#32](https://github.com/bhoudebert/shelf-sdlc-agents/issues/32)) ([6234ea2](https://github.com/bhoudebert/shelf-sdlc-agents/commit/6234ea2af14fedbec0b4be146e87172f5b16ebf7))
* **doctor:** read the proposed pull request title from the first line ([#38](https://github.com/bhoudebert/shelf-sdlc-agents/issues/38)) ([cd4f2ad](https://github.com/bhoudebert/shelf-sdlc-agents/commit/cd4f2ad8a1cfa1579fcd4419d04015da3b19720b))
* **durable-workflow:** link the pull request a review started from ([#42](https://github.com/bhoudebert/shelf-sdlc-agents/issues/42)) ([ffc0bf0](https://github.com/bhoudebert/shelf-sdlc-agents/commit/ffc0bf0f320b8d18e0c5a33c35c46d4b09d8b2d9))
* give the first-run screens the product's design ([#18](https://github.com/bhoudebert/shelf-sdlc-agents/issues/18)) ([c29cbd4](https://github.com/bhoudebert/shelf-sdlc-agents/commit/c29cbd4b0417805dec6efe1e0762d91689117ede))
* keep work in progress alive across updates ([#31](https://github.com/bhoudebert/shelf-sdlc-agents/issues/31)) ([dbe728d](https://github.com/bhoudebert/shelf-sdlc-agents/commit/dbe728dc5a71f3f72d0ccd9da36c434a4e1313a1))
* let reviewers run git and show every agent the whole picture ([#30](https://github.com/bhoudebert/shelf-sdlc-agents/issues/30)) ([3390e2e](https://github.com/bhoudebert/shelf-sdlc-agents/commit/3390e2e4b85798a2c14d1844bc6b799739f7386d))
* make GitHub App registration work and explain it step by step ([#20](https://github.com/bhoudebert/shelf-sdlc-agents/issues/20)) ([925b024](https://github.com/bhoudebert/shelf-sdlc-agents/commit/925b0249a9a197f80fb3bb0cb74bdc8c8e8270af))
* make the install script replace and report what runs ([#19](https://github.com/bhoudebert/shelf-sdlc-agents/issues/19)) ([3ee01e7](https://github.com/bhoudebert/shelf-sdlc-agents/commit/3ee01e7920fc8a7a2f6cd8f0e470c5e48562f608))
* report an invalid shelf.toml clearly instead of a crash loop ([#22](https://github.com/bhoudebert/shelf-sdlc-agents/issues/22)) ([6c65823](https://github.com/bhoudebert/shelf-sdlc-agents/commit/6c65823418c98a990a372f449e432e3ecaaaf534))
* serve the static files on the first-run setup page ([#17](https://github.com/bhoudebert/shelf-sdlc-agents/issues/17)) ([c2a36ed](https://github.com/bhoudebert/shelf-sdlc-agents/commit/c2a36ed5e681a7ae446eba7876fffb65853a6a87))
* **steps:** explain a push refused for the Workflows permission ([#45](https://github.com/bhoudebert/shelf-sdlc-agents/issues/45)) ([cc47a4b](https://github.com/bhoudebert/shelf-sdlc-agents/commit/cc47a4b4d2d0342589a6edebc5d1124bba4b2c3a))
* **steps:** heartbeat for as long as a step runs, so a wait for the CI is not timed out ([#49](https://github.com/bhoudebert/shelf-sdlc-agents/issues/49)) ([4035705](https://github.com/bhoudebert/shelf-sdlc-agents/commit/403570557cd03560fd03c5e1aee62f026a8604f4))
* stop tracking shelf.toml; create it from an example ([#24](https://github.com/bhoudebert/shelf-sdlc-agents/issues/24)) ([582d94b](https://github.com/bhoudebert/shelf-sdlc-agents/commit/582d94ba3c1daf62b487823690a069f93458d589))
* **web:** let a document's text use the whole width of its folded panel ([#51](https://github.com/bhoudebert/shelf-sdlc-agents/issues/51)) ([aa06f83](https://github.com/bhoudebert/shelf-sdlc-agents/commit/aa06f83841d067ab84fedc18b424ae769107b3be))
* **web:** let an administrator close work an older release left unreadable ([#36](https://github.com/bhoudebert/shelf-sdlc-agents/issues/36)) ([4f873bf](https://github.com/bhoudebert/shelf-sdlc-agents/commit/4f873bffd2a14fa5749b76c57aea78f0a5b031c1))
* **web:** let Temporal's named queries, such as the stack trace, through the read-only proxy ([#60](https://github.com/bhoudebert/shelf-sdlc-agents/issues/60)) ([da117c3](https://github.com/bhoudebert/shelf-sdlc-agents/commit/da117c307098dc25c9f63e4d192d58670b3f404c))
* **web:** link no plan and promise no spec for work on an existing pull request ([#62](https://github.com/bhoudebert/shelf-sdlc-agents/issues/62)) ([435a0ae](https://github.com/bhoudebert/shelf-sdlc-agents/commit/435a0aea6f43acfa4be9f0bbd5359bf6a84cc720))
* **web:** make the light theme the default whatever the system prefers ([#56](https://github.com/bhoudebert/shelf-sdlc-agents/issues/56)) ([b9514dd](https://github.com/bhoudebert/shelf-sdlc-agents/commit/b9514ddfbeabc7a346963bf0e794c92ccdf626a9))
* **web:** redirect after closing work to a fixed page ([#37](https://github.com/bhoudebert/shelf-sdlc-agents/issues/37)) ([e5ad311](https://github.com/bhoudebert/shelf-sdlc-agents/commit/e5ad31145b18d8a92e9cb4cd19e9474ca9ead978))
* **web:** show a failed workflow as over, with the reason it gave, not as unreadable ([#61](https://github.com/bhoudebert/shelf-sdlc-agents/issues/61)) ([9d1537d](https://github.com/bhoudebert/shelf-sdlc-agents/commit/9d1537db6e2cca78602f52e78e91ad539ad55fbd))
* **web:** show the steps of work on a pull request in the start preview ([#59](https://github.com/bhoudebert/shelf-sdlc-agents/issues/59)) ([631bf51](https://github.com/bhoudebert/shelf-sdlc-agents/commit/631bf511ac64e6c41cb439475996f3611538ac48))
* **work-requests:** parse a reference's address instead of matching it with a pattern ([#66](https://github.com/bhoudebert/shelf-sdlc-agents/issues/66)) ([927de20](https://github.com/bhoudebert/shelf-sdlc-agents/commit/927de20c6e37f52025f9cc4debbea99d714eea3b))


### Performance

* stop every open board from hammering GitHub and Temporal ([#26](https://github.com/bhoudebert/shelf-sdlc-agents/issues/26)) ([a9f4099](https://github.com/bhoudebert/shelf-sdlc-agents/commit/a9f4099d0429927422280c0a671100c504b54474))


### Documentation

* add the public site ([#10](https://github.com/bhoudebert/shelf-sdlc-agents/issues/10)) ([032ccbf](https://github.com/bhoudebert/shelf-sdlc-agents/commit/032ccbf4d4b537cdaaf63a12999897d785024e18))
* document the architecture, security model and the verified deployment ([#16](https://github.com/bhoudebert/shelf-sdlc-agents/issues/16)) ([bc478d7](https://github.com/bhoudebert/shelf-sdlc-agents/commit/bc478d7cf7695758442a367e77c12d3071a43854))
* **github-app:** name the safeguards when the Workflows permission is granted ([#46](https://github.com/bhoudebert/shelf-sdlc-agents/issues/46)) ([07b2a2e](https://github.com/bhoudebert/shelf-sdlc-agents/commit/07b2a2e9cd0027256f94fafe0f6832c2123f6131))


### Build and tooling

* move the foundation to Python with a hexagonal skeleton ([#2](https://github.com/bhoudebert/shelf-sdlc-agents/issues/2)) ([61372e8](https://github.com/bhoudebert/shelf-sdlc-agents/commit/61372e8f2bb0ebbb9b80ff91d67ac9a9ddedcbd4))
