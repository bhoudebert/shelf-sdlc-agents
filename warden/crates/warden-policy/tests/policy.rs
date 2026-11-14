#![allow(clippy::expect_used, clippy::unwrap_used, clippy::indexing_slicing)]

use std::path::Path;

use warden_policy::{Category, Decision, Layer, Mode, Network, OnError, Policy, Profile};

const HOME: &str = "/home/dev";

fn layer(text: &str) -> Layer {
    Layer::parse(text).expect("layer parses")
}

fn resolve(layers: &[(&str, &str)]) -> Policy {
    let layers: Vec<(String, Layer)> = layers.iter().map(|(name, text)| ((*name).to_owned(), layer(text))).collect();
    Policy::resolve(&layers, Path::new(HOME)).expect("resolves")
}

fn preset(profile: &str) -> Policy {
    resolve(&[("test", &format!("profile = \"{profile}\""))])
}

#[test]
fn every_profile_has_a_preset_that_resolves_and_decides_every_shell_category() {
    for profile in ["observe", "guarded", "strict", "unattended", "shelf"] {
        let policy = preset(profile);
        for category in [Category::Destructive, Category::Exfil, Category::Tamper, Category::SecretAccess] {
            assert!(policy.categories.contains_key(&category) || category.always_denied(), "{profile}: {category}");
        }
        assert!(policy.warnings.is_empty(), "{profile}: {:?}", policy.warnings);
    }
}

#[test]
fn the_default_profile_is_guarded() {
    let policy = resolve(&[]);
    assert_eq!(policy.profile, Profile::Guarded);
    assert_eq!(policy.decision(Category::Destructive), Decision::Ask);
    assert_eq!(policy.decision(Category::Exfil), Decision::Deny);
    assert!(policy.interactive);
    assert_eq!(policy.mode, Mode::Enforce);
}

#[test]
fn observe_decides_like_guarded_but_enforces_nothing() {
    let observe = preset("observe");
    assert_eq!(observe.mode, Mode::Audit);
    assert_eq!(observe.decision(Category::Exfil), Decision::Deny);
}

#[test]
fn strict_is_stricter_than_guarded_everywhere_it_differs() {
    let (guarded, strict) = (preset("guarded"), preset("strict"));
    for category in Category::ALL {
        assert!(strict.decision(*category) >= guarded.decision(*category), "{category}");
    }
    assert_eq!(strict.on_error, OnError::Closed);
}

#[test]
fn unattended_never_asks_and_fails_closed() {
    for profile in ["unattended", "shelf"] {
        let policy = preset(profile);
        assert!(!policy.interactive, "{profile}");
        assert_eq!(policy.on_error, OnError::Closed, "{profile}");
        assert!(
            policy.categories.values().all(|decision| *decision != Decision::Ask),
            "{profile} must not leave an ask nobody can answer"
        );
        assert_eq!(policy.paths.scope, Some(vec![".".to_owned()]));
    }
}

#[test]
fn tampering_and_blocked_domains_are_denied_whatever_a_file_says() {
    let policy = resolve(&[("repo", "[categories]\ntamper = \"allow\"\nblocked_domain = \"ask\"")]);
    assert_eq!(policy.decision(Category::Tamper), Decision::Deny);
    assert_eq!(policy.decision(Category::BlockedDomain), Decision::Deny);
    assert_eq!(policy.warnings.len(), 2);
}

#[test]
fn a_layer_overrides_a_decision_and_lists_add_up() {
    let policy = resolve(&[
        ("global", "[categories]\npackage_install = \"ask\"\n[paths]\nprotected = [\"infra/prod/**\"]"),
        ("repo", "[categories]\npackage_install = \"allow\"\n[paths]\nprotected = [\"CODEOWNERS\"]"),
    ]);
    assert_eq!(policy.decision(Category::PackageInstall), Decision::Allow);
    assert!(policy.paths.protected.is_match(&["infra/prod/main.tf"]));
    assert!(policy.paths.protected.is_match(&["CODEOWNERS"]));
    assert!(policy.paths.protected.is_match(&["/home/dev/.claude/settings.json"]), "the preset's entries stay");
}

#[test]
fn a_locked_layer_cannot_be_loosened_by_the_layers_after_it() {
    let policy = resolve(&[
        (
            "operator",
            "locked = true\nprofile = \"unattended\"\n[categories]\nexfil = \"deny\"\nsecret_access = \"deny\"",
        ),
        (
            "repo",
            "mode = \"audit\"\ninteractive = true\non_error = \"open\"\n[categories]\nexfil = \"allow\"\nsecret_access = \"ask\"\n\
             publish = \"deny\"\n[[rules]]\nid = \"loosen\"\nmatch = \"^curl\"\ndecision = \"allow\"",
        ),
    ]);
    assert_eq!(policy.decision(Category::Exfil), Decision::Deny);
    assert_eq!(policy.decision(Category::SecretAccess), Decision::Deny);
    assert_eq!(policy.decision(Category::Publish), Decision::Deny);
    assert_eq!(policy.mode, Mode::Enforce);
    assert!(!policy.interactive);
    assert_eq!(policy.on_error, OnError::Closed);
    assert!(policy.rules.iter().all(|rule| rule.id != "loosen"));
    assert!(policy.locked);
    assert_eq!(policy.warnings.len(), 6, "{:?}", policy.warnings);
}

