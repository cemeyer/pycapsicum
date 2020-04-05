# Copyright 2020 Conrad Meyer <cem@FreeBSD.org>
#
# SPDX-License-Identifier: WTFNMFPL-1.0

import functools
import linecache
import multiprocessing as mp
import re
import sys
import traceback


cov_handle = None


def _do_nothing(*args):
    pass


# One-off monkey-patch of format_exception ...
__format_exception = traceback.format_exception
def _format_exception(etype, value, tb, limit=None):
    msg = ['Traceback (most recent call last):\n']

    tbdat = []
    for i, (fname, lno, methnam, linestr) in enumerate(value.tbdat):
        # Elide implementation details that don't help debug test failures.
        if i == 0 and methnam == "_remote_wrapper":
            continue
        # Py unittest result _exc_info_to_string attempts to skip the
        # implementation of assertions.  This method is more crude, but
        # whatever.
        elif re.match(r'.*thon\d.\d\/unittest\/', fname):
            continue

        if linestr is None:
            linestr = linecache.getline(fname, lno)
            if linestr:
                linestr = linestr.strip()
            else:
                linestr = None

        tbdat.append((fname, lno, methnam, linestr))

    result = traceback.format_list(tbdat)
    result += traceback.format_exception_only(etype, value)
    traceback.format_exception = __format_exception
    return result


# Py3000 rototills traceback and uses something called TracebackException instead.
if sys.version_info >= (3, 0):
    _TracebackException = traceback.TracebackException
    class MonkeyPatchTraceBack(traceback.TracebackException):
        def __init__(self, etype, value, *args, **kwargs):
            super().__init__(etype, value, *args, **kwargs)
            self.value = value
            traceback.TracebackException = _TracebackException

        def format(self, *args, **kwargs):
            for x in _format_exception(self.exc_type, self.value, None):
                yield x


# In a remote process, run the test and send pickled test result (None for
# success, exception for all other conditions) back to the runner.
def _remote_wrapper(target, args, resultq):
    try:
        if sys.version_info >= (3, 2):
            # Avoid useless noise ResourceWarning on Py3000 for ephemeral test
            # processes:
            import warnings
            warnings.filterwarnings("ignore", "", ResourceWarning, "", 0)

        # Preopen linecache so that exception traces have (some) code contents
        # from this end of things.  We can't predict in advance what files will
        # be needed, and can't open files after capsicum entry.
        if sys.version_info >= (3, 0):
            # Another gratuitous Python3 API change ...
            fnam = target.__code__.co_filename
        else:
            fnam = target.func_code.co_filename

        # Cache lines from the file of the test case itself.  Any missing lines
        # we'll be able to fill on the test-runner side afterwards (assuming
        # files contents don't change racily).
        linecache.getlines(fnam)

        # Prevent linecache from destroying its cache when it can't stat the
        # files from the sandbox.
        linecache.checkcache = _do_nothing

        # Run the dang wrapped test!
        target(*args)
    except:
        # Can't pickle tracebacks, so extract most metadata and pickle that
        # instead.
        einfo = sys.exc_info()
        einfo = einfo[:2] + (traceback.extract_tb(einfo[2]),)

        resultq.put(einfo)
    else:
        resultq.put(None)
    finally:
        # Coverage-py needs some help to actually emit data from the forked
        # process.  Not sure why the atexit handler is not honored.  Perhaps
        # they are cleared on fork.
        if cov_handle is not None:
            cov_handle.stop()
            cov_handle.save()


# Decorator: Run a test in a subprocess, to isolate effects (principally,
# capsicum sandboxing).
def _process_isolate(f):
    @functools.wraps(f)
    def wrapper(test, subprocess=False):
        q = mp.Queue()
        p = mp.Process(target=_remote_wrapper, args=(f, (test,), q))
        p.start()
        p.join()

        # XXX Notably missing:
        # 1. Handle of remote process death for any reason that isn't a Python
        # exception or otherwise doesn't get serialized into anything for this
        # Queue.  (E.g., fatal signal.)
        # 2. Any sort of timeout mechanism.  Granted, we don't have that
        # anyway.
        res = q.get_nowait()
        if res is None:
            return

        # Re-raise exception
        if sys.version_info >= (3, 0):
            traceback.TracebackException = MonkeyPatchTraceBack
        else:
            traceback.format_exception = _format_exception
        res[1].tbdat = res[2]
        raise res[1]
    return wrapper
