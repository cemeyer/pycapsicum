# Copyright 2020 Conrad Meyer <cem@FreeBSD.org> (file encoding=utf-8)
#
# SPDX-License-Identifier: WTFNMFPL-1.0

import errno
import os
import sys

from _cap_cffi import lib as _cap
from _cap_cffi import ffi as _cffi


# Don't use import *.
__all__ = []


__doc__ = """
cap is a Python API wrapper for FreeBSD's capsicum(4)¹ sandbox using CFFI.

Capsicum is a lightweight OS capability sandbox.  It can be used for
application and library compartmentalization; privilege separation into
isolated, sandboxed components; and to limit the impact of software
vulnerabilities.

There are two core concepts:

    - Capability mode (sandbox)

        A sandbox where access to global OS namespaces (such as the filesystem)
        is restricted.  Only explicitly delegated rights, referenced by memory
        mappings or file descriptors, may be used.  Once entered (with
        cap.enter()), sandbox mode cannot be escaped.  Child processes inherit
        sandbox mode; there is no escape.

    - Capabilities

        Limits to the set of operations which may be performed on file
        descriptors.  For example, an fd may be restricted such that read(2)
        and write(2) are permitted, but not fchmod(2).  The complete list of
        rights can be found in the rights(4) manual page².

The C documentation is a good reference point for understanding how to write
secure programs using Capsicum.

[1]: https://www.freebsd.org/cgi/man.cgi?query=capsicum&sektion=4
[2]: https://www.freebsd.org/cgi/man.cgi?query=rights&sektion=4
"""

# Not a real capsicum macro, but represents (by pointer value) all rights /
# unrestricted rights.
_ALL = object()


# Cache of used cap_rights_t objects to avoid repeated libc initialization
# calls.
_rights_cache = {}
def _rights_cache_get(fset):
    try:
        return _rights_cache[fset]
    except KeyError:
        robj = Rights(fset)
        _rights_cache[fset] = robj
        return robj


# Cache of used cap.Fcntl objects to avoid excessive object spam for what
# amounts to, at most, maybe 16 different integers.
_fcntls_cache = {}


# Cache of all single-right objects, created only on-demand.
class _right:
    """
    A cache of common, reuable cap_rights_t objects.  Use of these objects is a
    small performance optimization compared to constructing new objects every
    time the rights are needed.

    One may replace:
        cap.limit(my_fd, cap.Rights({cap.READ}))
    with:
        cap.limit(my_fd, cap.right.READ)

    In addition to single capabilities like cap.READ, two special values are
    defined:

        cap.right.NONE
        cap.right.ALL

    They represent cap_rights_t objects containing no capabilities, and all
    capabilities, respectively.
    """

    _allnyms = None

    def __getattr__(self, attr):
        if attr not in self._allnyms:
            return super(type(self)).__getattribute__(attr)

        if attr == "NONE":
            robj = Rights(None)
        elif attr == "ALL":
            robj = Rights(_ALL)
        else:
            robj = _rights_cache_get(frozenset((globals()[attr],)))
        setattr(self, attr, robj)
        return robj


# Export Capsicum C macro constants as API.
def _once():
    # Hide in a function to prevent leaking names into module namespace.
    gl = globals()
    nyms = []
    for nym, val in _cap.__dict__.items():
        if not nym.startswith("CAP_") or "UNUSED" in nym or nym == "CAP_ALL":
            continue

        nym = nym[4:]

        gl[nym] = val
        nyms.append(nym)
    _right._allnyms = frozenset(nyms + ["ALL", "NONE"])
_once()
del _once


right = _right()
del _right


# Needless backwards compatibility breakage in Py3k.
try:
    long
except NameError:
    _number = int
else:
    _number = (int, long)

def _fdorfilelikeobj(foo):
    if isinstance(foo, _number):
        return foo
    try:
        return foo.fileno()
    except AttributeError:
        pass
    return None


def _posixerror(*filename):
    error = _cffi.errno
    raise OSError(error, os.strerror(error), *filename)


