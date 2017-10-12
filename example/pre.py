#!/usr/bin/env python
# vim:set ts=2 sw=2 expandtab:
#
# the pre.py script permits the reconstruction to specify the server and user
# name used for connection on a per-configuration basis. This is achieved by
# setting the parameters in a dictionary named jobArgs.
#
# Optional output variable : jobArgs
#
# Only being changed need to be specified in jobArgs; the defaults will be
# used for any missing values
#
# !! Note that the 'machines' entry must be a tuple. To use only one address,
# set the value to   ('ADDRESS',)   ... the tailing ',' makes it into a tuple
#
# jobArgs = { 'machines' : ('10.0.9.10', ),
#             'user' : 'reconuser'}


