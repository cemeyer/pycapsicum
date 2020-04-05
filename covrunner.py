# Copyright 2020 Conrad Meyer <cem@FreeBSD.org> (file encoding=utf-8)
#
# SPDX-License-Identifier: WTFNMFPL-1.0

from __future__ import print_function

import os
import sys
import types
import unittest

import tests.util

import coverage


# Convenient object we can hang arbitrary fields off of.
state = lambda: None


def patch_write_file(self, filename):
    if self._debug and self._debug.should('dataio'):
        self._debug.write("Writing data to %r" % (filename,))

    assert filename.startswith(state.dir_path)
    fname = filename[len(state.dir_path) + 1:]

    import cap
    if cap.sandboxed():
        print("\n ↳ Writing", fname, "in", state.dir_path, "(sandboxed test)")

    # coverage.py expects a string-mode handle, unfortunately.
    if sys.version_info < (3, 3):
        myopen = cap.compat33.open
    else:
        myopen = os.open

    rfd = myopen(fname, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644,
        dir_fd=state.dir_fd)
    with os.fdopen(rfd, "wt") as fdata:
        self.write_fileobj(fdata)


def print_annotated(cov):
    # Hijack output for annotation reporter, which does not provide configurable output...
    import io
    oo = io.open
    io.open = lambda x, y, **z: sys.stdout
    r = coverage.annotate.AnnotateReporter(cov, cov.config)
    r.report(None, directory=None)
    io.open = oo


def main():
    coverage.CoverageData
    cov = coverage.Coverage(branch=True)
    cov.start()

    # CoverageDataFiles obj
    state.dir_path = os.path.dirname(cov.data_files.filename)
    state.dir_fd = os.open(state.dir_path, os.O_RDONLY)

    # Pass handle to tests.util so it can explicitly stop and save on exit.
    # I'm not sure why the atexit handler doesn't do this for us automatically.
    tests.util.cov_handle = cov

    # CoverageData obj
    cov.data.write_file = types.MethodType(patch_write_file, cov.data)

    unittest.main(module='tests.test_cap', verbosity=3, exit=False)

    cov.stop()

    # N.B., intentionally combining results from prior runs (.coverage) so we
    # can get coverage for py2+py3 test runs.
    cov.combine(strict=True)
    cov.data_suffix = "py" + "".join([str(x) for x in sys.version_info[:2]])
    cov.save()

    # Emit already-combined results with no suffix as well, because 'coverage
    # xml' is too dumb to look for suffixed files.
    cov.data_suffix = None
    cov.save()

    # For Cirrus logs
    cov.report(file=sys.stdout)


if __name__ == "__main__":
    main()
