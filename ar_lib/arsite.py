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
Load site-specific customizations (e.g. DicomDest destinations) go here. Any
helper functions to re-use on conf.py scripts. Rather than modifying this file,
put your customizations into site-*.py next to this one. (* = match any string)
"""

# This will get import *'d, so use _private names for variables you don't want
# to export.

import os.path as _path
from glob import glob as _glob
from socket import gethostname as _gethostname

from .dicom import DicomDest as _DCMDST

# Here to facilitate testing failed DICOM pushes.
FAIL_TEST = _DCMDST('FAIL_TEST', '127.0.0.1', 999)

#############################################################################
# These should be overwritten by a configured site-*.py file; here to provide
# information on what needs to be done. See --------------------------------+
                                                                          # |
GOOD_TEST = "See site.py for information on configuring a working test."  # |
TEST_DIR = "Set to path to .sdcopen files on DEFAULT_RECON_MACHINES."     # |
                                                                          # v
## Copy the following two lines (into your site-*.py) and set values you expect
## to work. The first is for a DICOM reciever, and the second is for a location
## on DEFAULT_RECON_MACHINES that you expect to have *.sdcopen (DICOM) files.

#GOOD_TEST = _DCMDST('<AET>', '<IP>', '<PORT>') # Fill in with YOUR VALUES
#TEST_DIR = "A path to .sdcopen files on DEFAULT_RECON_MACHINES."


#############################################################################
# The remainder of these are configuration variables. You can edit them here
# or (preferred) create a file named site-foo.py (replace foo with your site
# name) next to this file with your definitions. No need to comment them out
# here, just redefine them in site-foo.py.

# AET for local push operation. If 'None', use first component of hostname
LOCAL_AET = None

# IP address for the default "local" push destination
LOCAL_IP = '127.0.0.1'

# TCP Port for the default "local" push destination
LOCAL_PORT = 4006

# Our AE title used when pushing DICOM images.
AE_TITLE = 'AUTOREC'

# The number of minutes to retry pushing to an unreachable DICOM destination
HARD_RETRIES = 15

# The number of retries (unit=5s; 12 = 1m) for "transient" DICOM push errors
SOFT_RETRIES = 12

# The total time allowed for a DICOM push task to finish in minutes
MAX_PUSH_TIME = 20

# Tuple of default IP addresses to connect to (can be over-ridden in pre.py)
# or in site-*.py, below.
# NOTE: THIS MUST BE A TUPLE; NEED TRAILING ',' IF ONLY ONE ITEM.
DEFAULT_RECON_MACHINES = ('127.0.0.1', )

# Username for reconstructing to remote system
USERNAME = 'autorec'

# Set to path to SSH pre-shared private key if it is not 'id_recon' in the same
# directory as the top-level autorec.py script.
KEYFILE = None

# Path to SSH configuration file to use. [Optional]
SSH_CONF = None

# Contact info to record in logs if there is an error.
CONTACT = 'system administrator'

# Directory for retrieving images into (temporarily); Uses an internal default
# if NONE
EXPORT_PATH = None

# This must exist on both sides of connection. If you are bandwidth limited
# (and your output files are compressible) consider upping the compression
# level.
COMPRESS = 'gzip -1'
DECOMPRESS = 'gzip -q -d'

# You can also add site-specific config in site-*.py files next to this one.
for _site_local in \
    sorted(_glob(_path.join(_path.dirname(__file__), 'site-*.py'))):
    with open(_site_local, 'r') as _site_conf:
        exec(compile(_site_conf.read(), _site_local, 'exec'))

# Read <hostname>.py config last; local overrides.
_hostname = _gethostname().split('.')[0].lower()
_local_site = _path.join(_path.dirname(__file__), '{0}.py'.format(_hostname))
if _path.exists(_local_site):
    with open(_local_site, 'r') as _site_conf:
        exec(compile(_site_conf.read(), _local_site, 'exec'))
