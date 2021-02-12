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

"""
Class to provide t-like behavior.
"""

from __future__ import print_function

import sys

# Inspired by http://www.mail-archive.com/python-list@python.org/msg147679.html
class Tee(object):
    """
    Copies stdout and stderr into a new log file. Restores on close().
    NOTE: Due to references from sys.stdout and sys.stderr created on
    construction, close() MUST be called for a later deletion of this object to
    succeed.
    """
    def __init__(self, name, mode='w'):
        self.logfile = open(name, mode, buffering=1)  # Open line-buffered
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        sys.stdout = self
        sys.stderr = self
        self.stdout.write("Logging into: %s\n" % name)

    def __del__(self):
        # Usually only clled once object has already been closed
        self.close()

    def close(self):
        """
        Closes the log output file and restores the original sys.stdout/err
        objects.
        """
        if self.logfile is None:
            return
        self.flush()
        # Restore system outputs
        sys.stdout = self.stdout
        sys.stderr = self.stderr
        self.logfile.close()
        self.logfile = None
        self.stdout = None
        self.stderr = None

    def write(self, data):
        """
        Write data to the log file and stdout
        """
        if self.logfile is None:
            print("Tee.write() should not be called after close()!")
            return
        self.logfile.write(data)
        self.stdout.write(data)

    def flush(self):
        """
        Flush stdout.
        """
        if self.stdout is None:
            return
        # self.logfile is unbuffered; no flush
        self.stdout.flush()
