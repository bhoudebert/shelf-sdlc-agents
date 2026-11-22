"""The environment a step gives its commands beyond what the runner sets. Pure: no I/O.

The runner knows nothing of what the worker installed into the repository's home, so a step reads its own home and asks
here what to add (decision 0019).
"""

from collections.abc import Mapping, Sequence
from typing import Final

JDKS: Final = ".local/share/mise/installs/java"
"""Where mise puts each JDK it installs, under the home, one folder per version."""


def jdk_environment(env: Mapping[str, str], home: str, installed: Sequence[str]) -> dict[str, str]:
    """``JAVA_HOME`` and a ``PATH`` that starts with its ``bin`` for the one JDK in ``installed``, else nothing.

    ``./mvnw`` and ``java`` then work whether or not the tool shims do. A ``JAVA_HOME`` that is set is the person's or
    the repository's own and is left alone; with several JDKs the shims, which read the repository's declaration,
    decide.
    """
    if env.get("JAVA_HOME"):
        return {}
    names = [name for name in installed if name and "/" not in name and name not in {".", ".."} and ".." not in name]
    if len(names) != 1 or len(installed) != 1:
        return {}
    java_home = f"{home}/{JDKS}/{names[0]}"
    path = env.get("PATH", "")
    return {"JAVA_HOME": java_home, "PATH": f"{java_home}/bin:{path}" if path else f"{java_home}/bin"}
