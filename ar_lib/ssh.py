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
import re
import shlex
import subprocess
import sys
import tempfile
import time

if __name__ == "__main__":
    # Hack around relative imports with a module file executable as script
    updir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    sys.path.append(updir)
    from ar_lib.arsite import COMPRESS, DECOMPRESS
else:
    from .arsite import COMPRESS, DECOMPRESS

from signal import SIGINT, SIGQUIT, SIGKILL

DEBUG = os.environ.get('SSH_DEBUG', '0') != '0'

def pretty_bytes(num):
    "Nice power-of-two dislpay"
    suffix = {0:'', 10:'K', 20:'M', 30:'G', 40:'T', 50:'E'}
    for power in sorted(suffix.keys()):
        if num / 2.0**power < 768:
            return "{0:.3f} {1}B".format(num / 2.0**power, suffix[power])
    return "{0:g} B".format(num)



class SSH(object):
    """
    Object to handle an active (kept open with a control master connection) SSH
    session providing rapid (~ 30/s) execution of remote tasks.
    """
    class ConnectionError(Exception):
        "All errors during SSH session."
        def __init__(self, message):
            Exception.__init__(self)
            self.message = message

        def __str__(self):
            return "Error from SSH session: [{0}]".format(self.message)

    def __init__(self,
                 hostname,
                 username=None,
                 key=None,
                 executable='ssh',
                 standalone=False):
        """
        Initialize session. Raises IOError if unable to connect.

        arguments:
         hostname: Remote host (or user@host, overriding username)
         username: Remote user
         key: path to SSH key file
         executable: SSH executable to call
         standalone: True:       use /dev/null
                     String:     use as config file
                     Otherwise:  use normal ~/.ssh/config
        """
        if '@' in hostname:
            [self._username, self._hostname] = hostname.split('@')
        else:
            self._hostname = hostname
            self._username = username
        self._key = key
        self._exe = executable
        self._init = True
        self._standalone = standalone

        if DEBUG:
            print("Launching master session. "
                  "pid: {0}, id: {1}".format(os.getpid(), id(self)))

        # We start this with pipe input such that the remote cat doesn't exit
        self._master = self.run("echo Y; cat > /dev/null",
                                stdin=subprocess.PIPE,
                                universal_newlines=True)
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

        for item in defaults.items():
            kwargs.setdefault(*item)

        # Avoid opening these fds if we don't need to
        if 'stdout' not in kwargs:
            kwargs['stdout'] = open('/dev/null', 'w')
        if 'stderr' not in kwargs:
            kwargs['stderr'] = open('/dev/null', 'w')

        j = self.run(command,
                     **kwargs)
        j.wait()
        if j.returncode:
            raise subprocess.CalledProcessError(j.returncode, command)

    def check_connected(self):
        "Raise ConnectionError if not currently connected."
        if not self.is_connected():
            raise SSH.ConnectionError("Attempted while not connected!")

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

        for item in defaults.items():
            kwargs.setdefault(*item)

        # Avoid opening these fds if we don't need to
        if 'stdin' not in kwargs:
            kwargs['stdin'] = open('/dev/null', 'r')

        j = self.run(command,
                     **kwargs)
        res = j.communicate()
        if j.returncode:
            raise OSError("Error in check_output: [{0}]".format(j.returncode))
        return res

    def close(self):
        "Close (if connected) currently active session."
        if not self.is_connected():
            if DEBUG:
                print("Skipping close({0}); not connected".format(id(self)))
            self._master = None
            return

        if DEBUG:
            print("Closing master session. "
                  "pid: {0}, id: {1}".format(os.getpid(), id(self)))
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

    def get_hostname(self):
        "Accessor."
        return self._hostname

    def is_connected(self):
        "Quick check if currently connected. Returns True if connected."
        return isinstance(self._master, subprocess.Popen) and \
               self._master.returncode is None

    def run(self, command, **kwargs):
        """
        Launch an remote command via ssh.

        Returns the running subprocess.Popen object.

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

        for var in defaults.items():
            kwargs.setdefault(*var)

        # Avoid opening these fds if we don't need to
        if 'stdin' not in kwargs:
            kwargs['stdin'] = open('/dev/null', 'r')

        if 'stderr' not in kwargs:
            efile = tempfile.TemporaryFile('w+')
            kwargs['stderr'] = efile
        else:
            efile = None

        master = 'yes' if self._init is True else 'no'

        # our ssh_wrapper script discards "FIPS mode initialized" messages on
        # stderr.
        cmd = [self._exe]
        if self._standalone is True:
            cmd += ["-F", "/dev/null"]
        elif isinstance(self._standalone, str):
            cmd += ["-F", self._standalone]
        if self._key:
            cmd += ["-o", "IdentityFile={0}".format(self._key)]
        if self._username:
            cmd += ["-l", self._username]
        cmd += ["-o", "BatchMode=yes",
                "-o", "ConnectTimeout=5",
                "-o", "ControlMaster={0}".format(master),
                "-o", "ControlPath=/tmp/ssh.%h.{0}.{1}".format(os.getpid(),
                                                               id(self)),
                "-o", "ServerAliveInterval=20",
                "-o", "StrictHostKeyChecking=no",
                self._hostname,
                command]
        if DEBUG:
            print("Executing SSH command:\n  [{0}]".format(cmd))

        sub_cmd = subprocess.Popen(cmd, **kwargs)
        if efile:
            sub_cmd.stderr = efile

        return sub_cmd


class SFTP():
    """
    Provides sftp-like functionality. (Only uses bin/ssh, however.)
    """

    class SFTPErrors(Exception):
        "Parent class for all SFTP errors."
        pass


    class FileError(SFTPErrors):
        "Errors with local files."
        def __init__(self, fileNameIn=""):
            super(self.__class__, self).__init__()
            self.file_name = fileNameIn

        def __repr__(self):
            return "Unable to access file [%s]" % self.file_name

        def __str__(self):
            return repr(self)

    class RemoteFileError(SFTPErrors):
        "Errors with remote files."
        def __init__(self, session, fileName):
            super(self.__class__, self).__init__()
            self.file_name = fileName
            self.machine_name = session.get_hostname()

        def __repr__(self):
            return ("Tried to access %s on %s; does not exist!" %
                    (self.file_name, self.machine_name))

        def __str__(self):
            return repr(self)

    class SessionError(SFTPErrors):
        "Errors during remote operations."
        def __init__(self, errorString="undefined"):
            super(self.__class__, self).__init__()
            self.error_string = errorString

        def __repr__(self):
            return "Error during session [%s]" % self.error_string

        def __str__(self):
            return repr(self)

    def __init__(self, session, chroot=True):
        """
        Creates an 'sftp' session. Wraps an existing ssh session.
        """
        self._ssh = session
        if chroot:
            self._cwd = '/'
            self._root = self._ssh.check_output('pwd')[0].strip()
        else:
            self._cwd = self._ssh.check_output('pwd')[0].strip()
            self._root = '/'

    def cd(self, pth):
        """
        'Changes' into the relative or absoulte (but always relative to _root)
        path pth. (We don't really change into it, just keep track of where we
        are operating.
        """
        pth = self.clean_path(pth)

        if not pth:
            self._cwd = '/'
            return

        dest = self._root + pth

        try:
            self._ssh.check_call("test -e '{0}' && test -x '{0}'".format(dest))
            self._cwd = pth
        except:
            raise SSH.ConnectionError("Path [{0}] not available!".format(pth))

    def clean_path(self, pth):
        """
        Returns the normalized path formed by appending pth to _cwd.
        """
        pth = os.path.normpath(os.path.join(self._cwd, pth))
        return pth

    def dir_names(self, pattern='[^.].*'):
        """
        Returns the directories in the current directory matching RE pattern.

        Only items that don't start with '.' are included by default; Set
        pattern to None to return all directories.
        """
        self._ssh.check_connected()
        return self.listing(dir_mode=True, pattern=pattern)

    def file_names(self, pattern='[^.].*'):
        """
        Returns the files in the current directory matching RE pattern.

        Only items that don't start with '.' are included by default; Set
        pattern to None to return all files.
        """
        self._ssh.check_connected()
        return self.listing(dir_mode=False, pattern=pattern)

    def get_cwd(self):
        "Accessor"
        return self._cwd

    def _get_abs_cwd(self):
        "Internal accessor"
        return os.path.normpath(self._root + self._cwd)

    def listing(self, dir_mode=False, pattern=None):
        """
        Returns an array file names unless dir_mode is true (then dir names)
        in the current directory
        """
        self._ssh.check_connected()
        mode = 'd' if dir_mode else 'f'

        listcommand = "cd '{0}' && ".format(self._get_abs_cwd()) + \
                      "find -L . -maxdepth 1 -type {0} ".format(mode) + \
                      "-print0"
        output = \
            self._ssh.check_output(listcommand,
                                   universal_newlines=False)[0].split(b'\0')
        lst = sorted((x[2:]).decode('utf-8') for x in output if len(x) > 2)

        if pattern:
            rexp = re.compile(pattern)
            lst = list(filter(rexp.match, lst))

        if DEBUG:
            print(lst)
        return lst

    def mkdir(self, pth):
        """
        Creates a directory at the relative (to _cwd) or absolute path pth
        (always relative to _root)
        """
        pth = self.clean_path(pth)

        if not pth:
            return

        dest = os.path.join(self._root, pth)

        try:
            self._ssh.check_call("mkdir -p '{0}'".format(dest))
        except:
            raise SSH.ConnectionError("Errored while creating "
                                      "[{0}]!".format(dest))


    def get_file(self, remote_name, local_path, quiet=False, check_exist=True):
        """
        Retrieves one file from the remote server at remote_name and
        stores it at local_path. Returns received file size in bytes.
        """
        self._ssh.check_connected()

        if check_exist:  # Don't get listings again if we know it exists
            if remote_name not in self.file_names():
                raise self.RemoteFileError(self._ssh,
                                           os.path.join(self.get_cwd(),
                                                        remote_name))

        # Open local file for writing
        try:
            fid = open(local_path, 'wb')
        except:
            raise self.FileError(local_path)

        start_time = time.time()
        rpath = os.path.join(self._get_abs_cwd(), remote_name)

        # Open remote file for reading
        with fid:
            try:
                rcat = self._ssh.run("cat '{0}'".format(rpath),
                                     stdout=fid,
                                     stderr=subprocess.PIPE,
                                     universal_newlines=False)
                rcat.wait()
                size = fid.tell()
                os.fsync(fid.fileno())
                if rcat.returncode:
                    raise subprocess.CalledProcessError(rcat.returncode,
                                                        "Error during send.")
            except Exception as err:
                for lout in rcat.stderr:
                    print(lout.rstrip())
                raise self.SessionError("Unable to retrieve file: %s [%s]" %
                                        (remote_name, repr(err)))

        retrieve_time = time.time() - start_time

        if not quiet:
            if remote_name != local_path:
                print ("Retrieved %s as %s: %s in %fs [%s/s]" %
                       (remote_name,
                        local_path,
                        pretty_bytes(size),
                        retrieve_time,
                        pretty_bytes(size / retrieve_time)))
            else:
                print ("Retrieved %s: %s in %fs [%s/s]" %
                       (remote_name,
                        pretty_bytes(size),
                        retrieve_time,
                        pretty_bytes(size / retrieve_time)))
        return size

    def _get_files(self, file_list):
        """
        Used internally by get_files to perform a tar-based transfer of
        multiple files. Skips many checks as it is called from get_files()
        directly.

        Returns total bytes transferred (slightly larger that file bytes.)
        """
        total_sz = 0
        chunk = 256
        if len(file_list) > chunk:
            # make sure we don't create obscenely long command lines
            fin = 0
            while fin < len(file_list):
                total_sz += self._get_files(file_list[fin:fin+chunk])
                fin += chunk
            return total_sz

        dir_xfer = len(file_list) == 1 and file_list[0] in self.dir_names()

        rem_tar = "tar -C '{0}' -vcf- '{1}' | {2}" \
                    .format(self._get_abs_cwd(),
                            "' '".join(file_list),
                            COMPRESS)
        count_cmd = shlex.split('sh -c "{0} | dd bs=32k"'.format(DECOMPRESS))
        lcl_tar = ('tar', '-vxf-')

        files = [tempfile.TemporaryFile() for n in range(3)]

        if DEBUG:
            print("Remote command: " + rem_tar)
            print("local decompress and count: " + ' '.join(count_cmd))
            print("Untar command: " + ' '.join(lcl_tar))

        cmds = [None] * 3
        cmds[0] = self._ssh.run(rem_tar,
                                stderr=files[0],
                                universal_newlines=False,  # Otherwise corrupts
                                bufsize=0)
        cmds[1] = subprocess.Popen(count_cmd,
                                   stdin=cmds[0].stdout,
                                   stdout=subprocess.PIPE,
                                   stderr=files[1],
                                   bufsize=0)
        cmds[2] = subprocess.Popen(lcl_tar,
                                   stdin=cmds[1].stdout,
                                   stdout=files[2],
                                   stderr=subprocess.STDOUT,
                                   bufsize=0)

        # Polling loop
        while None in [x.returncode for x in cmds]:
            time.sleep(0.01)
            for (n, c) in enumerate(cmds):
                if c.returncode is None:
                    c.poll()
                if c.returncode:
                    # Print process log on error
                    files[n].seek(0)
                    for line in files[n]:
                        print(line)
                    raise subprocess.CalledProcessError(
                        c.returncode,
                        "Error during _get_files() cmds[{0}].".format(n))

        if DEBUG:
            for f in files:
                f.seek(0)
                print("---")
                print(f.read())

        # Get bytecount from dd
        files[1].seek(0)
        for lout in files[1]:
            byte_count = re.search(r'(\d+) bytes', lout.decode('utf-8'))
            if byte_count:
                total_sz += int(byte_count.group(1))
                break
        else:
            print("Unable to extract byte count ??")
        files[1].close()

        # Count number of sent / received files from tar logs
        counts = []
        for file_h in (files[0], files[2]):
            file_h.seek(0)
            count = 0
            for line in file_h:
                if line.strip():
                    count += 1
            counts.append(count)
            file_h.close()

        if counts[0] != counts[1]:
            raise self.SessionError("Mis-match in files count! "
                                    "{0}:{1} ".format(counts[0], counts[1]))

        if counts[1] != len(file_list) and not dir_xfer:
            raise self.SessionError("Wrong number of files transferred!")

        return total_sz


    def get_files(self, remote_pattern=r'[^.].*', quiet=False, callback=None):
        """
        Retrieves files from the remote server matching remote_pattern (can
        include relative or absolute leading directories) into CWD. Returns
        total received size in bytes. When called without a pattern retrieves
        all files that don't start with '.' in the directory.
          callback: GetFilesCallback object
        """
        self._ssh.check_connected()

        orig_dir = self.get_cwd()

        (head, tail_pat) = os.path.split(remote_pattern)
        if head:
            self.cd(head)
    
        if tail_pat in self.dir_names():
            # Download a directory
            f_names = [tail_pat,]
            dir_xfer = True
        else:
            f_names = self.file_names(tail_pat)
            dir_xfer = False

        if not f_names:
            missing_path = self.get_cwd() + "/" + tail_pat
            if head:
                self.cd(orig_dir)
            raise self.RemoteFileError(self._ssh, missing_path)

        print_next = 1
        total_size = 0
        start_time = time.time()

        # Callback setup
        callback_time = 0.0
        if callback:
            if dir_xfer:
                if head:
                    self.cd(orig_dir)
                raise self.SessionError("Callbacks not supported when"
                                        "transferring a directory!")
            cb_files = []
            callback.error = False
            callback.complete = False
            cb_name = callback.desc  # Save this now in case of errors

        if callback:
            step = max(callback.limit, 1)
        else:
            # Process in parts; minimum of 256 at a time
            step = max(len(f_names)//8, 256)

        for i in range(0, len(f_names), step):
            try:
                total_size += self._get_files(f_names[i:i+step])
            except:
                # If there is an error, put us back in original dir
                if head:
                    self.cd(orig_dir)
                raise

            # Progress output
            if i + step > print_next:
                while print_next < min(i + step, len(f_names)):
                    if not quiet:
                        print(print_next, end=' ')
                    print_next *= 2
                try:
                    # When runing within matlab, this call fails
                    sys.stdout.flush()
                except:
                    pass

            if callback:
                cb_files = f_names[i:i+step]

                # len(cb_files) is always >= 1 at this point
                cb_start_time = time.time()
                try:
                    if callback.func(cb_files) != len(cb_files):
                        raise callback.error("Bad count from callback!")
                except BaseException as err:
                    # Handle exception here and set callback['error']
                    print("Error in callback [%s]: %s" % (cb_name,
                                                          str(err)))
                    callback.error = True
                    callback = None  # don't try to process any additional
                end_time = time.time()
                callback_time += end_time - cb_start_time

        if not quiet:
            print(":: total %d" % len(f_names))

        if callback:
            callback.complete = True  # Only set once all files are processed

        # Make sure directory is sync-ed
        dir_d = os.open('.', os.O_RDONLY)
        os.fsync(dir_d)
        os.close(dir_d)
        del dir_d

        if not quiet:
            retrv_time = time.time() - start_time - callback_time
            if dir_xfer:
                msg = 'Retrieved "{0}" directory, {2:0.1f}s [{3} @ {4}/s]'
            else:
                msg = 'Retrieved "{0}": {1} files, {2:0.1f}s [{3} @ {4}/s]'
            print(msg.format(remote_pattern,
                             len(f_names),
                             retrv_time,
                             pretty_bytes(total_size),
                             pretty_bytes(total_size / retrv_time)))
            if callback_time > 0.0:
                print('%s callbacks [%s]; took %0.1fs'
                      % ("Performed" if callback else "Attempted",
                         cb_name,
                         callback_time))

        if head:
            self.cd(orig_dir)

        return total_size


if __name__ == '__main__':
    # Ugly, but it works... otherwise 'site' is a standard package
    sys.path.insert(0, '..')
    from ar_lib.arsite import *

    if KEYFILE is None:
        KEYFILE = updir + '/id_recon'

    def _pstree():
        if not DEBUG:
            return
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
    sess = SSH(host, USERNAME, KEYFILE, standalone=SSH_CONF)
    sess = SSH(host, USERNAME, KEYFILE, standalone=SSH_CONF)

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
    ssh_dir = os.path.dirname(os.path.abspath(__file__))
    sess = SSH(host, USERNAME, KEYFILE, standalone=SSH_CONF,
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

    #sf = SFTP(host, USERNAME, KEYFILE, standalone=SSH_CONF)
