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


state = lambda: None


def patch_write_file(self, filename):
    if self._debug and self._debug.should('dataio'):
        self._debug.write("Writing data to %r" % (filename,))

    assert filename.startswith(state.dir_path)
    fname = filename[len(state.dir_path) + 1:]

    import cap
    if cap.sandboxed():
        print("\n ↳ Writing", fname, "in", state.dir_path, "(sandboxed test)")
    with cap.openat(state.dir_fd, fname, os.O_WRONLY | os.O_CREAT, 0644) as fdata:
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
    cov.combine(strict=True)
    cov.save()

    # For Cirrus logs
    cov.report(file=sys.stdout)

    # Emit coverage.xml so covdata doesn't have to grovel for it quite as much.
    cov.xml_report()


if __name__ == "__main__":
    main()