def enter():
    """
    cap.enter() causes the current process to enter capsicum(4) capability mode
    (i.e., sandboxed).  See cap_enter(2)¹.

    In the sandbox, the process may only issue system calls operating on file
    descriptors and access some limited global state (read only).  Access to
    global namespaces, such as the filesystem or IPC namespaces, is prevented.
    Once a process is in the sandbox, it cannot escape.  Nor can any child
    processes it creates.

    System calls that are prevented by the sandbox return error codes
    ENOTCAPABLE or ECAPMODE.  (By convention, Python raises C errnos as
    exceptions derived from EnvironmentError).  Unfortunately, Python's errno
    module does not define these error values on FreeBSD (in any version of
    Python).  So the constants are exported by this module, in case users would
    find it helpful to detect them programmatically: cap.ENOTCAPABLE and
    cap.ECAPMODE.

    [1]: https://www.freebsd.org/cgi/man.cgi?query=cap_enter&sektion=2
    """
    rc = _cap.cap_enter()
    if rc < 0 and _cffi.errno != errno.ENOSYS:  # pragma: no cover
        _posixerror()


def fcntls_limit(fd, fcntls):
    """
    cap.fcntls_limit(fd, fcntls) limits the fcntl(2) commands a program may
    issue on fd to the set represented by fcntls.  The limit is only meaningful
    if the fd has the cap.FCNTL right.  (If the fd does not have cap.FCNTL, no
    fcntl commands are permitted.)

    fd is an integer file descriptor.  fcntls is a cap.Fcntls() object.

    Like cap.limit(), the allowed fcntl commands for a given fd can be reduced,
    but never expanded.  See cap_fcntls_limit(2):
    https://www.freebsd.org/cgi/man.cgi?query=cap_fcntls_limit&sektion=2
    """

    rc = _cap.cap_fcntls_limit(fd, fcntls._flags)
    if rc < 0:
        _posixerror()


def ioctls_limit(fd, ioctls):
    """
    cap.ioctls_limit(fd, ioctls) limits the ioctl(2) commands a program may
    issue on fd to the set represented by ioctls.  The limit is only meaningful
    if the fd has the cap.IOCTL right.  (If the fd does not have cap.IOCTL, no
    ioctl commands are permitted.)

    fd is a file descriptor.  ioctls is a cap.Ioctls() object.

    Like cap.limit(), the allowed ioctl commands for a given fd can be reduced,
    but never expanded.  See cap_ioctls_limit(2):
    https://www.freebsd.org/cgi/man.cgi?query=cap_ioctls_limit&sektion=2
    """

    # None represents CAP_IOCTLS_ALL; no restriction.
    if ioctls._ioctls is None:
        return

    rc = _cap.cap_ioctls_limit(fd, ioctls._ioctls, len(ioctls._ioctls))
    if rc < 0:
        _posixerror()


def limit(fd, rights):
    """
    cap.limit(fd, rights) limits the operations the program can perform on fd
    to those permitted by the rights parameter.

    fd is a file descriptor.  rights is a cap.Rights() object.

    Rights may always be reduced, but never expanded.  See cap_rights_limit(2):
    https://www.freebsd.org/cgi/man.cgi?query=cap_rights_limit&sektion=2
    """
    rc = _cap.cap_rights_limit(fd, rights._rights)
    if rc < 0:
        _posixerror()


