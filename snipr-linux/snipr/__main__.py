"""Entry point for python -m snipr."""

import sys


def main():
    from snipr.app import SniprApplication

    app = SniprApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
