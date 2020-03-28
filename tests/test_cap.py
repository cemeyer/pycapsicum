# Copyright 2020 Conrad Meyer <cem@FreeBSD.org>
#
# SPDX-License-Identifier: WTFNMFPL-1.0

import errno
import fcntl as py_fcntl
import os
import sys
import termios
import unittest

if sys.version_info >= (3, 2):
    import warnings

from . import util

sys.path.append("..")
import cap


my_filename = os.path.basename(__file__).rstrip("co")
my_dirname = os.path.dirname(__file__)


class TestPyAPI(unittest.TestCase):
    def setUp(self):
        # Avoid useless noise ResourceWarning on Py3000 for ephemeral test
        # processes:
        if sys.version_info >= (3, 2):
            warnings.filterwarnings("ignore", "", ResourceWarning, "", 0)

    @unittest.skipIf(sys.version_info >= (3, 3), "irrelevant for newer Python")
    def test_compat33_names(self):
        cap.compat33.open
        cap.compat33.listdir

    def test_demo_names(self):
        cap.enter
        cap.Rights
        cap.openat
        cap.right
        cap.right.READ
        cap.limit

    def test_more_names(self):
        cap.sandboxed
        cap.Fcntls
        cap.fcntl
        cap.fcntls_limit
        cap.Ioctls
        cap.ioctls_limit
        cap.AT_FDCWD
        cap.O_CLOEXEC
        cap.right.ALL
        cap.right.NONE

    @util._process_isolate
    def test_sandbox_trivial(self):
        self.assertFalse(cap.sandboxed())
        cap.enter()
        self.assertTrue(cap.sandboxed())

    # cap_rights_limit, etc.
    def test_rights_obj(self):
        cap.Rights()
        cap.Rights({cap.READ})
        cap.Rights({cap.READ, cap.WRITE})

    def test_right_cache(self):
        cap.right.READ
        cap.right.LOOKUP
        cap.right.MMAP_R

    def test_right_cache_negative(self):
        with self.assertRaises(AttributeError):
            cap.right.DoesNotExist

    @util._process_isolate
    def test_limit_trivial(self):
        fd = os.open("/dev/zero", os.O_RDONLY)

        cap.enter()
        self.assertTrue(cap.sandboxed())

        # Unrestricted fds have full privileges after entering the
        # sandbox:
        os.read(fd, 1)

        # After removing all privileges (principally, CAP_READ),
        # read() is no longer permitted in sandbox mode:
        cap.limit(fd, cap.right.NONE)
        with self.assertRaises(EnvironmentError) as cm:
            os.read(fd, 1)
        self.assertEqual(cm.exception.errno, cap.ENOTCAPABLE)

    # cap_fcntls_limit, etc.
    def test_fcntl_names(self):
        cap.fcntl.GETFL
        cap.fcntl.SETFL
        cap.fcntl.GETOWN
        cap.fcntl.SETOWN
        cap.fcntl.ALL

    def test_fcntls_obj(self):
        cap.Fcntls()
        cap.Fcntls({cap.fcntl.GETFL})
        cap.Fcntls([cap.fcntl.SETFL, cap.fcntl.SETOWN])

    def test_fcntls_negative(self):
        # By definition zero is not a valid flag bit.
        with self.assertRaises(ValueError):
            cap.Fcntls([0])
        with self.assertRaises(AttributeError):
            cap.fcntl.DoesNotExist

    @util._process_isolate
    def test_fcntls_limit_trivial(self):
        fd = os.open("/dev/null", os.O_RDONLY)
        cap.fcntls_limit(fd, cap.Fcntls([cap.fcntl.ALL]))

        cap.enter()
        self.assertTrue(cap.sandboxed())

        # No-op, just verify no exception is raised.
        flags = py_fcntl.fcntl(fd, py_fcntl.F_GETFL)
        py_fcntl.fcntl(fd, py_fcntl.F_SETFL, flags)

        # Restrict to no fcntl rights and except NOTCAPABLE.
        cap.fcntls_limit(fd, cap.Fcntls())
        with self.assertRaises(EnvironmentError) as cm:
            py_fcntl.fcntl(fd, py_fcntl.F_GETFL)
        self.assertEqual(cm.exception.errno, cap.ENOTCAPABLE)

    # cap_ioctls_limit, etc.
    def test_ioctls_obj(self):
        cap.Ioctls()
        cap.Ioctls({termios.TCION})

    @util._process_isolate
    def test_ioctls_limit_trivial(self):
        fd = os.open("/dev/null", os.O_RDONLY)

        cap.enter()
        self.assertTrue(cap.sandboxed())

        cap.ioctls_limit(fd, cap.Ioctls({termios.FIONREAD}))
        try:
            py_fcntl.ioctl(fd, termios.FIONREAD)
        except EnvironmentError as ee:
            # ENOTTY is fine, we're sending a stupid ioctl to a device
            # that doesn't know about it.  The point is that capsicum
            # permitted it.
            if ee.errno != errno.ENOTTY:
                raise

        # Capsicum rejects ioctls outside the set we've limited
        # ourselves to above.
        with self.assertRaises(EnvironmentError) as cm:
            py_fcntl.ioctl(fd, termios.TIOCGETD)
        self.assertEqual(cm.exception.errno, cap.ENOTCAPABLE)

        # Capsicum rejects requests to increase privileges:
        with self.assertRaises(EnvironmentError) as cm:
            cap.ioctls_limit(fd,
                cap.Ioctls({termios.FIONREAD, termios.TIOCGETD}))
        self.assertEqual(cm.exception.errno, cap.ENOTCAPABLE)

    @util._process_isolate
    def test_openat(self):
        fd = os.open("/dev", os.O_RDONLY)

        cap.enter()
        self.assertTrue(cap.sandboxed())

        rightset = {
            cap.READ,   # to allow the openat(O_RDONLY)
            cap.LOOKUP, # Also for openat()
            cap.FSTAT,  # Used by Python os.fdopen(), although non-fatal if
                        # denied.  Attempts the syscall twice if denied,
                        # though.
            cap.FCNTL,  # Used by Python os.fdopen() for F_GETFL.  Fatal if
                        # denied.
            }
        cap.limit(fd, cap.Rights(rightset))

        # Since we permit fcntl(), restrict the set of valid fcntls.
        cap.fcntls_limit(fd, cap.Fcntls({cap.fcntl.GETFL}))

        # Ordinary open is not permitted in sandbox mode:
        with self.assertRaises(EnvironmentError) as cm:
            open("/dev/null")
        self.assertEqual(cm.exception.errno, cap.ECAPMODE)

        # But with at least the privileges granted above, we can openat() and
        # read() from a file-like object:
        f = cap.openat(fd, "null", os.O_RDONLY)
        f.readlines()

    def test_fromfile(self):
        fd = os.open("/dev/null", os.O_RDONLY)
        fp = open("/dev/null")

        self.assertEqual(cap._cffi.buffer(cap.Rights(fd)._rights),
            cap._cffi.buffer(cap.right.ALL._rights))
        cap.Rights(fp)

        self.assertEqual(cap.Fcntls(fd)._flags, cap.fcntl.ALL)
        cap.Fcntls(fp)

        self.assertIs(cap.Ioctls(fd)._ioctls, None)
        cap.Ioctls(fp)

    def test_copy_ctors(self):
        cap.Rights(cap.Rights())
        cap.Fcntls(cap.Fcntls())
        cap.Ioctls(cap.Ioctls())


@unittest.skipIf(sys.version_info >= (3, 3), "irrelevant for newer Python")
class TestCompat33(unittest.TestCase):
    def test_compat33_open(self):
        dfd = os.open(my_dirname, os.O_RDONLY)
        fd = cap.compat33.open(my_filename, os.O_RDONLY, dir_fd=dfd)

    def test_compat33_open_enoent(self):
        dfd = os.open(my_dirname, os.O_RDONLY)
        with self.assertRaises(OSError) as cm:
            fd = cap.compat33.open("__does_not_exist__", os.O_RDONLY, dir_fd=dfd)
        exo = cm.exception
        self.assertEqual(exo.errno, errno.ENOENT)

    def test_compat33_listdir(self):
        expected = sorted(os.listdir(my_dirname))

        dfd = os.open(my_dirname, os.O_RDONLY)
        actual = sorted(cap.compat33.listdir(dfd))

        self.assertItemsEqual(actual, expected)
