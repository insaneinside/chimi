# chimi: a companion tool for ChaNGa: Makefile
# Copyright (C) 2014 Collin J. Sutton
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# The GNU General Public License version 2 may be found at
# <http://www.gnu.org/licenses/gpl-2.0.html>.

all: build/chimi

PY_SOURCES:=__main__.py $(wildcard chimi/*.py)
DATA_FILES:=$(sort chimi/data/host-index.yaml $(wildcard chimi/data/*.yaml chimi/data/host/*.yaml))

build/chimi: $(PY_SOURCES) $(DATA_FILES)
	(test -d build || mkdir build) && \
	zip $@.tmp $^ && \
	echo '#!/usr/bin/env python' | cat - $@.tmp > $@ && \
	rm $@.tmp && chmod +x $@

chimi/data/host-index.yaml: make-host-index.py $(wildcard chimi/data/host/*.yaml)
	python make-host-index.py > $@


.PHONY: all
