# Copyright 2020 Conrad Meyer <cem@FreeBSD.org>
#
# SPDX-License-Identifier: WTFNMFPL-1.0

import re
import subprocess
import sys

import cffi
import pycparser

# XXX CFFI cdef() does not allow inline functions, which is more or less all of
# capsicum_helpers.h.
# TODO: Casper.

cappp = pycparser.preprocess_file("/usr/include/sys/capsicum.h",
    cpp_args=[
        '-P',     # Don't generate line markers
        '-undef', # Don't include predefined macros (most of them, anyway)
        '-dD',    # Keep '#define' directives
        '-D_SYS_CDEFS_H_',
        '-D_SYS_TYPES_H_',
        '-D_SYS__TYPES_H_',
        '-D_SYS_PARAM_H_',
        '-D_SYS_FILE_H_',
        '-D_SYS_FCNTL_H_',
        '-D__BEGIN_DECLS=',
        '-D__END_DECLS=',
        '-Du_int=unsigned',
        '-Dcap_ioctl_t=unsigned long',
    ])

cdefs = []
trailing_trash = False
for line in cappp.splitlines():
    # Remove remnents of deleted multi-line macros.
    if trailing_trash:
        if not line.endswith('\\'):
            trailing_trash = False
        continue

    # Remove leftover function-like macros.  We don't need any of 'em.
    if re.match(r'^#define\s+(CAP|cap)[^( \t]+\([^)]+\)', line):
        if line.endswith('\\'):
            trailing_trash = True
    # Use dot-dot-dot mechanism to have the C compiler fill in numeric constant
    # macros[1].
    # [1]: https://cffi.readthedocs.io/en/latest/cdef.html#letting-the-c-compiler-fill-the-gaps
    elif re.match(r"^#define\s+CAP\S+\s+\S", line):
        cdefs.append(re.sub(r'^(#define\s+CAP\S+\s).*', r'\1...', line))
        if line.endswith('\\'):
            trailing_trash = True
    # Don't export non CAP_ macro values:
    elif re.match(r"^#define\s+\S+", line):
        pass
    # Delete blank lines (ease of debugging)
    elif re.match(r'^\s*$', line):
        pass
    # Remove bogus userspace definition of kernel symbol (fails dynamic link):
    elif re.match(r'.*__cap_rights_sysinit.*', line):
        pass
    else:
        cdefs.append(line)

# Constants we use in high-level cap module missing from os in older
# Python.  (Python.org has no excuses here -- these constants long predate
# Python 3.0 and their inability to give a fuck about Python 2.)
cdefs.append("#define AT_FDCWD ...")
cdefs.append("#define ECAPMODE ...")
cdefs.append("#define ENOTCAPABLE ...")
cdefs.append("#define O_ACCMODE ...")

# Expose so we can create an "ALL" object.
cdefs.append("static void CAP_ALL(cap_rights_t *);")

# Compat code helpers.
if sys.version_info < (3, 3):
    cdefs += [
        "#define O_CLOEXEC ...",
        "int openat(int, const char *, int, ...);",
        "typedef struct _dirdesc DIR;",
        "struct dirent {",
        "    char d_name[];",
        "    ...;",
        "};",
        "DIR *fdopendir(int);",
        "struct dirent *readdir(DIR *);",
        "int closedir(DIR *);",
        ]

cappp = "\n".join(cdefs)

ffibuilder = cffi.FFI()
ffibuilder.set_source("_cap_cffi", """
        #include <sys/capsicum.h>
        #include <errno.h>
        #include <dirent.h>
        #include <fcntl.h>
    """, libraries=['c'])
ffibuilder.cdef(cappp)

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
