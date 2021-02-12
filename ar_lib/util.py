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
Collection of generic support functions
"""

from __future__ import print_function

import fcntl
import hashlib
import subprocess
import re
import sys

from io import StringIO
from os import stat
from re import search
from time import time, sleep

## Functions

def flatten(orig, flat):
    """
    Flattens nested iterables in orig to single depth list appended to flat.
    """
    if '__iter__' not in dir(orig):
        flat += [orig]
    else:
        for memb in orig:
            flatten(memb, flat)


def get_ge_ver():
    """
    Runs GE's whatRev and returns the major and minor version numbers as a
    tuple of ints: (major, minor).
    """
    rev = subprocess.Popen(["/usr/g/bin/whatRev", "-format_small"],
                           stdout=subprocess.PIPE)
    rev.wait()
    rev = rev.stdout.readline()
    rev = [int(z) for z in search(r'([0-9]+)\.([0-9]*)', rev).group(1, 2)]
    return rev


def pretty_bytes(num):
    """
    Pretty string of bytes size
    """
    ext = {0: '', 10: 'K', 20: 'M', 30: 'G', 40: 'T', 50: 'E'}
    for pwr in sorted(ext.keys()):
        if num / 2.0**pwr < 512:
            return "{0:.3g} {1}B".format(num / 2.0**pwr, ext[pwr])
    return "{0:g} B".format(num)


def print_out(output, label=('Output', 'Error messages')):
    """
    Prints output[:], described by label[:], sequentially to stdout.
    """
    printed = False
    for (buf, lbl) in zip(output, label):
        if buf is None or buf.find('\n') == -1:
            continue
        printed = True
        print(" +--- %s:" % lbl)
        if sys.version_info[0] >= 3:
            buf = StringIO(buf)
        else:
            buf = StringIO(unicode(buf))
        for line in buf:
            print(" | " + line.rstrip())
        print(" +--- End of %s." % lbl)
    if not printed:
        print(" -- No output --")


def run_cmd(cmd):
    """
    Runs the external command cmd in a shell and prints the result.
    Raises an IOError exception if a non-zero exit code is detected.
    """
    print("Exectuting command [{0}]".format(cmd))
    sub_cmd = subprocess.Popen(cmd,
                               bufsize=4096,
                               close_fds=True,
                               shell=True,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               universal_newlines=True)
    output = sub_cmd.communicate()
    print_out(output)
    if sub_cmd.returncode:  # Had a non-zero return code
        raise IOError("Subprocess returned non-zero exit code (%d)" %
                      sub_cmd.returncode)


def settle_file(file_path, age=5.0):
    """Wait until file at file_path is at least age seconds old."""
    def wait_time():
        "How much longer to wait for file_path to be age seconds old."
        return max(0.0, stat(file_path).st_mtime + age - time())
    start_time = time()
    slept = False
    while wait_time() > 0.0:
        if not slept:
            print("Waiting for file [{0}] to stop changing.".format(file_path))
            print(" ^-", end="")
            sys.stdout.flush()
        sleep(min(1, wait_time()))
        print("-", end="")
        sys.stdout.flush()
        slept = True
    if slept:
        print(" waited {0:.2g}s total.".format(time() - start_time))


def get_fid(pathname):
    if not re.match('^\d+$', pathname):
        return None
    fd = int(pathname)
    try:
        fcntl.fcntl(fd, fcntl.F_GETFL)
        return fd
    except OSError as err:
        return None
## Classes

class MD5Wrapper(object):
    """"
    Used to wrap a file object which will be checksummed while read().
    """
    def __init__(self, fileObject):
        """
        Creates a new MD5Wrapper object; initialized checksum.

        fileObject: Opened object supporting read([size]) method.
        """
        self.handle = fileObject
        # Create checksum object
        try:
            self.md5 = hashlib.md5()
        except ValueError:
            # pylint: disable=E1123
            # RHEL FIPS mode support
            self.md5 = hashlib.md5(usedforsecurity=False)

    def read(self, *args):
        """
        Read from wrapped file and update checksum.
        """
        buf = self.handle.read(*args)
        self.md5.update(buf)
        return buf

    def hexdigest(self):
        """
        Return hexdigest (string) of read bytes.
        """
        return self.md5.hexdigest()
