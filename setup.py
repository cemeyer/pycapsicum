from setuptools import setup, Extension

setup(name='py-capsicum-cffi',
    version='3',
    description="Python interface to Capsicum",
    long_description="""
PyCapsicumCFFI is a Python API wrapper for FreeBSD's Capsicum sandbox.
        """,

    author="Conrad Meyer",
    author_email="cem@FreeBSD.org",
    url="https://github.com/cemeyer/pycapsicumcffi",
    project_urls={
        "Source Code": "https://github.com/cemeyer/pycapsicumcffi",
        },
    keywords="capsicum FreeBSD pycapsicum capability sandbox pledge seccomp",
    license="DO WHAT THE FUCK YOU WANT TO BUT IT'S NOT MY FAULT PUBLIC LICENSE",
    data_files=[("", ["COPYING"])],

    setup_requires=["cffi>=1.14.0"],
    install_requires=["cffi>=1.14.0"],
    platforms=["FreeBSD"],
    python_requires='>=2.7',

    cffi_modules=["cap_build.py:ffibuilder"],
    packages=['cap'],
    package_data={"": ["../cap_build.py"]},
    test_suite="tests",

    classifiers=[
        "Intended Audience :: Developers",
        "Operating System :: POSIX :: BSD :: FreeBSD",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Topic :: Security",
        "Topic :: Software Development :: Libraries",
        "Topic :: System :: Operating System",
        ],
    )
