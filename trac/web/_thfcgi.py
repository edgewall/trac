# -*- coding: iso-8859-1 -*-
# thfcgi.py - FastCGI communication with thread support
#
# Copyright Peter Åstrand <astrand@lysator.liu.se> 2001
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License. 
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

# TODO:
#
# Compare compare the number of bytes received on FCGI_STDIN with
# CONTENT_LENGTH and abort the update if the two numbers are not equal.
#

import os
import sys
import select
import string
import socket
import errno
import cgi
import thread
from cStringIO import StringIO
import struct
from trac.web.cgi_frontend import TracFieldStorage

# Maximum number of requests that can be handled
FCGI_MAX_REQS = 50
FCGI_MAX_CONNS = 50
FCGI_VERSION_1 = 1
# Can this application multiplex connections?
FCGI_MPXS_CONNS = 0

# Record types
FCGI_BEGIN_REQUEST = 1
FCGI_ABORT_REQUEST = 2
FCGI_END_REQUEST = 3
FCGI_PARAMS = 4
FCGI_STDIN = 5
FCGI_STDOUT = 6
FCGI_STDERR = 7
FCGI_DATA = 8
FCGI_GET_VALUES = 9
FCGI_GET_VALUES_RESULT = 10
FCGI_UNKNOWN_TYPE = 11
FCGI_MAXTYPE = FCGI_UNKNOWN_TYPE

# Types of management records
KNOWN_MANAGEMENT_TYPES = [FCGI_GET_VALUES]

FCGI_NULL_REQUEST_ID = 0

# Masks for flags component of FCGI_BEGIN_REQUEST
FCGI_KEEP_CONN = 1

# Values for role component of FCGI_BEGIN_REQUEST
FCGI_RESPONDER = 1
FCGI_AUTHORIZER = 2
FCGI_FILTER = 3

# Values for protocolStatus component of FCGI_END_REQUEST
FCGI_REQUEST_COMPLETE = 0     # Request completed ok
FCGI_CANT_MPX_CONN = 1        # This app cannot multiplex
FCGI_OVERLOADED = 2           # Too busy
FCGI_UNKNOWN_ROLE = 3         # Role value not known

# Struct format types
FCGI_BeginRequestBody = "!HB5x"
FCGI_Record_header = "!BBHHBx"
FCGI_UnknownTypeBody = "!B7x"
FCGI_EndRequestBody = "!IB3x"

class Record:
    """Class representing FastCGI records"""
    def __init__(self):
        self.version = FCGI_VERSION_1
        self.rec_type = FCGI_UNKNOWN_TYPE
        self.req_id   = FCGI_NULL_REQUEST_ID
        self.content = ""

        # Only in FCGI_BEGIN_REQUEST
        self.role = None
        self.flags = None
        self.keep_conn = 0

        # Only in FCGI_UNKNOWN_TYPE
        self.unknownType = None

        # Only in FCGI_END_REQUEST
        self.appStatus = None
        self.protocolStatus = None

    def read_pair(self, data, pos):
        namelen = struct.unpack("!B", data[pos])[0]
        if namelen & 128:
            # 4-byte name length
            namelen = struct.unpack("!I", data[pos:pos+4])[0] & 0x7fffffff
            pos += 4
        else:
            pos += 1

        valuelen = struct.unpack("!B", data[pos])[0]
        if valuelen & 128:
            # 4-byte value length
            valuelen = struct.unpack("!I", data[pos:pos+4])[0] & 0x7fffffff
            pos += 4
        else:
            pos += 1

        name = data[pos:pos+namelen]
        pos += namelen
        value = data[pos:pos+valuelen]
        pos += valuelen

        return (name, value, pos)

    def write_pair(self, name, value):
        namelen = len(name)
        if namelen < 128:
            data = struct.pack("!B", namelen)
        else:
            # 4-byte name length
            data = struct.pack("!I", namelen | 0x80000000L)

        valuelen = len(value)
        if valuelen < 128:
            data += struct.pack("!B", value)
        else:
            # 4-byte value length
            data += struct.pack("!I", value | 0x80000000L)

        return data + name + value
        
    def readRecord(self, sock):
        data = sock.recv(8)
        if not data:
            # No data recieved. This means EOF. 
            return None
        
        fields = struct.unpack(FCGI_Record_header, data)
        (self.version, self.rec_type, self.req_id,
         contentLength, paddingLength) = fields
        
        self.content = ""
        while len(self.content) < contentLength:
            data = sock.recv(contentLength - len(self.content))
            self.content = self.content + data
        if paddingLength != 0:
            sock.recv(paddingLength)
        
        # Parse the content information
        if self.rec_type == FCGI_BEGIN_REQUEST:
            (self.role, self.flags) = struct.unpack(FCGI_BeginRequestBody,
                                                    self.content)
            self.keep_conn = self.flags & FCGI_KEEP_CONN

        elif self.rec_type == FCGI_UNKNOWN_TYPE:
            self.unknownType = struct.unpack(FCGI_UnknownTypeBody, self.content)

        elif self.rec_type == FCGI_GET_VALUES or self.rec_type == FCGI_PARAMS:
            self.values = {}
            pos = 0
            while pos < len(self.content):
                name, value, pos = self.read_pair(self.content, pos)
                self.values[name] = value
        elif self.rec_type == FCGI_END_REQUEST:
            (self.appStatus,
             self.protocolStatus) = struct.unpack(FCGI_EndRequestBody,
                                                  self.content)

        return 1

    def writeRecord(self, sock):
        content = self.content
        if self.rec_type == FCGI_BEGIN_REQUEST:
            content = struct.pack(FCGI_BeginRequestBody, self.role, self.flags)

        elif self.rec_type == FCGI_UNKNOWN_TYPE:
            content = struct.pack(FCGI_UnknownTypeBody, self.unknownType)

        elif self.rec_type == FCGI_GET_VALUES or self.rec_type == FCGI_PARAMS:
            content = ""
            for i in self.values.keys():
                content = content + self.write_pair(i, self.values[i])

        elif self.rec_type == FCGI_END_REQUEST:
            content = struct.pack(FCGI_EndRequestBody, self.appStatus,
                                  self.protocolStatus)

        # Align to 8-byte boundary
        clen = len(content)
        padlen = ((clen + 7) & 0xfff8) - clen
        
        hdr = struct.pack(FCGI_Record_header, self.version, self.rec_type,
                          self.req_id, clen, padlen)
        
        try:
            sock.sendall(hdr + content + padlen*"\x00")
        except socket.error:
            # Write error, probably broken pipe. Exit thread. 
            thread.exit()


