#!/usr/bin/env python
# vim:set ts=2 sw=2 expandtab:
#
# the pre.py script permits the reconstruction to specify the server, user
# name, and password used for connection. This is achieved by setting
# the parameters in a dictionary named jobArgs.
#
# Optional output variable : jobArgs
#
# Default dictionary; only those being changed need to be specified.
#
# jobArgs = { 'machines' : ('ip address 1', 'ip address 2'),
#             'user' : 'reconuser',
#             'keyfile' : None } (Which implies id_recon next to autorec.py)

print("********* Entering  pre.py *************")

print("# Objects present at pre.py:")
for x in sorted(locals().keys()):
  print("# {0:20} : {1}".format(x, locals()[x]))
print("")

# To override the DEFAULT_MACHINES_LIST for this reconstruction, for example:
#jobArgs = { 'machines' : ('127.0.0.1',) }  # Note trailing ',' if only one.

print("********* Exiting   pre.py *************")
