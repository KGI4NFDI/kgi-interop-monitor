"""
Command line entry point

Created on 2026-09-29

@author: danielviladrich
"""

import sys

from ngwidgets.cmd import WebserverCmd

from kgi_interop_monitor.nicekgi import KgiWebserver


class KgiCmd(WebserverCmd):
    """
    Command Line Interface
    """


def main(argv: list = None) -> int:
    """
    command line entry point

    Args:
        argv: the command line arguments, sys.argv[1:] when None

    Returns:
        the process exit code
    """
    cmd = KgiCmd(
        config=KgiWebserver.get_config(),
        webserver_cls=KgiWebserver,
    )
    exit_code = cmd.cmd_main(argv)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
