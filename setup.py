#!/usr/bin/env python

from distutils.core import setup

classifiers = """\
Development Status :: 4 - Beta
Intended Audience :: Developers
Programming Language :: Python
Programming Language :: Python :: 2
License :: OSI Approved :: GNU General Public License (GPL)
Operating System :: OS Independent
Topic :: Software Development :: Libraries :: Python Modules
Topic :: Communications :: Chat
Topic :: Internet :: WWW/HTTP :: Indexing/Search
Topic :: Software Development :: Quality Assurance
Topic :: System :: Monitorings
"""

setup(name='gitorious-mrq-monitor',
    version='0.0.1',
    description='Monitor Gitorious merge requests over IRC',
    author='Jon Nordby',
    author_email='jononor@gmail.com',
    url='https://github.com/jonnor/gitorious-mrq-monitor',
    packages=['gitorious_mrq'],
    scripts=['bin/gitorious-mrq-monitor'],
    classifiers=classifiers,
)
