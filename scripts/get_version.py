"""Print the installed or checkout version for build scripts."""

from todometry.core.version import get_version

if __name__ == "__main__":
    print(get_version())
