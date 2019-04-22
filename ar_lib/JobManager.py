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
JobManager class definitions & helpers.
"""
from __future__ import print_function

import contextlib
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import threading

import posixpath as ppath

from collections import namedtuple
from tempfile import TemporaryFile
from textwrap import dedent
from time import time, sleep

from . import ssh
from .dicom import DicomDest
from .util import print_out, pretty_bytes, MD5Wrapper, flatten
from .site import \
        AE_TITLE, \
        CONTACT, \
        DEFAULT_RECON_MACHINES, \
        EXPORT_PATH, \
        HARD_RETRIES, \
        KEYFILE, \
        MAX_PUSH_TIME, \
        SOFT_RETRIES, \
        SSH_CONF, \
        USERNAME

# Set RT_DEBUG to something other than '0' for debug mode.
DEBUG = os.environ.get('RT_DEBUG', '0') != '0'
DARWIN = os.uname()[0] == 'Darwin'
MOD_DIR = os.path.abspath(__file__)
# Want to get to folder above the one containing this file.. so twice
MOD_DIR = os.path.dirname(MOD_DIR)
MOD_DIR = os.path.dirname(MOD_DIR)
SSH_EXE = os.path.join(MOD_DIR, "ar_lib", "ssh_wrapper")

# Check if keyfile is available
if KEYFILE is None:
    KEYFILE = os.path.join(MOD_DIR, 'id_recon')

if not os.path.exists(KEYFILE):
    print("ERROR: REQUIRED FILE [{0}] DOES NOT EXIST!".format(KEYFILE))
    exit(1)


def remote_file(name, copy=False, delete=False):
    "Helper function for building remote file desciption tuples."
    if not (isinstance(copy, bool) and isinstance(copy, bool)):
        raise ValueError("'copy' and 'delete' must be booleans.")
    if not isinstance(name, str):
        raise ValueError("'name' must be a string.")
    return (name, copy, delete)


class GetFilesCallback(object):
    """
    Class to describe callback for get_files().
    All attributes other than 'error' and 'complete' are immutable after
    construction.

    Attributes:
    func:callback function. Called with ([file, <file, ...>])
    timeout: DEPRECATED
    limit:Maximum number of files per call. Defaults to 512.
    error:True/False <output> - Set True if error occured
    complete:True/False <output> - Set True when run (possibly errored)
    """

    CBack = namedtuple('Callback', 'func timeout limit desc')

    def __init__(self, func, timeout=None, limit=512, desc=''):
        """
        Construct a callback object for get_files calls
        """
        # Immutable
        self.__dict__['c'] = GetFilesCallback.CBack(func,
                                                    None,
                                                    int(limit),
                                                    desc)
        self.error = False  # Set to true if errored
        self.complete = False  # Set to true on completion

    def __getattr__(self, name):
        if name in self.__dict__['c']._fields:
            return getattr(self.c, name)
        try:
            return self.__dict__[name]
        except:
            raise AttributeError("no attribute: %s" % name)

    def __setattr__(self, attr, value):
        """
        Only 'error' and 'complete' can be modified in this way.
        """
        estring = None
        if attr in ('error', 'complete'):
            if value.__class__ is bool:
                self.__dict__[attr] = value
            else:
                estring = '[%s] must be bool' % attr
        else:
            estring = '[%s] does not exist or cannot change.' % attr
        if estring is not None:
            raise AttributeError(estring)

    def __repr__(self):
        status = "GetFilesCallback object: %s" % self.desc
        if self.error:
            status += "; ERRORED"
        if self.complete:
            status += "; completed"
        else:
            status += "; INCOMPLETE"
        return status


class JobManager(object):
    """
    Used to manage a job transfer / recieve session with a reconstuction
    (ftp) server
    """
    if DARWIN:
        # Used for testing on OSX; MacPorts dcmtk installed.
        # For Homebrew; use /usr/local/bin
        DCM_DIR = "/opt/local/bin"
        try:
            DISABLE_PUSH = os.environ['DISABLE_PUSH'] == '1'
        except KeyError:
            DISABLE_PUSH = False
        export_path = './'
    else:
        # Linux MRI host settings. Use our compiled dicom/storescu from dcmtk
        DCM_DIR = os.path.join(MOD_DIR, "dicom")
        os.environ['DCMDICTPATH'] = os.path.join(DCM_DIR, 'dicom.dic')

        # If this file exists, don't push outside of localhost
        DISABLE_PUSH = os.path.exists(os.path.join(MOD_DIR, 'dcm.hold'))
        if EXPORT_PATH is None:
            export_path = '/export/home1/sdc_image_pool/import/'
        else:
            export_path = EXPORT_PATH

    if export_path[-1] != '/':
        export_path = export_path + '/'

    __TMP = (os.path.join(DCM_DIR, "storescu"),
             "--call {aet}",
             "--aetitle " + AE_TITLE,
             "--log-level info",
             "--timeout 15")
    PUSH_CMD = ' '.join(__TMP + ("{ip} {port}",)) + ' '
    PUSH_CMD_DIR = ' '.join(__TMP + ("--scan-directories",
                                     "{ip} {port}",
                                     "{dir}"))
    __TMP = None

    class JobErrors(Exception):
        pass

    class NotConnected(JobErrors):
        def __repr__(self):
            return "JobManager not connected!"

        def __str__(self):
            return repr(self)

    class FileError(JobErrors):
        def __init__(self, fileNameIn=""):
            JobManager.JobErrors.__init__(self)
            self.file_name = fileNameIn

        def __repr__(self):
            return "Unable to access file [%s]" % self.file_name

        def __str__(self):
            return repr(self)

    class ConnectionError(JobErrors):
        def __repr__(self):
            return "Unable to open connection!"

        def __str__(self):
            return repr(self)

    class PushError(JobErrors):
        def __repr__(self):
            return ("Error during DICOM push operation:\n"
                    "  [{0}]".format(self.message))

        def __str__(self):
            return repr(self)

    class SessionError(JobErrors):
        def __repr__(self):
            return "Error during session [%s]" % self.message

        def __str__(self):
            return repr(self)

    class RemoteFileError(JobErrors):
        def __init__(self, file_name="", machine_name=""):
            JobManager.JobErrors.__init__(self)
            self.file_name = file_name
            self.machine_name = machine_name

        def __repr__(self):
            return ("Tried to access %s on %s; does not exist!" %
                    (self.file_name, self.machine_name))

        def __str__(self):
            return repr(self)

    def __init__(self,
                 machines=DEFAULT_RECON_MACHINES, # Def in site.py / site-*.py
                 user=USERNAME,
                 keyfile=None):
        """
        Connects to the first working server in machines with the user
        and keyfile specified
        """
        self.tx_size = 2**16
        self.user_name = user
        # Use default ID if available and not provided
        if keyfile is None:
            self.keyfile = KEYFILE
        else:
            self.keyfile = keyfile
        if self.keyfile is None:
            raise self.SessionError("No valid ID found for connection.")
        self.machine_name = None
        self.cwd = None
        self.make_connection(machines=machines,
                            user=self.user_name,
                            keyfile=self.keyfile)

    def __setattr__(self, attr, value):
        """
        Performs checking of attribute names for allowed ones.
        """
        if attr in ('machine_name', 'user_name', 'keyfile', 'base',
                    'cwd', 'tx_size', 'S'):
            self.__dict__[attr] = value
        else:
            raise AttributeError(attr + ' not allowed')

    # Parallel job setup
    # Used while printing error messages in threaded section to avoid
    # inter-mingling of messages when calling print()

    PRINT_LOCK = threading.RLock()
    _REAL_PRINT = print
    MAIN_THREAD = threading.current_thread().ident
    JOB_GATE = threading.BoundedSemaphore(value=6)  # Max 6 parallel jobs

    @staticmethod
    def print_serial(*args, **kwargs):
        "Print under PRINT_LOCK"
        with JobManager.PRINT_LOCK:
            tid = threading.current_thread()
            if tid.ident != JobManager.MAIN_THREAD:
                JobManager._REAL_PRINT("[{0}] ".format(tid.name),
                                       end='')
            JobManager._REAL_PRINT(*args, **kwargs)

    @staticmethod
    @contextlib.contextmanager
    def serialized_printing():
        "Handles rerouting all prints through print_serial"
        global print
        print = JobManager.print_serial     #pylint: disable=W0622
        try:
            yield
        finally:
            print = JobManager._REAL_PRINT

    @staticmethod
    def cleanup(to_delete):
        """
        Removes the files (keys = names) in the dictonary to_delete
        where value[2] == True
        """
        for key in to_delete:
            if to_delete[key][2]:
                print("Deleting file [%s]" % key)
                os.unlink(key)

    @staticmethod
    def dir_suffix():
        """
        Returns a PID-unique suffix; Used during retrieve_dir and import_dir
        operations.
        """
        if DARWIN:
            return ""
        return ".%d" % os.getpid()

    @staticmethod
    def import_dir(dir_name):
        """
        Moves the dir_name.<PID> folder in the sdc_image_pool/import directory
        to dir_name.sdcopen and waits for it to disappear (after GE imports it.)
        """
        oldDirName = JobManager.import_dir_name(dir_name)
        newDirName = oldDirName + ".sdcopen"
        os.rename(oldDirName, newDirName)
        print("Waiting for GE system to import %s" % newDirName, end='')
        sys.stdout.flush()
        while os.access(newDirName, os.F_OK):
            sleep(0.2)
            sys.stdout.write(".")
            sys.stdout.flush()
        print("complete")

    @staticmethod
    def import_dir_name(dir_name):
        "Returns the the full path for the import directory dir_name identifies"
        return os.path.join(JobManager.export_path,
                            dir_name + JobManager.dir_suffix())

    @staticmethod
    def __push(cmd_line,
               dest,
               error_message="Pushing DICOM failed in __push!"):
        # If DISABLE_PUSH is true, only permit local DICOM pushes.
        if JobManager.DISABLE_PUSH and dest.ip not in ("127.0.0.1",
                                                       "localhost",
                                                       platform.node()):
            msg = "REMOTE PUSH DISABLED (dcm.hold exists.) Skipping: "
            raise JobManager.PushError(msg + repr(dest))

        retries = SOFT_RETRIES
        hard_failure = HARD_RETRIES # Times to retry hard errors

        while retries > 0:
            proc = subprocess.Popen(shlex.split(cmd_line.encode('ascii')),
                                    bufsize=4096,
                                    close_fds=True,
                                    stdin=open('/dev/null', 'r'),
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    universal_newlines=True)

            # Wait for process to finish
            (dcm_out, dcm_err) = proc.communicate()

            if proc.returncode == 0:
                break  # success!

            if 'Transient' in dcm_err:
                print("Transient error. Will retry {0} {1} times."
                      .format(dest, retries))
                retries -= 1
                sleep(5)
                continue
            elif hard_failure > 0:
                with JobManager.PRINT_LOCK:
                    print(" +--- Experienced hard failure during push to {0}:"
                          .format(dest))
                    print(" +--- Command: [{0}{1}]"
                          .format(cmd_line[0:160],
                                  "..." if len(cmd_line) >= 160 else ""))
                    print_out((dcm_out, dcm_err))
                    print(" +--- Will retry every minute.")
                    print(" +--- {0} retries remain.".format(hard_failure))
                hard_failure -= 1
                sleep(60)
                continue

            # success or had (10 transient or 15 hard failures)
            break

        # Check to see if everything worked
        if proc.returncode != 0:
            with JobManager.PRINT_LOCK:
                print(" +--- Error during DICOM send. Returned [{0}]"
                      .format(proc.returncode))
                print_out((dcm_out, dcm_err))
            raise JobManager.PushError(error_message)

        # See how many images we transferred.
        return dcm_out.count('\n')

    @staticmethod
    def push_files(dest, files):
        """
        A callback suitable for use with GetFilesCallback()

        Raises PushError on error.

        Keyword arguments:
        dest -- push to a given DicomDest
        files -- Array of file names to push
        """
        if not files or dest is None:
            return 0

        # Handle case where multiple destinations are provided
        if '__iter__' in dir(dest):
            for dest_n in dest:
                # Don't accumulate. Will raise an error if wrong number
                # are transferred in any of the executions
                tot = JobManager.push_files(dest_n, files)
            return tot

        # Make sure dest is now a DicomDest object
        if dest.__class__ is not DicomDest:
            raise JobManager.PushError("Only DicomDest objects can be used.")

        pushCommand = JobManager.PUSH_CMD + ' '.join(files)

        try:
            cmd = pushCommand.format(**dest())
            pushed = JobManager.__push(cmd,
                                       dest,
                                       "Failed push: {aet}.".format(**dest()))
            if pushed != len(files):
                raise JobManager.PushError("Did not push enough files!?")
            return pushed
        except JobManager.PushError:
            # Propagate
            raise
        except BaseException as e:
            raise JobManager.PushError(str(e))

    # Define our error handling function
    @staticmethod
    def parallel_handler(e, dest="[unknown]"):
        # Report, but don't raise errors in threads
        with JobManager.PRINT_LOCK:
            print("!!! {0}".format(e))
            print("^^^ Error sub-processing {0}; SKIPPING!"
                  .format(dest))

    @staticmethod
    def serial_handler(e, dest=None):
        # Propagate errors as PushError objects
        if e.__class__ is JobManager.PushError:
            raise e
        else:
            if e.__class__ is str:
                raise JobManager.PushError(e)
            else:
                raise JobManager.PushError(repr(e))

    @staticmethod
    def push_dir(dir_name, dest, handler=serial_handler):
        """
        Use storescu to push sdcopen files in dir_name (relative to GE import
        directory, .<PID> added internally) to the server described in dest.

        Returns the number of images successfully pushed.

        Raises JobManager.PushError on error.

        Keyword arguments:
        dir_name -- Name of directory
        dest --  DicomDest object, or an iterable containing DicomDest objects
        """
        # Handle case of dest==None (no destinations to push to)
        if dest is None:
            return 0

        # Handle (in parallel) case where multiple destinations are provided
        if '__iter__' in dir(dest):
            # Flatten any nested iterables
            dests = []
            flatten(dest, dests)

            def push_thread(push_dest, thread_label):
                return threading.Thread(target=JobManager.push_dir,
                                        args=(dir_name,
                                              push_dest,
                                              JobManager.parallel_handler),
                                        name=thread_label)

            # Using our serialized prints during multi-threaded processing
            print("\n* PERFORMING {0} BACKGROUND DICOM PUSH OPERATIONS\n"
                  .format(len(dests)))
            with JobManager.serialized_printing():
                jobs = []
                tStart = time()
                for n in range(len(dests)):
                    lbl = '{0:02d}:{1}'.format(n, dests[n].aet)
                    jobs.append(push_thread(dests[n], lbl))
                    # Lets us exit without finishing if there is a timeout
                    jobs[-1].daemon = 1
                    jobs[-1].start()
                for j in jobs:
                    # Dicom push jobs must complete in 30 minutes. (Should
                    # be much, much less.)
                    tMinutes = MAX_PUSH_TIME
                    tWait = 60 * tMinutes
                    tWait -= time() - tStart
                    if tWait == 0:  # Awfully unlucky; join(0) blocks forever
                        tWait = -1
                    j.join(tWait)
                    if j.isAlive():
                        print("{0} still alive after {1} minutes. Abandoning!"
                              .format(j.name, tMinutes))
                elapsed = int(round(time() - tStart))
            print("\n* FINISHED BACKGROUND DICOM PUSHES IN {0}:{1:02d}.\n"
                  .format(elapsed // 60, elapsed % 60))
            return

        # Make sure dest is now a DicomDest object
        if dest.__class__ is not DicomDest:
            handler("Only DicomDest objects can be used!")
            return 0

        pushCommand = JobManager.PUSH_CMD_DIR

        try:
            job = dest().copy()
            job['dir'] = JobManager.import_dir_name(dir_name)
            job['shortDir'] = dir_name
            cmd = pushCommand.format(**job)
            # JOB_GATE only permits the specified number of threads to enter
            # this section (where the actual SENDs occur) concurrently.
            with JobManager.JOB_GATE:
                print("Pushing '{shortDir}' directory to {aet} [{ip}:{port}]"
                      .format(dir_name, **job))

                startTime = time()
                pushed = JobManager.__push(cmd,
                                           dest,
                                           "Failed push of {dir} to {aet}."
                                           .format(**job))

                jobTime = time() - startTime
                print("Successfully pushed {0} images from '{shortDir}' to "
                      "{aet} in {1:.1f}s"
                      .format(pushed, jobTime, **job))

            return pushed

        except BaseException as e:
            handler(e, dest)  # May not raise error if in parallel mode
            return 0  # Just for clarity

    @staticmethod
    def remove_import_dir(dir_name):
        "Removes the import directory identified by dir_name."
        dir_name = JobManager.import_dir_name(dir_name)
        if dir_name == "/" or dir_name == "":
            print("Refusing to try to remove '{0}'".format(dir_name))
            return
        shutil.rmtree(dir_name)
        print("Removed {0}.".format(dir_name))

    def check_connected(self):
        """
        Used to ensure the server is connected. Raises NotConnected if the
        session is not connected to an FTP server.
        """
        if not self.is_connected():
            raise self.NotConnected()

    def cur_dir(self):
        """
        We report only the section rooted inside our initial (~) directory.
        """
        return self.cwd[len(self.base):]

    def dir_names(self):
        """
        Returns the directories in the current directory
        """
        self.check_connected()
        return self.listing(dir_mode=True)

    def disconnect(self):
        """
        Disconnects from the server
        """
        if self.is_connected():
            self.S.close()
            self.machine_name = None

    def enter_dir(self, dir_name, create_dir=True, create_parents=False):
        """
        Enters the directory dir_name on server; can be relative or absolute.
        Can optionally create the directory or the directory and parents.
        """
        self.check_connected()

        while dir_name[-1:] == '/':
            dir_name = dir_name[0:-1]  # remove trailing slash(es)

        if not dir_name:
            return

        if ' ' in dir_name:
            raise self.SessionError("Spaces in dir_name within enter_dir()"
                                    " are not supported.")

        if dir_name[0] == '/':
            # Absolute path (rel to base)
            self.cwd = self.base
            # Remove leading slash
            dir_name = dir_name[1:]

        # Handle . .. ../ etc. using posixpath
        dir_name = ppath.normpath(ppath.join(self.cwd, dir_name))

        if len(dir_name) < len(self.base):
            raise self.SessionError("Tried to escape starting directory!")

        # We now have (foo/)*bar
        head = ppath.dirname(dir_name)

        for (pth, create) in zip((head, dir_name),
                                 (create_parents, create_dir)):
            try:
                # If it exists and we can move into it, we're done
                self.S.check_call("test -x '{0}' -a -w '{0}'".format(pth))
            except Exception:
                # pth doesn't exist
                if create:
                    try:
                        self.S.check_call("mkdir -p '{0}'".format(pth))
                        print("Created [{0}]".format(pth))
                    except:
                        raise self.SessionError("Unable to create path {0}"
                                                .format(pth))
                else:
                    raise self.SessionError("Path [{0}] don't exist!"
                                            .format(pth))

        # If we are here, we've made the directory and can move into it
        self.cwd = dir_name
        print("Entered [{0}]".format(self.cwd))

    def file_names(self):
        """
        Returns the files in the current directory
        """
        self.check_connected()
        return self.listing(dir_mode=False)

    def get_file(self, remote_name, local_path, quiet=False, check_exist=True):
        """
        Retrieves one file from the remote server at remote_name and
        stores it at local_path. Returns received file size in bytes.
        """
        self.check_connected()

        if check_exist:  # Don't get listings again if we know it exists
            if remote_name not in self.file_names():
                raise self.RemoteFileError(ppath.join(self.cur_dir(),
                                                      remote_name),
                                           self.machine_name)

        # Open local file for writing
        try:
            lcl_file = open(local_path, 'wb')
        except:
            raise self.FileError(local_path)

        startTime = time()
        rpath = ppath.join(self.cwd, remote_name)

        # Open remote file for reading
        with lcl_file:
            try:
                fr = self.S.run("cat '{0}'".format(rpath),
                                stdout=lcl_file,
                                stderr=subprocess.PIPE,
                                universal_newlines=False)
                fr.wait()
                size = lcl_file.tell()
                os.fsync(lcl_file.fileno())
                if fr.returncode:
                    raise subprocess.CalledProcessError(fr.returncode,
                                                        "Error during send.")
            except Exception as e:
                for l in fr.stderr:
                    print(l.rstrip())
                raise self.SessionError("Unable to retrieve file: %s [%s]" %
                                        (remote_name, repr(e)))

        retrTime = time() - startTime

        if not quiet:
            if remote_name != local_path:
                print ("Retrieved %s as %s: %s in %fs [%s/s]" %
                       (remote_name,
                        local_path,
                        pretty_bytes(size),
                        retrTime,
                        pretty_bytes(size / retrTime)))
            else:
                print ("Retrieved %s: %s in %fs [%s/s]" %
                       (remote_name,
                        pretty_bytes(size),
                        retrTime,
                        pretty_bytes(size / retrTime)))
        return size

    def get_files(self, remote_pattern=r'.*', quiet=False, callback=None):
        """
        Retrieves files from the remote server matching remote_pattern (can
        include relative or absolute leading directories) into CWD. Returns
        total received size in bytes.
          callback: GetFilesCallback object
        """
        self.check_connected()

        sftp = ssh.SFTP(self.S)
        sftp.cd(self.cur_dir())
        return sftp.get_files(remote_pattern, quiet, callback)

    def is_connected(self):
        """
        Returns, without raising an exception, connected state (True/False)
        """
        return self.machine_name is not None

    def listing(self, dir_mode=False):
        """
        Returns an array file names unless dir_mode is true (then dir names)
        in the current directory
        """
        self.check_connected()
        mode = 'd' if dir_mode else 'f'

        listcommand = "cd '{0}' && ".format(self.cwd) + \
                      "find -L . -maxdepth 1 -type {0} ".format(mode) + \
                      "-print0"
        output = self.S.check_output(listcommand,
                                     universal_newlines=False)[0].split('\0')
        lst = []
        for x in output:
            if len(x):
                lst.append(x[2:])
        lst = sorted(lst)
        if DEBUG:
            print(lst)
        return lst

    def make_connection(self, machines, user, keyfile):
        """
        Connects the FTP session.
        """
        self.user_name = user
        self.keyfile = keyfile
        self.machine_name = None
        for m in machines:
            try:
                self.S = ssh.SSH(m,
                                 user,
                                 keyfile,
                                 executable=SSH_EXE,
                                 standalone=SSH_CONF)
            except Exception as e:
                print("Unable to connect to machine %s [%s] "
                      "trying next connection." % (m, str(e)))
                continue
            self.machine_name = m
            break
        else:
            raise self.ConnectionError()

        # Record starting directory; make us stay inside it later
        self.base = self.S.check_output("pwd")[0].split('\n')[0].strip()
        self.cwd = self.base

    def remove_file(self, file_name):
        """
        Removes file_name from the current directory.

        Raises RemoteFileError if the file doesn't exist.
        """
        self.check_connected()
        if file_name not in self.listing():
            raise self.RemoteFileError(file_name,
                                       self.machine_name)
        self.S.check_call("rm -f '{0}'".format(ppath.join(self.cwd,
                                                          file_name)))

    def retrieve_dir(self,
                     dir_name,
                     extra_dest=None,
                     callback=None):
        """
        retrieves all .sdcopen files from the dir_name dir
        (relative to current remote path) into the GE import directory
        in a subdirectory named dir_name.<PID>
          Callback: GetFilesCallback object
        """
        self.check_connected()
        currentPath = os.getcwd()
        # Actually receive into the level above EXPORT_PATH to avoid having GE
        # delete the directory while we try to recieve into it
        retrieveTmp = \
          os.path.join(os.path.dirname(JobManager.export_path),
                       "mar_tmp_" + dir_name + JobManager.dir_suffix())
        os.mkdir(retrieveTmp)
        os.chdir(retrieveTmp)
        self.get_files(dir_name + r"/.*\.sdcopen",
                      callback=callback)
        if extra_dest:
            try:
                shutil.copytree(retrieveTmp, extra_dest)
            except shutil.Error as e:
                print("Error copying files to extra destination: " + extra_dest)
                print("Error: ", e)
                print("Continuing...")

        os.chdir(currentPath)
        # Move temporary retrieve dir into EXPORT_PATH
        retrieveDest = JobManager.import_dir_name(dir_name)
        shutil.move(retrieveTmp, retrieveDest)

    def start_and_wait_job(self, token_name_in, outdir=""):
        """
        Kicks off reconstruction (by placing the tokenName file)
        and waits for completion.
        If outdir is provided, look for completion tokens in outdir. Will
        be in outdir after returning from call.
        """

        # Early exit if no job name (no job to run)
        if not token_name_in:
            return

        # Make a unique (enough) token name
        # The next possible occurence is when the pid wraps on this host
        tokenName = "{0}.{1}.{2}".format(token_name_in,
                                         platform.node().split('.')[0],
                                         os.getpid())

        self.check_connected()

        # Create and send key file

        token = TemporaryFile()
        token.write(self.cur_dir().split('/')[-1] + "\n")
        token.seek(0, 0)

        try:
            print("Sending session information in ../%s" % tokenName)
            self.S.check_call("cd '{0}' && "
                              "cat > '{1}' && "
                              "mv '{1}' '../{2}'".format(self.cwd,
                                                         '.sftp_tmp',
                                                         tokenName),
                              stdin=token)
        except Exception as e:
            raise self.SessionError("Unable to open send ../%s\n"
                                    "---> Error: [%s]" %
                                    (tokenName, str(e)))
        finally:
            token.close()

        print("Sending files complete; wating for checksum...")


        self.wait_file(ppath.join(outdir, "md5_done"))
        if outdir:
            self.enter_dir(outdir, create_dir=False)
        self.remove_file("md5_done")

        print(dedent(
              """
              ---------------
              Files transferred to reconstruction system and verified.
              Reconstruction may take up to ten minutes, please be patient.
              Should reconstruction fail, the raw data has been stored.
              This script will timeout after sixty minutes.
              ---------------
              """))

        self.wait_file("done", 3600)
        # Remove "done" file from server
        self.remove_file("done")

    def store_file(self, local_path, remote_name, quiet=False, md5Map=None):
        """
        Sends the file at local_path to the remote server at remote_name
        """
        self.check_connected()

        def storeError(e):
            return self.SessionError("Unable to transfer local file [%s] "
                                     "as [%s] :: Error: [%s]" %
                                     (local_path, remote_name, str(e)))

        if not os.path.exists(local_path):
            raise storeError("Local file does not exist!")

        REPORT_SIZE = 128 * 2**20
        startTime = time()

        def updateUser(s, sz):
            # Print transfer progress for files >= 128 MB
            if sz >= REPORT_SIZE:
                if s >= sz:
                    print('100%')
                elif s * 10 // sz > (s - self.tx_size) * 10 // sz:
                    print('%d' % (s * 100 // sz), end='% ')

        try:
            with open(local_path, 'r', buffering=0) as f:
                # Get size for progress
                f.seek(0, os.SEEK_END)
                SIZE = f.tell()
                f.seek(0, os.SEEK_SET)

                if SIZE >= REPORT_SIZE:
                    print("Transfer progress [%s]: " % remote_name, end='')

                # Create checksum wrapper
                f_md5 = MD5Wrapper(f)
                sent = 0
                rpath = ppath.join(self.cwd, remote_name)

                # Use an SSH session running cat into the desired filename
                # on the far side for transfer.
                xf = self.S.run("cat > '{0}'".format(rpath),
                                stdin=subprocess.PIPE,
                                bufsize=2*self.tx_size)

                while 1:
                    data = f_md5.read(self.tx_size)
                    if len(data) == 0:
                        break
                    xf.stdin.write(data)
                    sent += len(data)
                    updateUser(sent, SIZE)

                xf.communicate()
                if xf.returncode:
                    for l in xf.stdout:
                        print(l.rstrip())
                    raise IOError("SSH process closed unexpectedly!")

                md5 = f_md5.hexdigest()
                f_md5 = None
                if sent != SIZE:
                    raise IOError("Transferred size not expected size!")

        except Exception as e:
            raise storeError(e)

        storTime = time() - startTime

        if not quiet:
            print("Store [%s #%s] -> [%s] %s in %.1fs [%s/s]" %
                  (local_path,
                   md5[0:8].upper(),
                   remote_name,
                   pretty_bytes(SIZE),
                   storTime,
                   pretty_bytes(SIZE / storTime)))

        if md5Map is not None:
            md5Map[remote_name] = md5

        return SIZE

    def store_files(self, files, set_quiet=True):
        """
        Sends a set of files defines in a dictionary where:
            key = local file name
            value = (Remote file name (relative),
                     True to copy into WORK_DIR,
                     True to delete after success)

        Note: store_files DOES NOT perform the copy or deletion actions, but
        will mark the delete after success as False if the transfer fails
        as a precaution.

        Returns a dictionary of {remoteName: md5 checksum}
        """
        self.check_connected()
        size = 0
        count = 0
        errCount = 0
        errList = []
        md5s = {}
        startTime = time()

        for key in sorted(files):
            try:
                size += self.store_file(key,
                                       files[key][0],
                                       quiet=set_quiet,
                                       md5Map=md5s)
                count += 1
            except self.JobErrors as e:
                print("Error storing file %s as %s; continuing.\n"
                      "  Error: [%s]" % (key, files[key][0], str(e)))
                # Never delete errored files
                files[key] = (files[key][0], files[key][1], False)
                errCount += 1
                errList.append(key)
                sleep(1)

        storTime = time() - startTime
        print("\n  Stored and checksummed %i file[s] totaling "
              "%s in %.1fs [%s/s]\n" %
              (count,
               pretty_bytes(size),
               storTime,
               pretty_bytes(size / storTime)))

        if errCount:
            raise self.SessionError("Unable to send %i file[s] (%s) "
                                    "in store_files()" %
                                    (errCount, str(errList)))

        return md5s

    def wait_file(self, file_name, timeout=1800, interval=1):
        """
        Waits for the reqested file to appear on the remote site.
        """
        # Rather than keep polling with ssh transfer attempts, just run a
        # shell script on the remote server.

        self.check_connected()
        rshell = self.S.run("cd '{0}' && bash -s".format(self.cwd),
                            stdout=None,
                            stdin=subprocess.PIPE,
                            bufsize=0)

        # Make the sleep interval an integer >= 1
        interval = max(1, int(round(interval)))

        # Make the timeout an integer
        timeout = int(round(timeout))

        # DO NOT REMOVE the final exit 0!
        # If we ever wait, the return value is from the last executed line
        # INSIDE THE LOOP (not the test.) If the file appears, the last
        # executed line is the (failing) (( t <= 0 )) test; and we would return
        # an exit code of 1, even though the file appeared. (If we never
        # enter the loop, $? == 0, and we would work by accident.)
        cmd = dedent(
           """
           let t={0}
           until [ -e "{1}" ]; do
             let r=t/60
             (( t%60 == 0 )) && date +"%T: Will wait for $r minutes..."
             sleep {2}
             let t-={2}
             (( t <= 0 )) && exit 1
           done
           exit 0  # DO NOT REMOVE
           """).format(timeout, file_name, interval)
        if DEBUG:
            print("Waiting for [{0}]; running via ssh:".format(file_name))
            print(cmd)
        rshell.stdin.write(cmd)
        rshell.stdin.close()

        rshell.wait()

        if rshell.returncode:
            print(dedent("""
                         Waited for file [{0}]; never appeared!
                         Contact {1} for help.
                         """).format(file_name, CONTACT))
            raise self.SessionError("File never appeared [{0}]!"
                                    .format(file_name))

# vim: ts=4:sw=4:et
