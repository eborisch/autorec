#!/usr/bin/env python
# vim: set expandtab ts=4 sw=4:

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

import datetime
import traceback
import os
import shutil
import socket
import sys
import time

import posixpath as ppath

from ar_lib.JobManager import \
        JobManager, \
        GetFilesCallback, \
        MOD_DIR, \
        remote_file
from ar_lib.dicom import DicomDest
from ar_lib.tee import Tee
# run_cmd is imported to be available in conf.py executions.
from ar_lib.util import settle_file, run_cmd, get_fid
# import * as user-provided site-*.py functions need to be included
from ar_lib.arsite import *

now = datetime.datetime.now
pjoin = os.path.join

# Don't write world-writable files/dirs
os.umask(0x2)

# Arguments
#  1  pfile#
#  2  #scans/Series
#  3  ??
#  4  exam#
#  5  series#
#  6  next image #

###############################################################
# (0) Setup logging & initialize SFTP connection ###############
###############################################################

# Set up TIME_STAMP
TIME_STAMP = now()
SHORT_DATE = TIME_STAMP.strftime('%Y_%m_%d')

# Parse args
if len(sys.argv) < 7:
    print("Expected 6 arguments!")

PFILE_N = 0
EXAM = os.getpid()  # If it's not changed below, make somewhat unique
SERIES = 0

try:
    if len(sys.argv) >= 2:
        PFILE_N = int(sys.argv[1])
    if len(sys.argv) >= 5:
        EXAM = int(sys.argv[4])
    if len(sys.argv) >= 6:
        SERIES = int(sys.argv[5])
except ValueError:
    print("Unable to parse args as int()s; continuing...")

HOSTNAME = socket.gethostname().split('.')[0]

if LOCAL_AET is None:
    LOCAL_AET = HOSTNAME


# This exam's name; YEAR_MONTH_DAY_EXAM_SERIES_HOST
EXAM_DIR = "%s_%d_%02d_%s" % (SHORT_DATE, EXAM, SERIES, HOSTNAME)

# Figure out what recon we're running
RECON_NAME = os.path.basename(sys.argv[0])

if RECON_NAME == 'autorec.py':
    print("""
WARNING: autorec.py must be called via a link (hard or soft) that is the
name of the desired recon. (e.g. recon1723) autorec.py will look for the
configuration files (for example) recon1723/conf.py and (optionally)
recon1723/pre.py and recon1723/post.py in the directory:
{0}""".format(MOD_DIR))
    quit(1)

# Setup work/logging dir ... add trailing slash to support trivial '+'
WORK_DIR = pjoin(MOD_DIR, RECON_NAME, "logs", EXAM_DIR) + os.sep

# Make the work directory
if not os.access(WORK_DIR, os.W_OK):
    os.makedirs(WORK_DIR)

# Start the log of this script
LOGGER = Tee(pjoin(WORK_DIR, "Runlog.%d" % os.getpid()))

print("Starting autorec script at: %s" % TIME_STAMP.ctime())
print("Invocation [%s]\n" % ' '.join(sys.argv))

os.chdir(WORK_DIR)  # Move ourselves into the work/log dir

PRE_SCRIPT_NAME = pjoin(MOD_DIR, RECON_NAME, "pre.py")
CONF_SCRIPT_NAME = pjoin(MOD_DIR, RECON_NAME, "conf.py")
POST_SCRIPT_NAME = pjoin(MOD_DIR, RECON_NAME, "post.py")

# conf.py is required; error if missing.
if not os.access(CONF_SCRIPT_NAME, os.R_OK):
    raise IOError("Unable to find recon-specific information file: " +
                  CONF_SCRIPT_NAME)

##############################################################################
## Run pre.py (if it exists) #################################################
##############################################################################
# pre.py is an optional script; no error if missing.

jobArgs = {}

if os.access(PRE_SCRIPT_NAME, os.R_OK):
    print("Executing pre.py script...")
    # Variable that can be defined in pre.py:
    # jobArgs: keyword-dictionary of arguments for JobManager creation below.
    recon_vars = locals().copy()
    execfile(PRE_SCRIPT_NAME, recon_vars)

    # Extract jobArgs
    if 'jobArgs' in recon_vars:
        jobArgs = recon_vars['jobArgs']
    del recon_vars