def openat(dfd, path, flags, mode=0):
    """
    cap.openat(dir_fd, path, flags, mode=0) is a convenience helper that
    performs essentially:

        fd = os.open(path, flags, mode, dir_fd=dir_fd)
        return os.fdopen(fd, ...)

    In capability mode, all absolute path APIs — such as normal Python open() —
    are forbidden.  Instead, only lookups relative to a directory fd with
    cap.LOOKUP are permitted.  Python does not make this especially ergonomic:
    os.open() has an awkward dir_fd= keyword parameter in Python 3.3+, but that
    just gives you a raw fd; and Python has no dir_fd-relative open operation
    at all in older versions than 3.3.

    cap.openat() gives you a file-like object with a single function
    convenience.  Files opened this way inherit capabilities from the provided
    dir_fd — so if you want to write the file, the dir_fd must have cap.WRITE.

    Additionally, Python's os.fdopen() routine wants fstat() and fcntl(F_GETFL)
    on the new fd, so these privileges (cap.FSTAT, cap.FCNTL) must be present
    on the dir_fd.  (And if fcntls are limited on dir_fd, cap.fcntl.GETFL must
    be permitted.)
    """
    if sys.version_info >= (3, 3):
        py_openat = os.open
    else:
        py_openat = compat33.open
    fd = py_openat(path, flags, mode, dir_fd=dfd)

    accmode = (flags & _cap.O_ACCMODE)
    smode = None
    if accmode == os.O_RDONLY:
        smode = "rb"
    elif accmode == os.O_RDWR:
        smode = "r+b"
    elif accmode == os.O_WRONLY:  # pragma: no branch
        smode = "wb"

    return os.fdopen(fd, smode)


def sandboxed():
    """
    The cap.sandboxed() predicate returns True if the current process is
    running in the capability mode sandbox.  See cap_sandboxed(3):

    https://www.freebsd.org/cgi/man.cgi?query=cap_sandboxed&sektion=3
    """
    return _cap.cap_sandboxed()


class Rights(object):
    """
    cap.Rights() represents a single, immutable cap_rights_t object.

    cap_rights_t objects are essentially small bitsets representing a set of
    privileges.

    The complete list of capability rights can be found in the rights(4) manual
    page: https://www.freebsd.org/cgi/man.cgi?query=rights&sektion=4
    """

    _ULL = "unsigned long long"

    def __new__(cls, rights=None):
        try:
            rights = frozenset(rights)
            res = _rights_cache.get(rights, None)
            if res is not None:
                return res
        except TypeError:
            pass
        return super(Rights, cls).__new__(cls)


    def __init__(self, rights=None):
        """
        Create a new cap_rights_t object.

        The optional rights argument may be another Rights object, a file-like
        object, or an iteration (e.g., a tuple, set, or list) containing only
        valid capability flags.

        Rights(), Rights(None), and Rights([]) are equivalent.  They all create
        a Rights object representing the empty set (no privileges).

        If the rights argument is another Rights object, the object is copied.

        If the rights argument is an integer fd, or a file-like object backed
        by a file descriptor (::fileno()), the resulting Rights object
        represents the set of privileges currently held by that file
        descriptor.  (See cap_rights_get(3).)

        If the rights argument is an iterable containing valid capability
        flags, the resulting object represents the set containing those
        capabilities.  E.g., cap.Rights({cap.READ, cap.LOOKUP}).  (See
        cap_rights_init(3).)

        https://www.freebsd.org/cgi/man.cgi?query=cap_rights_init&sektion=3
        """

        self._rights = _cffi.new("cap_rights_t *")
        if rights is None:
            args = []
        elif rights is _ALL:
            _cap.CAP_ALL(self._rights)
            return
        elif isinstance(rights, type(self)):
            _cffi.memmove(self._rights, rights._rights, _cffi.sizeof(self._rights[0]))
            return
        else:
            fd = _fdorfilelikeobj(rights)
            if fd is not None:
                # Workaround for stupid Python __ name-jacking.
                rc = getattr(_cap, '__cap_rights_get')(_cap.CAP_RIGHTS_VERSION, fd, self._rights)
                if rc < 0:
                    _posixerror()
                return

            args = [_cffi.cast(self._ULL, x) for x in rights]
        args.append(_cffi.cast(self._ULL, 0))
        # Workaround for stupid Python __ name-jacking.
        getattr(_cap, '__cap_rights_init')(_cap.CAP_RIGHTS_VERSION, self._rights, *args)


class _fcntl:
    """
    The cap.fcntl object is just a namespace for CAP_FCNTL_* values.

    See cap_fcntls_limit(2):
    https://www.freebsd.org/cgi/man.cgi?query=cap_fcntls_limit&sektion=2
    """
    GETFL = _cap.CAP_FCNTL_GETFL
    SETFL = _cap.CAP_FCNTL_SETFL
    GETOWN = _cap.CAP_FCNTL_GETOWN
    SETOWN = _cap.CAP_FCNTL_SETOWN
    ALL = _cap.CAP_FCNTL_ALL
