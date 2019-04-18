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
Copy this file and rename it to site-*.py (where * is something descriptive
for your location. Uncomment and change values as needed.
"""

# This will get import *'d, so use _private names for variables you don't want
# to export.

# Set values you expect ## to work for testing. The first is for a DICOM
# reciever, and the second is for a location on DEFAULT_RECON_MACHINES that
# you expect to have *.sdcopen (DICOM) files.

#GOOD_TEST = _DCMDST('<AET>', '<IP>', '<PORT>') # Fill in with YOUR VALUES
#TEST_DIR = "A path to .sdcopen files on DEFAULT_RECON_MACHINES."

## AET for local push operation. If 'None', use first component of hostname
#LOCAL_AET = None

## Our AE title used when pushing DICOM images.
#AE_TITLE = 'AUTOREC'

## The number of minutes to retry pushing to an unreachable DICOM destination
#HARD_RETRIES = 15

## The number of retries (unit=5s; 12 = 1m) for "transient" DICOM push errors
#SOFT_RETRIES = 12

## The total time allowed for a DICOM push task to finish in minutes
#MAX_PUSH_TIME = 20

## Tuple of default IP addresses to connect to (can be over-ridden in pre.py)
## or in site-*.py, below.
## NOTE: THIS MUST BE A TUPLE; NEED TRAILING ',' IF ONLY ONE ITEM.
#DEFAULT_RECON_MACHINES = ('127.0.0.1', )

## Username for reconstructing to remote system
#USERNAME = 'autorec'

## Set to path to SSH pre-shared private key if it is not 'id_recon' in the same
## directory as the top-level autorec.py script.
#KEYFILE = None

## Path to SSH configuration file to use. [Optional]
#SSH_CONF = None

## Contact info to record in logs if there is an error.
#CONTACT = 'system administrator'

## Directory for retrieving images into (temporarily); Uses an internal default
## if NONE
#EXPORT_PATH = None
