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
# OPTIONAL:
#    mipCopy = Additional directory to copy resulting MIP DICOMs into
#    imgCopy = Additional directory to copy resulting image DICOMs into
#    getMip = Retrieve and import "mip" directory (defaults to true)
#    getImg = Retrieve and import "img" directory (defaults to true)
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

# The sendFiles variable is a dictionary; the keys are the local (absolute)
# paths to files for sending, and the values are a tuple of:
#  (relative remote name, copy to log dir (bool), delete after recon (bool))
#
# See also:
#  http://docs.python.org/tutorial/datastructures.html#dictionaries
#  http://docs.python.org/tutorial/datastructures.html#tuples-and-sequences
#
# This line copies the p-file from the current EXAM (set in PFILE_N) as
# P_FILE_<EXAM>S<SERIES>_<YYYY_MM_DD>.7 in the destination job directory.
#
# Modify and add others as needed.

sendFiles = {'/usr/g/mrraw/P%05d.7' % PFILE_N : 
    ('P_FILE_%dS%d_%s.7' % (EXAM, SERIES, SHORT_DATE), False, False)}

# Annotated version of above:
# sendFiles = { # Dictionary start
#  '/usr/g/mrraw/P%05d.7' % PFILE_N : # Dictionary key; local (absolute) path
#  ( # Tuple start; First dictionary entry value
#    'P_FILE_%dS%d_%s.7' % (EXAM, SERIES, SHORT_DATE), # (relative) remote name
#    False, # False = Do not copy to log dir
#    False  # False = No deletion post completion
#  ) # Tuple end
# } # Dictionary end
