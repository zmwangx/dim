# dim

[![download](https://img.shields.io/badge/download-dim.py-brightgreen.svg)](https://raw.githubusercontent.com/zmwangx/dim/master/dim.py)
[![docs](https://img.shields.io/badge/documentation-dev-brightgreen.svg)](https://docs.tcl.sh/py/dim/)
[![travis](https://travis-ci.org/zmwangx/dim.svg?branch=master)](https://travis-ci.org/zmwangx/dim/)
[![codecov](https://codecov.io/gh/zmwangx/dim/branch/master/graph/badge.svg)](https://codecov.io/gh/zmwangx/dim)

`dim` is an HTML parser and simple DOM implementation with CSS selector support.

`dim`

- is a single module;
- has no dependency outside PSL;
- is not crazy long;
- supports Python 3.5 and forward,

so the file could be directly embedded in any Python 3.4+ application, or even in a monolithic source file.

`dim` is strictly typed and fully documented. Documentation is available at <https://docs.tcl.sh/py/dim/>.

## Development

`make init` installs dev dependencies via `pipenv`.

`pipenv run make` or just `make` runs checks (type, style, etc.) and tests, and builds docs.

See `Makefile` for details.

`Pipfile` is provided solely for development purposes. (As pointed out above, `dim` itself is plug and play.)

## License

Copyright © 2018 Zhiming Wang <i@zhimingwang.org>

This work is free. You can redistribute it and/or modify it under the
terms of the Do What The Fuck You Want To Public License, Version 2,
as published by Sam Hocevar. See the COPYING file for more details.
