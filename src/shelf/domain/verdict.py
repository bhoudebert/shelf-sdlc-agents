"""Reading a reviewer's answer: free text that ends with a verdict line."""

import re

from shelf.domain.work import Reviewed, Verdict

_LINE = re.compile(r"^\s*VERDICT:\s*(APPROVE|CHANGES|ESCALATE)\s*$", re.IGNORECASE | re.MULTILINE)


_REPEATED = re.compile(r"^\s*REPEATED:\s*(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
_BLOCKING = re.compile(r"^\s*BLOCKING:\s*(yes|no)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_verdict(answer: str) -> Reviewed:
    """Take the last ``VERDICT:`` line as the verdict and everything before it as the issues.

    A reviewer that gives no verdict is not trusted to have approved: the work goes to a person.
    """
    matches = list(_LINE.finditer(answer))
    if not matches:
        return Reviewed(Verdict.ESCALATE, f"The reviewer gave no verdict.\n\n{answer.strip()}".strip())
    last = matches[-1]
    body = answer[: last.start()]
    repeated = [int(found.group(1)) for found in _REPEATED.finditer(body)]
    blocking = [found.group(1).lower() == "yes" for found in _BLOCKING.finditer(body)]
    return Reviewed(
        Verdict(last.group(1).lower()),
        body.strip(),
        repeated=repeated[-1] if repeated else 0,
        blocking=blocking[-1] if blocking else True,
    )