class Request:
    """A request, corresponding to an accept():ed connection and
    a FCGI request. 
    """
    def __init__(self, conn, req_handler):
        self.conn = conn
        self.req_handler = req_handler
        
        self.keep_conn = 0
        self.req_id = None

        # Input
        self.env = {}
        self.env_complete = 0
        self.stdin = StringIO()
        self.stdin_complete = 0
        self.data = StringIO()
        self.data_complete = 0

        # Output
        self.out = StringIO()
        self.err = StringIO()

        self.have_finished = 0

    def run(self):
        while 1:
            if self.conn.fileno() < 1:
                # Connection lost
                return

            select.select([self.conn], [], [])
            rec = Record()
            if rec.readRecord(self.conn):
                if self._handle_record(rec):
                    return
            else:
                # EOF, connection closed. Break loop, end thread. 
                return
                
    def getFieldStorage(self):
        self.stdin.reset()
        return TracFieldStorage(fp=self.stdin, environ=self.env,
                                keep_blank_values=1)

    def _flush(self, stream):
        stream.reset()

        rec = Record()
        rec.rec_type = FCGI_STDOUT
        rec.req_id = self.req_id
        data = stream.read()

        if not data:
            # Writing zero bytes would mean stream termination
            return
        
        while data:
            chunk, data = self.getNextChunk(data)
            rec.content = chunk
            rec.writeRecord(self.conn)
        # Truncate
        stream.reset()
        stream.truncate()

    def flush_out(self):
        self._flush(self.out)

    def flush_err(self):
        self._flush(self.err)

    def finish(self, status=0):
        if self.have_finished:
            return

        self.have_finished = 1

        # stderr
        self.err.reset()
        rec = Record()
        rec.rec_type = FCGI_STDERR
        rec.req_id = self.req_id
        data = self.err.read()
        while data:
            chunk, data = self.getNextChunk(data)
            rec.content = chunk
            rec.writeRecord(self.conn)
        rec.content = ""
        rec.writeRecord(self.conn)      # Terminate stream

        # stdout
        self.out.reset()
        rec = Record()
        rec.rec_type = FCGI_STDOUT
        rec.req_id = self.req_id
        data = self.out.read()
        while data:
            chunk, data = self.getNextChunk(data)
            rec.content = chunk
            rec.writeRecord(self.conn)
        rec.content = ""
        rec.writeRecord(self.conn)      # Terminate stream

        # end request
        rec = Record()
        rec.rec_type = FCGI_END_REQUEST
        rec.req_id = self.req_id
        rec.appStatus = status
        rec.protocolStatus = FCGI_REQUEST_COMPLETE
        rec.writeRecord(self.conn)
        if not self.keep_conn:
            self.conn.close()
            thread.exit()
    
    #
    # Record handlers
    #
    def _handle_record(self, rec):
        """Handle record"""
        if rec.req_id == FCGI_NULL_REQUEST_ID:
            # Management record            
            self._handle_man_record(rec)
        else:
            # Application record
            self._handle_app_record(rec)

    def _handle_man_record(self, rec):
        """Handle management record"""
        rec_type = rec.rec_type
        if rec_type in KNOWN_MANAGEMENT_TYPES:
            self._handle_known_man_types(rec)
        else:
            # It's a management record of an unknown
            # type. Signal the error.
            rec = Record()
            rec.rec_type = FCGI_UNKNOWN_TYPE
            rec.unknownType = rec_type
            rec.writeRecord(self.conn)

    def _handle_known_man_types(self, rec):
        if rec.rec_type == FCGI_GET_VALUES:
            reply_rec = Record()
            reply_rec.rec_type = FCGI_GET_VALUES_RESULT

            params = {'FCGI_MAX_CONNS' : FCGI_MAX_CONNS,
                      'FCGI_MAX_REQS' : FCGI_MAX_REQS,
                      'FCGI_MPXS_CONNS' : FCGI_MPXS_CONNS}

            for name in rec.values.keys():
                if params.has_key(name):
                    # We known this value, include in reply
                    reply_rec.values[name] = params[name]

            rec.writeRecord(self.conn)

    def _handle_app_record(self, rec):
        if rec.rec_type == FCGI_BEGIN_REQUEST:
            # Discrete
            self._handle_begin_request(rec)
            return
        elif rec.req_id != self.req_id:
            #print >> sys.stderr, "Recieved unknown request ID", rec.req_id
            # Ignore requests that aren't active
            return
        if rec.rec_type == FCGI_ABORT_REQUEST:
            # Discrete
            rec.rec_type = FCGI_END_REQUEST
            rec.protocolStatus = FCGI_REQUEST_COMPLETE
            rec.appStatus = 0
            rec.writeRecord(self.conn)
            return
        elif rec.rec_type == FCGI_PARAMS:
            # Stream
            self._handle_params(rec)
        elif rec.rec_type == FCGI_STDIN:
            # Stream
            self._handle_stdin(rec)
        elif rec.rec_type == FCGI_DATA:
            # Stream
            self._handle_data(rec)
        else:
            # Should never happen. 
            #print >> sys.stderr, "Recieved unknown FCGI record type", rec.rec_type
            pass

        if self.env_complete and self.stdin_complete:
            # Call application request handler. 
            # The arguments sent to the request handler is:
            # self: us. 
            # req: The request.
            # env: The request environment
            # form: FieldStorage.
            try:
                self.req_handler(self, self.env, self.getFieldStorage())
                self.finish()
            except SystemExit:
                return True

    def _handle_begin_request(self, rec):
        if rec.role != FCGI_RESPONDER:
            # Unknown role, signal error.
            rec.rec_type = FCGI_END_REQUEST
            rec.appStatus = 0
            rec.protocolStatus = FCGI_UNKNOWN_ROLE
            rec.writeRecord(self.conn)
            return

        self.req_id = rec.req_id
        self.keep_conn = rec.keep_conn
        
    def _handle_params(self, rec):
        if self.env_complete:
            # Should not happen
            #print >> sys.stderr, "Recieved FCGI_PARAMS more than once"
            return
        
        if not rec.content:
            self.env_complete = 1

        # Add all vars to our environment
        self.env.update(rec.values)

    def _handle_stdin(self, rec):
        if self.stdin_complete:
            # Should not happen
            #print >> sys.stderr, "Recieved FCGI_STDIN more than once"
            return
        
        if not rec.content:
            self.stdin_complete = 1

        self.stdin.write(rec.content)

    def _handle_data(self, rec):
        if self.data_complete:
            # Should not happen
            #print >> sys.stderr, "Recieved FCGI_DATA more than once"
            return

        if not rec.content:
            self.data_complete = 1
        
        self.data.write(rec.content)

    def getNextChunk(self, data):
        chunk = data[:8192]
        data = data[8192:]
        return chunk, data