fcntl = _fcntl()
del _fcntl


class Fcntls(object):
    """
    cap.Fcntls() represents a set of permitted fcntl(2) commands.

    The complete set of capability mode fcntl(2) commands is:

        cap.fcntl.GETFL
        cap.fcntl.SETFL
        cap.fcntl.GETOWN
        cap.fcntl.SETOWN

    Additionally, cap.fcntl.ALL represents all of the above.
    """

    _VALID = frozenset({fcntl.GETFL, fcntl.SETFL, fcntl.GETOWN,
        fcntl.SETOWN, fcntl.ALL,
        })

    def __new__(cls, fcntls=None):
        insert_res = False
        try:
            if fcntls is None:
                fcntls = []
            fcntls = frozenset(fcntls)
            return _fcntls_cache[fcntls]
        except KeyError:
            insert_res = True
        except TypeError:
            pass
        obj = super(Fcntls, cls).__new__(cls)
        if insert_res:
            _fcntls_cache[fcntls] = obj
        return obj


    def __init__(self, fcntls=None):
        """
        Create a new cap.Fcntls object.

        The optional fcntls argument may be another Fcntls object, a file-like
        object, or an iteration (e.g., a tuple, set, or list) containing only
        valid cap.fcntl.* flags.

        Fcntls(), Fcntls(None), and Fcntls([]) are equivalent.  They all create
        an Fcntls object representing the empty set (no privileges).

        If the fcntls argument is another Fcntls object, the object is copied.

        If the fcntls argument is an integer fd, or a file-like object backed
        by a file descriptor (::fileno()), the resulting Fcntls object
        represents the set of privileges currently held by that file
        descriptor.  (See cap_fcntls_get(3)¹.)

        If the fcntls argument is an iterable containing valid cap.fcntl.*
        flags, the resulting object represents the capability set containing
        those fcntl(2) commands.  E.g.,

            cap.Fcntls({cap.fcntl.GETFL, cap.fcntl.SETFL})

        [1]: https://www.freebsd.org/cgi/man.cgi?query=cap_fcntls_get&sektion=2
        """

        if fcntls is None:
            self._flags = 0
            return

        if isinstance(fcntls, type(self)):
            self._flags = fcntls._flags
            return

        fd = _fdorfilelikeobj(fcntls)
        if fd is not None:
            u32 = _cffi.new("uint32_t *")
            rc = _cap.cap_fcntls_get(fd, u32)
            if rc < 0:
                _posixerror()
            self._flags = int(u32[0])
            return

        flags = 0
        for x in fcntls:
            if x not in self._VALID:
                raise ValueError(
                    "{}: Not a valid capsicum fcntl capability flag".format(x))
            flags = flags | x
        self._flags = flags


