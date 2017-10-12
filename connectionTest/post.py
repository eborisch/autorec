# vim: set expandtab ts=2 sw=2:
# The post.py script is called after reconstruction completes, but before
# importing or cleanup is performed.
#
# This script is run in the calling environment; use with care!

print("********* Entering post.py *************")

print("# Objects present at post.py:")
for x in sorted(locals().keys()):
  print("# {0:20} : {1}".format(x, locals()[x]))
print("")

#sys.exit(0)

print("********* Entering post.py *************")
