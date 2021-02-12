# vim:set expandtab ts=2 sw=2:
#
# The <reconName>/conf.py external script is responsible for setting up the
# reconstruction.

##########################################################################
# Variables that can be assigned in the <reconName>/conf.py file:
# NOTE: Only these variables will be retained from this script.
#       Other variables can be used within the script, but are not saved.
#
# REQUIRED:
#    jobsDir    = path to directory this job will be placed into
#    tokenName  = name of the file created in jobsDir to kickoff recon
#    sendFiles  = Dictionary of files to send.
#
# OPTIONAL: [default when != None]
#    getImg     = Retrieve and import "img" directory [True]
#    getMip     = Retrieve and import "mip" directory [False]
#    imgCopy    = Additional directory to copy resulting image DICOMs into
#    mipCopy    = Additional directory to copy resulting MIP DICOMs into
#    import     = Perform local imports (overrides pushImport when False) [True]
#    pushDests  = DicomDest (or iterable of) object[s] of additional dests.
#    pushImport = Perform a local push into scanner database [True]
#    isolate    = Remote reconstruction is configured in isolate mode [False]
##########################################################################
#
# Some useful variables defined on entry by autorec:
#
# EXAM          = exam #
# EXAM_DIR      = String name of directory for this EXAM/SERIES/host
# MGR           = JobManager instance
# PFILE_N       = pfile #
# MOD_DIR       = Where these scripts live
# SERIES        = SERIES number
# SHORT_DATE    = 'YYYY_MM_DD' formatted string of today's date
# TIME_STAMP    = Launch time
# WORK_DIR      = log / work directory  (also the current directory)
#

# Change to the base path you would like to use on the reconstruction server.
# Should line up with one of the watched directories by recwatch
jobsDir = '/incoming/RECONNAME'

# Change KEY to the name of the token file recwatch is expecting
tokenName = 'KEY'

# The sendFiles variable is a dictionary; the keys are the local **absolute**
# paths to files for sending, and the values are created with remote_file():
#
#   remote_file(name, copy=False, delete=False)
#     name:     relative name in remote work directory (string)
#     copy:     copy the local file into logging directory (boolean)
#     delete:   delete local after successful completion. NOTE: Deletes only
#               the copy if copy=True; otherwise deletes the source. (boolean)
#
# For example, this:
#
#     sendFiles['/tmp/info-file'] = remote_file('info', delete=True)
#
# will copy '/tmp/info-file' into the remote work directory as 'info' and
# delete the local (/tmp/info-file) on successful completion.
#
# An advanced usage allows you to stream the contents of an already opened file
# descriptor (passed as a string numeric, like '3') to the remote file name.
# This can be used to run a subprocess with the stdout rerouted to a file in
# the remote work directory. For example:
#
#    import os
#    import subprocess
#
#    (r, w) = pipe()
#    proc = subprocess.Popen(['rsh', 'server', 'cat', fname],
#                            stdout=os.fdopen(w, 'wb', 0),
#                            stdin=open('/dev/null', 'rb'),
#                            stderr=open('fetchlog.err', 'w'),
#                            universal_newlines=False)
#    sendFiles['{0}'.format(r)] = remote_file(fname.split('/')[-1])
#
# will execute (via rsh) 'cat' on 'server' of the path fname, with the output
# placed into the file-part of fname in the remote destination directory
# without staging on the local filesystem. Note in this usage BOTH _copy_ and
# _delete_ args, if provided, must be false.
#
# This line copies the p-file from the current EXAM (set in PFILE_N) as
# P_FILE_<EXAM>S<SERIES>_<YYYY_MM_DD>.7 in the destination job directory.
#
# Modify and add others as needed.

sendFiles['/usr/g/mrraw/P%05d.7' % PFILE_N] = \
    remote_file('P_FILE_%dS%d_%s.7' % (EXAM, SERIES, SHORT_DATE))

# Additional destinations for pushing img and mip directories (if retrieved)
# can be added by assigning one or more DicomDests to pushDests:
#
#    DicomDest constructor: DicomDest(aet, ip, port=4006)
#
# pushDests = [DicomDest('archive', '10.0.0.10', 4242),
#              DicomDest('pacs',    '10.0.0.11')] # Uses default port=4006