###############
# (0) Connect #
###############
# Connects to first working host (listed in autorec_utils.py)
# unless otherwise directed by pre.py script

try:
    MGR = JobManager(**jobArgs)
except JobManager.ConnectionError:
    MGR = None
    print("""
Unable to make a connection; checking to see if any files should be copied
locally for safe keeping before exiting.
""")

##############################################################################
## Run conf.py ###############################################################
##############################################################################
# Variables that must be assigned in the <RECON_NAME>/conf.py file:
# jobsDir    = path to directory this job will be placed into
# tokenName  = name of the file created in jobsDir to kickoff recon
# sendFiles  = Dictionary of files to send.
#
# Optional variables that can be assigned:
# mipCopy = Additional directory to copy resulting MIP DICOMs to
# imgCopy = Additional directory to copy resulting image DICOMs to
# getMip = Retrieve and import "mip" directory (defaults to true)
# getImg = Retrieve and import "img" directory (defaults to true)
#
# The sendFiles dictionary keys are the local (absolute) paths to files
# for sending, and the values are a tuple of:
# (relative remote name,
#  copy to work/log dir (bool),
#  delete after recon (bool))

sendFiles = {}
reconVars = locals().copy()
# We already checked for existence
try:
    execfile(CONF_SCRIPT_NAME, reconVars)
except Exception as e:
    if MGR is not None:
        print("Unable to execute {0}. ".format(CONF_SCRIPT_NAME) +
              "Will likely fail soon.")
    print("Execution failed: [{0}]".format(e))
    traceback.print_exc()
    # conf script failed; try to make sure we can save files at the minimum
    # Put into incoming/errored if jobsDir not yet set
    reconVars['jobsDir'] = reconVars.get('jobsDir', '/incoming/errored/')
    # Don't use tokenName from script; use special ERROR key
    reconVars['tokenName'] = TIME_STAMP.strftime('ERROR_%Y%m%d_%H%M%S')
    # If sendFiles exists, use that, but add the failing conf.py script
    reconVars['sendFiles'] = reconVars.get('sendFiles', {})
    reconVars['sendFiles'][CONF_SCRIPT_NAME] = ('conf.py', False, False)
    reconVars['sendFiles'][pjoin(WORK_DIR, "Runlog.%d" % os.getpid())] = \
        ('Runlog.%d' % os.getpid(), False, False)

# Below this point, globals aren't used by another (eg conf.py) script; 
# using lower-case variable names. (Well, they may be used by post.py.)

# These have to exist; throw errors (and exit) if they aren't set
jobsDir = reconVars['jobsDir']
tokenName = reconVars['tokenName']
sendFiles = reconVars['sendFiles']

if len(sendFiles) == 0:
    raise ValueError("No send files were defined!")

# Default values for optional variable
opt_value = {'mipCopy': None,
             'imgCopy': None,
             'getMip': False,
             'getImg': True,
             'pushDests': None,
             'pushImport': True,
             'import': True,
             'isolate': False}

# Copy any optional variables that were set
for n in opt_value:
    if n in reconVars:
        opt_value[n] = reconVars[n]


#################################################################
# (1) Check for stability and copy requested files into WORK_DIR #
#################################################################
key_list = sendFiles.keys()  # Need a copy as we will be modifying
for key in key_list:
    # Make sure file is at least 5s old. (i.e. not changing.)
    if get_fid(key) is not None:
        if sendFiles[key][1] or sendFiles[key][2]:
            print("Error: cannot copy or delete stream (fid) files!")
    elif 'Runlog' not in key:
        settle_file(key, 5.0)
    # Copy files if requested OR if system is not connected
    if sendFiles[key][1] or MGR is None:
        # We make our local copies now and send from these copies
        oldKeyData = sendFiles.pop(key)
        copyName = pjoin(WORK_DIR, oldKeyData[0])
        if key != copyName:     # Don't copy files already in WORK_DIR
            shutil.copyfile(key, copyName)
            print("Copied %s -> %s" % (key, copyName))
        # Send from copy in case another scan clobbers.  The copied file will
        # also be the deleted (if set to delete) file.
        # (The original source will _always_ be kept if copy is true.)
        sendFiles[copyName] = oldKeyData

