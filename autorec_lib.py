#!/usr/bin/env python

# MIT License
# 
# Copyright (c) 2017 Mayo Clinic
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import print_function

import glob
import os

from ar_lib.JobManager import JobManager, GetFilesCallback
# Import * as user-provided site-*.py functions / defs need to be included
from ar_lib.arsite import *

# Testing code
if __name__ == "__main__":
    # pylint: disable=C0103
    # Don't write world-writable files/dirs
    os.umask(0x2)
    mgr = JobManager()
    mgr.enter_dir(TEST_DIR)
    cback = \
        GetFilesCallback(lambda y: JobManager.push_files(GOOD_TEST, y),
                         desc='Push to {0}'.format(GOOD_TEST), limit=10)
    def echo_func(x):
        "An example of a function that can be wrapped by GetFilesCallback."
        print(x)
        # Callback functions need to return the number of files (elements of x)
        # successfully handled.
        return len(x)

    mgr.get_files(r'.*\.sdcopen', callback=cback)
    #echoback = GetFilesCallback(echo_func)
    #mgr.get_files(r'.*\.sdcopen', callback=echoback)
    mgr.get_files(r'.*\.sdcopen')
    print("Pushing to {0}".format(GOOD_TEST))
    mgr.push_files(GOOD_TEST, glob.glob('*.sdcopen'))

# vim: et:ts=4:sw=4:si:ai