class Ioctls:
    """
    cap.Ioctls() represents a logical set of permitted ioctl(2) commands.
    """

    def __init__(self, ioctls=None):
        """
        Create a new cap.Ioctls object.

        The optional ioctls argument may be another Ioctls object, a file-like
        object, or an iteration (e.g., a tuple, set, or list) containing
        FreeBSD ioctl(2) commands (integers).

        Ioctls(), Ioctls(None), and Ioctls([]) are equivalent.  They all create
        an Ioctls object representing the empty set (no privileges).

        If the ioctls argument is another Ioctls object, the object is copied.

        If the ioctls argument is an integer fd, or a file-like object backed
        by a file descriptor (::fileno()), the resulting Ioctls object
        represents the set of privileges currently held by that file
        descriptor.  (See cap_ioctls_get(3)¹.)

        If the ioctls argument is an iterable, the resulting object represents
        the capability set containing those ioctl(2) commands.  E.g.,

            cap.Ioctls({termios.FIONREAD, termios.TIOCGETD})

        [1]: https://www.freebsd.org/cgi/man.cgi?query=cap_ioctls_get&sektion=2
        """

        if ioctls is None:
            self._ioctls = []
            return

        if isinstance(ioctls, type(self)):
            if ioctls._ioctls is None:
                self._ioctls = None
            else:
                self._ioctls = ioctls._ioctls[:]
            return

        fd = _fdorfilelikeobj(ioctls)
        if fd is not None:
            rc = _cap.cap_ioctls_get(fd, _cffi.NULL, 0)
            if rc < 0:
                _posixerror()
            if rc == _cap.CAP_IOCTLS_ALL:
                # Unrestricted.
                self._ioctls = None
                return

            capacity = rc
            storage = _cffi.new("unsigned long[]", capacity)
            rc = _cap.cap_ioctls_get(fd, storage, capacity)
            if rc < 0:  # pragma: no cover
                _posixerror()
            if rc == _cap.CAP_IOCTLS_ALL or rc > capacity:  # pragma: no cover
                # This should not happen; the fd has gone from restricted to
                # 'capacity' ioctls to unrestricted, or less restricted.  This
                # can only happen if there is a race condition where the fd is
                # closed in another thread and reassigned by an operation which
                # allocates another fd.
                _cffi.errno = errno.EBADF
                _posixerror()

            ioctls = storage[0:rc]
            # FALLTHROUGH

        # No realistic way to validate the set of valid ioctls at this
        # layer.
        self._ioctls = [_cffi.cast("unsigned long", x) for x in ioctls]


# Export C macro constants as API.
AT_FDCWD = _cap.AT_FDCWD
ECAPMODE = _cap.ECAPMODE
ENOTCAPABLE = _cap.ENOTCAPABLE
if sys.version_info < (3, 3):
    O_CLOEXEC = _cap.O_CLOEXEC
else:
    O_CLOEXEC = os.O_CLOEXEC


if sys.version_info < (3, 3):
    class compat33:
        _olistdir = os.listdir

        @staticmethod
        def open(path, flag, mode=0o777, dir_fd=None):
            """
            open(path, flag [, mode=0o777 [, dir_fd=None]]) -> fd

            Open a file descriptor (integer) for low level IO.

            If dir_fd is not None, it should be a file descriptor open to a
            directory; path will be interpreted relative to that directory.
            See openat(2).

            The O_CLOEXEC flag is always set, even if not specified by the
            user.
            """
            if isinstance(path, unicode):
                path = path.encode(sys.getfilesystemencoding())
            if dir_fd is None:
                dir_fd = _cap.AT_FDCWD
            flag = int(flag) | _cap.O_CLOEXEC

            while True:
                fd = _cap.openat(dir_fd, path, flag, _cffi.cast("int", mode))
                if fd >= 0 or (fd < 0 and _cffi.errno != errno.EINTR):  # pragma: no cover
                    break

            if fd < 0:
                _posixerror(path)

            return fd

        @staticmethod
        def listdir(path):
            """
            listdir(path) -> list_of_strings

            Return a list containing the names of the entries in the directory.

            path can be specified as either unicode, bytes, or an integer file
            descriptor referring to a directory.

            The list is in arbitrary order.  It does not include the special
            entries '.' and '..'.
            """
            if not isinstance(path, (int, long)):
                return compat33._olistdir(path)

            res = []
            fdup = os.dup(path)
            if fdup < 0:  # pragma: no cover
                _posixerror()

            dirp = _cap.fdopendir(fdup)
            if dirp == _cffi.NULL:  # pragma: no cover
                os.close(fdup)
                _posixerror()

            try:
                while True:
                    _cffi.errno = 0
                    de = _cap.readdir(dirp)
                    if de == _cffi.NULL:
                        if _cffi.errno != 0:  # pragma: no cover
                            _posixerror()
                        break

                    nam = _cffi.string(de.d_name)
                    if nam not in {'.', '..'}:  # pragma: no branch
                        res.append(nam)
            finally:
                rc = _cap.closedir(dirp)
                if rc < 0 and sys.exc_info()[0] is None:  # pragma: no cover
                    _posixerror()

            return res
