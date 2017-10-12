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

"""
Module to handle SSH connections. Uses ssh executable and master connections
to enable rapid execution of each new task.
"""
from __future__ import print_function

import os
import subprocess
import time

from signal import SIGINT, SIGQUIT, SIGKILL

DEBUG = os.environ.get('SSH_DEBUG', '0') != '0'


class ConnectionError(Exception):
    "Errors occuring during SSH session."
    def __str__(self):
        return "Error from SSH session: [{0}]".format(self.message)


class SSH(object):
    """
    Object to handle an active (kept open with a control master connection) SSH
    session providing rapid (~ 30/s) execution of remote tasks.
    """
    def __init__(self, hostname, username, key, executable='ssh'):
        """
        Initialize session. Raises IOError if unable to connect.

        arguments:
         hostname: Remote host
         username: Remote user
         key: path to SSH key file
         executable: SSH executable to call
        """
        self._hostname = hostname
        self._username = username
        self._key = key
        self._exe = executable
        self._init = True

        if DEBUG:
            print("Launching master session. "
                  "pid: {0}, id: {1}".format(os.getpid(), id(self)))

        # We start this with pipe input such that the remote cat doesn't exit
        self._master = self.run("echo Y; cat > /dev/null",
                                stdin=subprocess.PIPE)
        self._init = False  # We have launched our control master session

        res = self._master.stdout.read(1)

        if res != "Y":
            print('Error during master setup:\n' + res, end='')
            for line in self._master.stdout:
                print(line.rstrip())
            self._master.stderr.seek(0)
            for line in self._master.stderr.readlines():
                print(">> " + line.rstrip())
            self._master = None
            raise IOError("Unexpected return from SSH master.")
        if DEBUG:
            print("Master connection initiated!")
        print("Connected to {0}".format(self._hostname))

    def __del__(self):
        """
        Closes down SSH connection gracefully.
        """
        self.close()

    def check_call(self,
                   command,
                   **kwargs):
        """
        Launch an remote command via ssh and raise on non-zero return value.

        command : Remote command to run
        kwargs : Arguments to subprocess.Popen()
         - Defaults if not provided:
           - bufsize: 4096 *
           - close_fds: True *
           - stdin: /dev/null *
           - stdout: /dev/null
           - stderr: /dev/null
           - universal_newlines: True *
           *: Defaults from run()
        """
        self.check_connected()

        # Defaults: (None here currently; kept here for consistency)
        defaults = {}

        for item in defaults.iteritems():
            kwargs.setdefault(*item)

        # Avoid opening these fds if we don't need to
        if 'stdout' not in kwargs:
            kwargs['stdout'] = file('/dev/null', 'w')
        if 'stderr' not in kwargs:
            kwargs['stderr'] = file('/dev/null', 'w')

        j = self.run(command,
                     **kwargs)
        j.wait()
        if j.returncode:
            raise subprocess.CalledProcessError(j.returncode, command)

    def check_connected(self):
        "Raise ConnectionError if not currently connected."
        if not self.is_connected():
            raise ConnectionError("Attempted while not connected!")

    def check_output(self,
                     command,
                     **kwargs):
        """
        Launch a remote command via ssh and return (stdout, stderr). Rasies
        subprocess.CalledProcessError on non-zero return value.

        command : Remote command to run
        kwargs : Arguments to subprocess.Popen()
         - Defaults if not provided:
           - bufsize: 32768
           - close_fds: True *
           - stdin: /dev/null
           - stdout: subprocess.PIPE *
           - stderr: subprocess.PIPE
           - universal_newlines: True *
           *: Defaults from run()
        """
        self.check_connected()

        # Defaults:
        defaults = {'bufsize':  32768,
                    'stderr':   subprocess.PIPE}

        for item in defaults.iteritems():
            kwargs.setdefault(*item)

        # Avoid opening these fds if we don't need to
        if 'stdin' not in kwargs:
            kwargs['stdin'] = file('/dev/null', 'r')

        j = self.run(command,
                     **kwargs)
        res = j.communicate()
        if j.returncode:
            raise OSError("Error in check_output: [{0}]".format(j.returncode))
        return res

    def close(self):
        "Close (if connected) currently active session."
        if DEBUG:
            print("Closing master session. "
                  "pid: {0}, id: {1}".format(os.getpid(), id(self)))
        if not self.is_connected():
            self._master = None
            return
        try:
            self._master.stdin.close()
            # Try to close out gracefully. Should finish by itself on
            # stdin.close, but just in case...
            for sig in (SIGINT, SIGQUIT, SIGKILL):
                time.sleep(0.5)
                if self._master.poll() is not None:
                    break
                self._master.send_signal(sig)
            self._master.wait()
        except Exception as err:                        #pylint: disable=W0703
            print("Error while closing master connection: [{0}]".format(err))
        finally:
            self._master = None

    def is_connected(self):
        "Quick check if currently connected. Returns True if connected."
        return isinstance(self._master, subprocess.Popen) and \
               self._master.returncode is None

    def run(self, command, **kwargs):
        """
        Launch an remote command via ssh.

        command : Remote command to run
        kwargs : Arguments to subprocess.Popen()
         - Defaults if not provided:
           - bufsize: 4096
           - close_fds: True
           - stdin: /dev/null
           - stdout: subprocess.PIPE
           - stderr: temporary file (NOT PIPE; available as <returned>.stderr)
           - universal_newlines: True
        """
        if self._init is False:
            self.check_connected()

        # Defaults:
        defaults = {'stdout':               subprocess.PIPE,
                    'universal_newlines':   True,
                    'bufsize':              4096,
                    'close_fds':            True}

        for var in defaults.iteritems():
            kwargs.setdefault(*var)

        # Avoid opening these fds if we don't need to
        if 'stdin' not in kwargs:
            kwargs['stdin'] = file('/dev/null', 'r')

        if 'stderr' not in kwargs:
            efile = os.tmpfile()
            kwargs['stderr'] = efile
        else:
            efile = None

        master = 'yes' if self._init is True else 'no'

        # our ssh_wrapper script discards "FIPS mode initialized" messages on
        # stderr.
        cmd = (self._exe,
               "-F", "/dev/null",
               "-o", "IdentityFile={0}".format(self._key),
               "-o", "BatchMode=yes",
               "-o", "ConnectTimeout=5",
               "-o", "ControlMaster={0}".format(master),
               "-o", "ControlPath=/tmp/ssh.%h.{0}.{1}".format(os.getpid(),
                                                              id(self)),
               "-o", "ServerAliveInterval=20",
               "-o", "StrictHostKeyChecking=no",
               "{0}@{1}".format(self._username, self._hostname),
               command)
        if DEBUG:
            print("Executing SSH command:\n  [{0}]".format(cmd))

        sub_cmd = subprocess.Popen(cmd, **kwargs)
        if efile:
            sub_cmd.stderr = efile

        return sub_cmd


