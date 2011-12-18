#!/usr/bin/env python

from distutils.core import setup

setup(name='gitorious-mrq-monitor',
    version='0.0.1',
    description='Monitor Gitorious merge requests over IRC',
    author='Jon Nordby',
    author_email='jononor@gmail.com',
    url='https://github.com/jonnor/gitorious-mrq-monitor',
    packages=['gitorious_mrq'],
    scripts=['bin/gitorious-mrq-monitor'],
)
