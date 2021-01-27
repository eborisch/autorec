# vim:set expandtab ts=2 sw=2:
#
# The <RECON_NAME>/conf.py external script is responsible for setting up the
# reconstruction.

# Variables that need to be assigned in the <RECON_NAME>/base.py file: ########
# NOTE: Only these variables will be retained from this script.  #############
#
# jobsDir    = path to directory this job will be placed into
# tokenName  = name of the file created in jobsDir to kickoff recon
# sendFiles  = Dictionary of files to send.
#
#
# Some useful variables defined on entry:
#
# EXAM        = exam #
# EXAM_DIR    = String name of directory for this exam/SERIES/host
# MGR         = JobManager instance
# PFILE_N     = pfile #
# MOD_DIR     = Where these scripts live
# SERIES      = series number
# SHORT_DATE  = 'YEAR_MO_DAY' formatted string of today's date
# TIME_STAMP  = Launch time
# WORK_DIR    = log / work directory  (also the current directory)

import os

print("********* Entering conf.py *************")
print("# Objects present in conf.py:")
for x in sorted(locals().keys()):
  print("# {0:20} : {1}".format(x, locals()[x]))
print("")

print("# Environment in conf.py:")
for x in sorted(os.environ.keys()):
  print("# {0:20} : {1}".format(x, os.environ[x]))
print("")

# Change RECONNAME to the directory you would like to use
jobsDir = '/incoming/testing'

# Change KEY to the name of the token file the watcher is expecting
tokenName = None

# The sendFiles dictionary keys are the local (absolute) paths to files 
# for sending, and the values are a tuple of:
# (relative remote name, copy to log dir (bool), delete after recon (bool))
#
cpth = os.path.join(MOD_DIR, 'connectionTest')

settle_file(os.path.join(cpth,'conf.py'))

sendFiles = {}
for x in ('conf.py', 'pre.py', 'post.py', 'raw', 'test_file'):
  _pth = os.path.join(cpth, x)
  settle_file(_pth)
  sendFiles[_pth] = (x, False, False)

getMip = False
getImg = False
print("********* Exiting  conf.py *************")