# If we aren't connected, exit at this point (we've copied files so we can
# manually try again later)
if MGR is None:
    print("Exiting after local copies created. Please contact "
          "{0} for manual execution.".format(CONTACT))
    sys.exit(1)

########################################################
# (2) Transfer files to server and calculate checksums #
########################################################
# Move SFTP client into the destination directory
# Using posixpath.join for SFTP locations
MGR.enter_dir(ppath.join(jobsDir, EXAM_DIR), create_parents=1)

print("\nTransfers starting: %s\n" % now().ctime())

md5_sums = MGR.store_files(sendFiles, set_quiet=False)

########################################
# (3) Write out and transfer checksums #
########################################
md5_name = "%d.md5" % EXAM

md5_file = file(pjoin(WORK_DIR, md5_name), 'w')
for k in md5_sums:
    # This is the format expected by the 'md5sum' executable)
    md5_file.write("%s  %s\n" % (md5_sums[k], k))
md5_file.close()

MGR.store_file(pjoin(WORK_DIR, md5_name), md5_name)

print("\nSubmission complete: %s\n" % now().ctime())

del reconVars

###############
# (4) Run Job #
###############
if tokenName:
    start_time = time.time()
    if opt_value['isolate']:
        #NOTE: This will cd into 'latest' on the remote side during call.
        MGR.start_and_wait_job(tokenName, "latest")
    else:
        MGR.start_and_wait_job(tokenName)
    job_time = time.time() - start_time
    print("Reconstruction time (including checksum): %ds\n" % int(job_time))
else:
    print("No reconstruction requested.")

##############################################################################
## Run post.py (if it exists) ################################################
##############################################################################
# post.py is an optional script; no error if missing.
if os.access(POST_SCRIPT_NAME, os.R_OK):
    print("Executing post.py script...")
    execfile(POST_SCRIPT_NAME)

##################################
# (6) Collect and import results #
##################################

for dir_name in ('mip', 'img'):
    # See if we are supposed to retrieve this directory
    # Keeping camel case names for interface.
    if not opt_value['get' + dir_name[0].upper() + dir_name[1:]]:
        continue

    pusher = None  # By default say we have not yet locally pushed.
    if opt_value['import'] and opt_value['pushImport']:
        # This sets up a callback used during retreiveDir() below. It attempts
        # to perform a local dicom push into the scanner database after every
        # 5 seconds or 512 files retrieved, whichever comes first.
        pusher = GetFilesCallback(
            lambda x: JobManager.push_files(DicomDest(aet=LOCAL_AET,
                                                      ip=LOCAL_IP,
                                                      port=LOCAL_PORT), x),
            timeout=5.0,
            limit=512,
            desc='%s push' % LOCAL_AET)

    # Copy directory from reconstruction server; optionally into extra copy.
    # The callback provided pushes into local database. If this fails or was
    # not requested (pusher['error']==True), will use a local import_dir below
    MGR.retrieve_dir(dir_name, opt_value[dir_name + 'Copy'], callback=pusher)
    print("\nRetrieval complete: %s\n" % now().ctime())

    # Perform any remote pushes after potential local push above
    try:
        # Returns without error if 2nd arg is the (default) None.
        MGR.push_dir(dir_name, opt_value['pushDests'])
    except:
        print("Error pushing to:{0}".format(opt_value['pushDests']))
        print("Continuing.")

    # We don't need the remainder of this loop if we're not importing. The
    # retrieved files will be left on the local filesystem.
    if not opt_value['import']:
        continue

    if opt_value['pushImport'] and pusher.complete is True:
        # Requested pushImport above worked; we're done here
        print("Successful import. Removing source directory.")
        try:
            JobManager.remove_import_dir(dir_name)
        except:
            print("Unable to remove {0}? Continuing."
                  .format(JobManager.import_dir_name(dir_name)))
    else:
        # Either we were told not to pushImport, or it failed.  Perform a
        # "Traditional" import. Note the directory is removed in this process.
        MGR.import_dir(dir_name)

################################################
# (7) Removes the files where value[2] == True #
################################################
MGR.cleanup(sendFiles)

print("\nCompletion: " + now().ctime())