#[test]
fn a_layer_after_a_locked_one_can_still_tighten() {
    let policy = resolve(&[
        ("operator", "locked = true\nprofile = \"guarded\""),
        (
            "repo",
            "[categories]\npackage_install = \"deny\"\n[[rules]]\nid = \"no-prod\"\nmatch = \"prod\"\ndecision = \"deny\"\n\
             [paths]\nprotected = [\"migrations/**\"]",
        ),
    ]);
    assert_eq!(policy.decision(Category::PackageInstall), Decision::Deny);
    assert_eq!(policy.rule_for("kubectl --context prod get pods").map(|r| r.id.as_str()), Some("no-prod"));
    assert_eq!(policy.warnings, Vec::<String>::new());
}

#[test]
fn a_layer_after_a_locked_one_cannot_switch_the_preset_or_widen_the_scope() {
    let policy = resolve(&[
        ("operator", "locked = true\nprofile = \"shelf\"\n[network]\nallow_domains = [\"github.com\"]"),
        ("repo", "profile = \"observe\"\n[network]\nallow_domains = [\"evil.example\"]\n[paths]\nscope = [\"/\"]"),
    ]);
    assert_eq!(policy.profile, Profile::Shelf);
    assert_eq!(policy.network.allow_domains, Some(vec!["github.com".to_owned()]));
    assert_eq!(policy.paths.scope, Some(vec![".".to_owned()]), "the preset's scope was fixed by the lock");
    assert_eq!(policy.warnings.len(), 3, "{:?}", policy.warnings);
}

#[test]
fn rules_of_a_higher_layer_come_first_and_the_first_match_wins() {
    let policy = resolve(&[
        ("global", "[[rules]]\nid = \"global-allow\"\nmatch = \"^deploy\"\ndecision = \"allow\""),
        (
            "repo",
            "[[rules]]\nid = \"repo-deny\"\nmatch = \"^deploy prod\"\ndecision = \"deny\"\nreason = \"hands off\"",
        ),
    ]);
    let rule = policy.rule_for("deploy prod").expect("a rule matches");
    assert_eq!((rule.id.as_str(), rule.decision, rule.reason.as_str()), ("repo-deny", Decision::Deny, "hands off"));
    assert_eq!(policy.rule_for("deploy staging").map(|r| r.id.as_str()), Some("global-allow"));
    assert!(policy.rule_for("ls").is_none());
}

#[test]
fn a_force_push_is_rewritten_to_force_with_lease() {
    let policy = preset("guarded");
    for (before, after) in [
        ("git push -f origin main", "git push  --force-with-lease origin main"),
        ("git push --force origin main", "git push  --force-with-lease origin main"),
    ] {
        let (line, applied) = policy.rewrite(before);
        assert_eq!(applied, ["force-with-lease"], "{before}");
        assert!(line.contains("--force-with-lease"), "{line} from {after}");
    }
    let (line, applied) = policy.rewrite("git push --force-with-lease origin main");
    assert_eq!(line, "git push --force-with-lease origin main");
    assert_eq!(applied, Vec::<String>::new());
}

#[test]
fn domains_match_exactly_or_as_subdomains() {
    let policy = resolve(&[("repo", "[network]\nallow_domains = [\"github.com\"]\ndeny_domains = [\"evil.example\"]")]);
    assert!(policy.network.denies("github.com").is_none());
    assert!(policy.network.denies("api.github.com").is_none());
    assert!(policy.network.denies("notgithub.com").is_some(), "not on the allow list");
    assert!(policy.network.denies("x.evil.example").is_some());
    assert!(policy.network.denies("pastebin.com").is_some(), "the preset's deny list stays");
    assert!(Network::listed(&["a.com".to_owned()], "B.a.com"));
}

#[test]
fn an_empty_allow_list_denies_nothing_by_itself() {
    let policy = resolve(&[("repo", "[network]\nallow_domains = []")]);
    assert!(policy.network.denies("example.com").is_none());
}

#[test]
fn credential_globs_expand_the_home_directory_and_match_relative_paths() {
    let policy = preset("guarded");
    assert!(policy.paths.deny_read.is_match(&["/home/dev/.ssh/id_rsa"]));
    assert!(policy.paths.deny_read.is_match(&[".env"]));
    assert!(policy.paths.deny_read.is_match(&["/work/app/.env.production"]));
    assert!(!policy.paths.deny_read.is_match(&[".env.example"]), "templates stay readable");
    assert!(policy.paths.pii.is_match(&["fixtures/users.json"]));
    assert!(policy.paths.protected.is_match(&["/home/dev/.zshrc", "x"]));
}