class THFCGI:
    def __init__(self, req_handler, fd=sys.stdin):
        self.req_handler = req_handler
        self.fd = fd
        self._make_socket()

    def run(self):
        """Wait & serve. Calls request handler in new
        thread on every request.
        """
        self.sock.listen(5)
        
        while 1:
            (conn, addr) = self.sock.accept()
            thread.start_new_thread(self.accept_handler, (conn, addr))

    def accept_handler(self, conn, addr):
        try:
            self._check_good_addrs(addr)
            req = Request(conn, self.req_handler)
            req.run()
        except Exception, e:
            import traceback, sys
            traceback.print_exc(file=sys.stderr)

    def _make_socket(self):
        """Create socket and verify FCGI environment"""
        try:
            s = socket.fromfd(self.fd.fileno(), socket.AF_INET,
                              socket.SOCK_STREAM)
            s.getpeername()
        except socket.error, (err, errmsg):
            if err != errno.ENOTCONN: 
                raise "No FastCGI environment"

        self.sock = s
        
    def _check_good_addrs(self, addr):
        # Apaches mod_fastcgi seems not to use FCGI_WEB_SERVER_ADDRS. 
        if os.environ.has_key('FCGI_WEB_SERVER_ADDRS'):
            good_addrs = string.split(os.environ['FCGI_WEB_SERVER_ADDRS'], ',')
            good_addrs = map(string.strip, good_addrs) # Remove whitespace
        else:
            good_addrs = None
        
        # Check if the connection is from a legal address
        if good_addrs != None and addr not in good_addrs:
            raise "Connection from invalid server!"
        
