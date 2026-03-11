"""Allow running as `python -m sbr_config`."""

import sys

from .cli import main

sys.exit(main())
