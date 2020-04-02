PyCapsicumCFFI
==============

PyCapsicumCFFI is a Python API wrapper for FreeBSD's Capsicum sandbox.

[![Build Status (cirrus-ci.com)](https://api.cirrus-ci.com/github/cemeyer/pycapsicumcffi.svg)](https://cirrus-ci.com/github/cemeyer/pycapsicumcffi)
[![Code Coverage (codecov.io)](https://codecov.io/gh/cemeyer/pycapsicumcffi/branch/master/graph/badge.svg)](https://codecov.io/gh/cemeyer/pycapsicumcffi)

The C documentation is a good reference point for understanding how to use Capsicum.

Demo
----

Quick Demo:

```python
    import cap
    import os
        
    # Python 3.3 adds dir_fd= kwarg to os.open(), but earlier versions do not expose openat.
    # So this module provides a backwards-compatible version on those platforms.  Similarly,
    # 3.3 accepts a directory fd for os.listdir(), but earlier versions do not.  Operating on
    # directory fds and directory-relative fds is essential to sandboxed applications.
    try:
        os.open = cap.compat33.open
        os.listdir = cap.compat33.listdir
    except AttributeError:
        pass

    # get an fd for /tmp
    t = os.open('/tmp', os.O_RDWR)

    # enter capability mode
    cap.enter()

    # create a new cap_rights object
    a = cap.Rights()
    
    # use os.open dir_fd (openat syscall) to open an fd in tmp
    x = os.open('foo', os.O_RDWR, dir_fd=t)
    # and os.fdopen() to convert it to Python file
    y = os.fdopen(x, 'r+')
    
    # Or save a little typing with the cap.openat() wrapper:
    z = cap.openat(t, 'bar', os.O_RDWR)

    # y and z are python file objects
    y.readlines()
    z.readlines()

    # get the capabilities of x (fd)
    a = cap.Rights(x)
    # or of y (a file object)
    b = cap.Rights(y)

    # construct a new cap.Rights with just the READ capability:
    c = cap.Rights({cap.READ})

    # or reference one of the many predefined commonly used single-capability Rights:
    d = cap.right.READ

    # restrict fd x to rights in c
    cap.limit(x, c)
    
    # One may use cap.Ioctls(), cap.ioctls_limit(), cap.Fcntls(), and cap.fcntls_limit()
    # analogously to cap.Rights() and cap.limit().
```

API Summary
-----------

### Basics
* `cap.enter()`: Enter sandboxed mode.
* `cap.sandboxed()`: Returns `True` if in sandboxed mode.
* `cap.openat(fd, path, flags [, mode])`: Convenience wrapper around `os.open(dir_fd=)` and `os.fdopen()`.

### Compatibility (Python 2.x)
* `cap.compat33.open(path, flags [, mode [, dir_fd=None]])`: Backport API for fd-relative `os.open`.
* `cap.compat33.listdir(path='.')`: Backport API for fd-relative `os.listdir`.  Path may be a path or a file descriptor.

### fcntl(2) related
* `cap.fcntl.GETFL`, `SETFL`, `GETOWN`, `SETOWN`: some of the valid flags for a `cap.Fcntl()`.
* `cap.Fcntls(fd)`: Fetch fcntl rights of `fd`.
* `cap.Fcntls({GETFL, ...})`: Construct an fcntl set.
* `cap.fcntls_limit(fd, cap.Fcntls())`: Limits `fd` to fcntls of provided fcntl set.

### ioctl(2) related
* `cap.Ioctls(fd)`: Fetch ioctl rights of `fd`.
* `cap.Ioctls({foo, bar, ...})`: Construct an ioctl set.
* `cap.ioctls_limit(fd, cap.Ioctls())`: Limits `fd` to ioctls of provided ioctl set.  `fd` may be a file descriptor, or any object supporting `::fileno()`.

### rights(4)
* `cap.READ`, `WRITE`, ...: some of the valid flags for a `cap.Rights()`.
* `cap.Rights(fd)`: Fetch rights of `fd`.
* `cap.Rights({READ, ...})`: Construct a rights set.
* `cap.limit(fd, cap.Rights())`: Limit `fd` to provided set of rights.

After (and only after) entering the capsicum sandbox, global filesystem namespace operations are disallowed, and rights associated with existing file descriptors may only be reduced; no additional rights may be granted.  Some kinds of file descriptor can be used to create more descriptors (e.g., a directory fd with `cap.LOOKUP | cap.READ` or a listening socket with `cap.ACCEPT`), but the new descriptors inherit the restrictions of the parent fd.

For more information, see the capsicum manual pages.
