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
DICOM-related classes / functions
"""

class DicomDest(object):
    """
    Class to describe destinations for push_dir calls.
    """
    def __init__(self, aet, ip, port=4006):
        """
        Construct an DicomDest object. Default port is 4006.
        """
        self.aet = aet
        self.ip = ip
        self.port = port

    def __call__(self):
        return self.__dict__

    def __setattr__(self, attr, value):
        """
        Performs checking of attribute names for allowed ones.
        """
        if attr == 'port':
            self.__dict__[attr] = int(value)
        elif attr in ('aet', 'ip'):
            self.__dict__[attr] = value
        else:
            raise AttributeError(attr + ' not allowed')

    def __repr__(self):
        return "DICOM destination: {aet} [{ip}:{port}]".format(**self())