#[test]
fn tool_names_are_matched_by_pattern() {
    let policy = resolve(&[("repo", "[tools]\ndeny = [\"^mcp__slack__.*\"]\nask = [\"^WebFetch$\"]")]);
    assert_eq!(policy.tool_decision("mcp__slack__post"), Some(Decision::Deny));
    assert_eq!(policy.tool_decision("WebFetch"), Some(Decision::Ask));
    assert_eq!(policy.tool_decision("Bash"), None);
}

#[test]
fn a_bad_pattern_is_an_error_naming_the_rule() {
    let layers = vec![("repo".to_owned(), layer("[[rules]]\nid = \"broken\"\nmatch = \"(\"\ndecision = \"deny\""))];
    let error = Policy::resolve(&layers, Path::new(HOME)).expect_err("bad regex");
    assert!(error.to_string().contains("broken"), "{error}");
}

#[test]
fn the_sources_say_which_layers_contributed() {
    let policy = resolve(&[("global", "profile = \"strict\""), ("repo", "")]);
    assert_eq!(policy.sources, ["preset:common", "preset:strict", "global", "repo"]);
}

#[test]
fn the_audit_log_is_on_by_default_and_a_repository_cannot_turn_off_a_locked_one() {
    let policy = resolve(&[]);
    assert!(policy.audit.enabled);
    assert_eq!(policy.audit.dir, "~/.local/share/warden/audit");
    let policy = resolve(&[
        ("operator", "locked = true\n[audit]\ndir = \"/var/log/warden\""),
        ("repo", "[audit]\nenabled = false\ndir = \"/tmp/elsewhere\""),
    ]);
    assert!(policy.audit.enabled);
    assert_eq!(policy.audit.dir, "/var/log/warden");
    assert_eq!(policy.warnings.len(), 2, "{:?}", policy.warnings);
}

#[test]
fn redaction_is_on_by_default_and_unattended_profiles_block_prompts() {
    use warden_policy::PromptMode;
    let guarded = preset("guarded");
    assert!(guarded.redact.outputs && guarded.redact.secrets && guarded.redact.mcp);
    assert_eq!(guarded.redact.prompts, PromptMode::Warn);
    assert_eq!(guarded.redact.pii.kinds, ["email", "phone", "iban", "card", "nir", "ssn"]);
    assert!(guarded.redact.pii.allow.contains(&"noreply@*".to_owned()));
    for profile in ["strict", "unattended", "shelf"] {
        assert_eq!(preset(profile).redact.prompts, PromptMode::Block, "{profile}");
    }
}

#[test]
fn a_repository_can_add_names_and_detectors_and_choose_its_kinds() {
    let policy = resolve(&[(
        "repo",
        "[redact.pii]\nnames = [\"Acme Corp\"]\nkinds = [\"email\", \"ip\"]\ncustom = [{ name = \"customer_id\", pattern = 'CUST-\\d{6}' }]\nallow = [\"*@acme.test\"]",
    )]);
    assert_eq!(policy.redact.pii.names, ["Acme Corp"]);
    assert_eq!(policy.redact.pii.kinds, ["email", "ip"]);
    assert_eq!(policy.redact.pii.custom, [("customer_id".to_owned(), "CUST-\\d{6}".to_owned())]);
    assert!(policy.redact.pii.allow.contains(&"*@acme.test".to_owned()));
}

#[test]
fn a_locked_layer_keeps_redaction_on_and_the_prompt_rule_and_the_kinds() {
    use warden_policy::{PromptMode, ReadTool};
    let policy = resolve(&[
        ("operator", "locked = true\n[redact]\nprompts = \"block\"\n[redact.pii]\nkinds = [\"email\", \"card\"]"),
        (
            "repo",
            "[redact]\noutputs = false\nsecrets = false\nmcp = false\nprompts = \"off\"\nread_tool = \"allow\"\n\
             [redact.pii]\nenabled = false\nkinds = [\"phone\"]\nallow = [\"*@anything\"]\nnames = [\"Client X\"]",
        ),
    ]);
    assert!(policy.redact.outputs && policy.redact.secrets && policy.redact.mcp);
    assert_eq!(policy.redact.prompts, PromptMode::Block);
    assert_eq!(policy.redact.read_tool, ReadTool::Deny, "the preset's deny is part of what the lock fixed");
    assert!(policy.redact.pii.enabled);
    assert_eq!(policy.redact.pii.kinds, ["email", "card", "phone"], "kinds can be added, not dropped");
    assert_eq!(policy.redact.pii.names, ["Client X"], "names only add");
    assert!(!policy.redact.pii.allow.contains(&"*@anything".to_owned()));
    assert_eq!(policy.warnings.len(), 8, "{:?}", policy.warnings);
}

#[test]
fn hidden_variables_add_up() {
    let policy = resolve(&[("a", "[env]\nhide = [\"*_TOKEN\"]"), ("b", "[env]\nhide = [\"*_SECRET\", \"*_TOKEN\"]")]);
    assert_eq!(policy.env_hide, ["*_TOKEN", "*_SECRET"]);
}
