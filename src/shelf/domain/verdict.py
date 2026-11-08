"""Reading a reviewer's answer: free text that ends with a verdict line."""

import re

from shelf.domain.work import Reviewed, Verdict

_LINE = re.compile(r"^\s*VERDICT:\s*(APPROVE|CHANGES|ESCALATE)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_verdict(answer: str) -> Reviewed:
    """Take the last ``VERDICT:`` line as the verdict and everything before it as the issues.

    A reviewer that gives no verdict is not trusted to have approved: the work goes to a person.
    """
    matches = list(_LINE.finditer(answer))
    if not matches:
        return Reviewed(Verdict.ESCALATE, f"The reviewer gave no verdict.\n\n{answer.strip()}".strip())
    last = matches[-1]
    return Reviewed(Verdict(last.group(1).lower()), answer[: last.start()].strip())
