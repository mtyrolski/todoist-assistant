import sys

from loguru import logger

from .automation import main


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    main()
