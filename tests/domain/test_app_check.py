from datetime import UTC, datetime, timedelta

from shelf.domain.app_check import (
    REQUIRED_EVENTS,
    REQUIRED_PERMISSIONS,
    AppFacts,
    Delivery,
    Level,
    check_app,
)

NOW = datetime(2026, 11, 8, 20, 0, tzinfo=UTC)
URL = "https://shelf.example.org/api/github/webhook"


def facts(**changes: object) -> AppFacts:
    base: dict[str, object] = {
        "events": frozenset[str](REQUIRED_EVENTS),
        "permissions": dict(REQUIRED_PERMISSIONS),
        "webhook_url": URL,
        "webhook_secret_set": True,
        "deliveries": (Delivery("issue_comment", 202, NOW),),
    }
    return AppFacts(**{**base, **changes})  # type: ignore[arg-type]


def levels(found: tuple[object, ...]) -> list[Level]:
    return [finding.level for finding in found]  # type: ignore[attr-defined]


def test_a_well_set_up_app_has_nothing_to_fix() -> None:
    assert {finding.level for finding in check_app(facts(), URL)} == {Level.OK}


def test_an_app_subscribed_to_nothing_is_told_which_boxes_to_tick() -> None:
    found = check_app(facts(events=frozenset[str]()), URL)
    assert found[0].level is Level.ERROR
    assert "pull_request, issue_comment" in found[0].title
    assert "Subscribe to events" in found[0].advice
    assert "greyed" in found[0].advice


def test_extra_events_are_harmless() -> None:
    assert Level.ERROR not in levels(check_app(facts(events=frozenset({*REQUIRED_EVENTS, "push"})), URL))


def test_a_missing_or_too_low_permission_is_named_with_what_is_granted() -> None:
    found = check_app(facts(permissions={"contents": "read", "metadata": "read"}), URL)
    error = next(finding for finding in found if "permissions" in finding.title)
    assert error.level is Level.ERROR
    assert "contents (write needed, read granted)" in error.title
    assert "issues (write needed, none granted)" in error.title


def test_a_higher_permission_than_needed_is_fine() -> None:
    permissions = {**REQUIRED_PERMISSIONS, "checks": "write"}
    assert Level.ERROR not in levels(check_app(facts(permissions=permissions), URL))


def test_a_webhook_url_that_is_not_ours_is_an_error_showing_both() -> None:
    found = check_app(facts(webhook_url="https://old.example.org/hook"), URL)
    assert found[0].level is Level.ERROR
    assert "https://old.example.org/hook" in found[0].title
    assert URL in found[0].title


def test_a_trailing_slash_does_not_matter() -> None:
    assert Level.ERROR not in levels(check_app(facts(webhook_url=URL + "/"), URL))


def test_no_webhook_secret_is_an_error() -> None:
    found = check_app(facts(webhook_secret_set=False), URL)
    assert found[0].level is Level.ERROR
    assert "GITHUB_WEBHOOK_SECRET" in found[0].advice


def test_no_delivery_at_all_is_a_warning_that_says_how_to_provoke_one() -> None:
    found = check_app(facts(deliveries=()), URL)
    assert found[0].level is Level.WARNING
    assert "Comment on a pull request" in found[0].advice


def test_a_signature_refusal_points_at_the_secret() -> None:
    found = check_app(facts(deliveries=(Delivery("issue_comment", 401, NOW),)), URL)
    assert found[0].level is Level.ERROR
    assert "signature" in found[0].title
    assert "GITHUB_WEBHOOK_SECRET" in found[0].advice


def test_a_delivery_that_never_arrived_points_at_the_address() -> None:
    found = check_app(facts(deliveries=(Delivery("issue_comment", 0, NOW),)), URL)
    assert found[0].level is Level.ERROR
    assert "could not reach" in found[0].title


def test_the_latest_delivery_decides_and_earlier_failures_only_warn() -> None:
    deliveries = (
        Delivery("issue_comment", 401, NOW - timedelta(hours=2)),
        Delivery("issue_comment", 202, NOW),
    )
    found = check_app(facts(deliveries=deliveries), URL)
    assert Level.ERROR not in levels(found)
    assert any(finding.level is Level.WARNING and "1 of the last 2" in finding.title for finding in found)


def test_the_most_serious_finding_comes_first() -> None:
    found = check_app(facts(webhook_secret_set=False, deliveries=()), URL)
    assert levels(found) == sorted(levels(found), key=[Level.ERROR, Level.WARNING, Level.OK].index)


def test_the_workflows_permission_is_off_by_default_and_that_is_fine() -> None:
    found = check_app(facts(), URL)
    note = next(finding for finding in found if "CI workflow files" in finding.title)
    assert note.level is Level.OK
    assert "cannot change" in note.title


def test_a_granted_workflows_permission_is_accepted_and_names_the_safeguards() -> None:
    permissions = {**REQUIRED_PERMISSIONS, "workflows": "write"}
    found = check_app(facts(permissions=permissions), URL)
    note = next(finding for finding in found if "CI workflow files" in finding.title)
    assert note.level is Level.OK
    assert "CODEOWNERS" in note.advice
    assert "required reviewers" in note.advice


def test_an_app_without_the_actions_permission_is_an_error_because_the_developer_cannot_read_a_failing_log() -> None:
    permissions = {name: level for name, level in REQUIRED_PERMISSIONS.items() if name != "actions"}
    found = check_app(facts(permissions=permissions), URL)
    error = next(finding for finding in found if "permissions" in finding.title)
    assert error.level is Level.ERROR
    assert "actions (read needed, none granted)" in error.title