##Future work...
#class SFTP(SSH):
#    """
#    Provides sftp-like functionality.
#    """
#
#    def __init__(self,
#                 hostname,
#                 username,
#                 key,
#                 executable='ssh',
#                 chroot=True):
#        """
#        Starts an SSH ("SFTP") session.
#        """
#        SSH.__init__(self, hostname, username, key, executable)
#        if chroot == True:
#            self._cwd = '/'
#            self._root = self.check_output('pwd')[0].strip()
#        else:
#            self._cwd = self.check_output('pwd')[0].strip()
#            self._root = '/'
#
#    def cd(self, pth):
#        pth = os.path.normpath(os.path.join(self._cwd, pth))
#        while len(pth) and pth[0] == '/':
#            pth = pth[1:]
#
#        if len(pth) == 0:
#            self._cwd = '/'
#            return
#
#        dest = os.path.join(self._root, pth)
#
#        try:
#            SSH.check_call(self, "test -e {0} && test -x {0}".format(dest))
#            self._cwd = '/' + pth
#        except:
#            raise ConnectionError("Path [{0}] not available!".format(pth))


if __name__ == '__main__':
    # pylint: disable=C0103
    dirname = os.path.dirname
    ssh_dir = dirname(os.path.abspath(__file__))

    # A bit of a hack to get these imports to work as we're not part of a 
    # loaded module here.
    import sys
    sys.path.insert(0, dirname(ssh_dir))
    from ar_lib.site import USERNAME, DEFAULT_RECON_MACHINES
    from ar_lib.JobManager import KEYFILE

    def _pstree():
        if not DEBUG:
            return 0
        print("\nCurrent process tree:\n")
        try:
            subprocess.call(("pstree", "{0}".format(os.getpid())))
        except OSError:
            print("Install pstree for process trees...")
        print("\n")

    import timeit

    if len(sys.argv) >= 2:
        host = sys.argv[1]
    else:
        host = DEFAULT_RECON_MACHINES[0]

    sess = SSH(host, USERNAME, KEYFILE)
    sess = SSH(host, USERNAME, KEYFILE)

    test = sess.run('sleep 1', stdout=None)
    _pstree()
    test.wait()

    print("Testing remote 'true': ", end='')
    sess.check_call('true')
    print('PASS')
    print("Testing remote 'exit 42': ", end='')
    try:
        sess.check_call('exit 42')
    except subprocess.CalledProcessError as err:
        if err.returncode == 42:
            print("PASS (failed as expected):\n  [{0}]".format(err))
        else:
            print("FAIL (failed WITH WRONG CODE)):\n  [{0}]".format(err))

    print("Testing check_output: ", end='')
    test = sess.check_output('echo PASS')
    if test[0].strip() == 'PASS':
        print('PASS')
    else:
        print('FAIL')

    print("\n---- Timing tests ----")

    reps = 10
    run_time = timeit.timeit("sess.check_call('true')",
                             "from __main__ import sess",
                             number=reps)
    print("Latency per call: {0:0.3f}s".format(run_time/reps))
    print("Calls per second: {0:0.1f}".format(reps/run_time))

    sess = None

    _pstree()
    print('Timings with ./ssh_wrapper:')
    sess = SSH(host, USERNAME, KEYFILE,
               executable=os.path.join(ssh_dir, 'ssh_wrapper'))
    _pstree()

    reps = 10
    run_time = timeit.timeit("sess.check_call('true')",
                             "from __main__ import sess",
                             number=reps)
    print("Latency per call (with wrapper): {0:0.3f}s".format(run_time/reps))
    print("Calls per second (with wrapper): {0:0.1f}".format(reps/run_time))
    sess.close()
    sess = None

    _pstree()

    #sf = SFTP(host, USERNAME, KEYFILE)
