#
#  QIRC Python Qt5 Class
#  Copyright (C) 2019  Daniel Hetrick
#               _   _       _                         
#              | | (_)     | |                        
#   _ __  _   _| |_ _  ___ | |__                      
#  | '_ \| | | | __| |/ _ \| '_ \                     
#  | | | | |_| | |_| | (_) | |_) |                    
#  |_| |_|\__,_|\__| |\___/|_.__/ _                   
#  | |     | |    _/ |           | |                  
#  | | __ _| |__ |__/_  _ __ __ _| |_ ___  _ __ _   _ 
#  | |/ _` | '_ \ / _ \| '__/ _` | __/ _ \| '__| | | |
#  | | (_| | |_) | (_) | | | (_| | || (_) | |  | |_| |
#  |_|\__,_|_.__/ \___/|_|  \__,_|\__\___/|_|   \__, |
#                                                __/ |
#                                               |___/ 
#  https://github.com/nutjob-laboratories
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import time
import sys
import socket
from collections import defaultdict

SSL_AVAILABLE = True
try:
	import ssl
except ImportError:
	SSL_AVAILABLE = False

from PyQt5.QtCore import *

QIRC_VERSION = "0.0132"

class QIRC(QThread):

	ping = pyqtSignal(dict)
	connected = pyqtSignal(dict)
	registered = pyqtSignal(dict)
	nick_collision = pyqtSignal(dict)
	message = pyqtSignal(dict)
	public = pyqtSignal(dict)
	private = pyqtSignal(dict)
	action = pyqtSignal(dict)
	tick = pyqtSignal(int)
	user_list = pyqtSignal(dict)
	user_part = pyqtSignal(dict)
	user_join = pyqtSignal(dict)
	user_quit = pyqtSignal(dict)
	nick_change = pyqtSignal(dict)
	invite = pyqtSignal(dict)
	oper = pyqtSignal(dict)
	error = pyqtSignal(dict)
	server_motd = pyqtSignal(str)
	server_hostname = pyqtSignal(str)

	def __init__(self,**kwargs):
		super(QIRC, self).__init__(None)

		self.server = None
		self.port = 0
		self.nickname = "qircclient"
		self.username = "qircclient"
		self.realname = "qircclient"
		self.alternate = "qirc_client"
		self.password = None
		self.encoding = "utf-8"
		self.flood_protection = True
		self.flood_protection_send_rate = 1.5

		self.ssl = False
		self._ssl_verify_hostname = False
		self._ssl_verify_cert = False

		self.uptime = 0
		self.socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)

		self._last_message_time = 0
		self._flood_timer_resolution = 0.10
		self._message_queue = []
		self._flood_timer = 0
		self._threadactive = True

		self._users = defaultdict(list)

		self.motd = []
		self.hostname = "Unknown"
		self.software = "Unknown"

		self.configure(**kwargs)

	def run(self):

		if self.ssl:
			# Creater SSL/TLS context
			self._ssl_context = ssl.create_default_context()

			# Set whether to verify hostname or not
			if self._ssl_verify_hostname:
				self._ssl_context.check_hostname = True
			else:
				self._ssl_context.check_hostname = False

			# Set whether to verify certificate or not
			if self._ssl_verify_cert:
				self._ssl_context.verify_mode = ssl.CERT_REQUIRED
			else:
				self._ssl_context.verify_mode = ssl.CERT_NONE

			# Wrap the socket with the SSL/TLS context
			if ssl.HAS_SNI:
				self.socket = self._ssl_context.wrap_socket(self.socket,server_side=False,server_hostname=self.server)
			else:
				self.socket = self._ssl_context.wrap_socket(self.socket,server_side=False)

		self.socket.connect((self.server,self.port))

		self.uptimeTimer = Timer()
		self.uptimeTimer.beat.connect(self._heartbeat)
		self.uptimeTimer.start()

		self.floodTimer = Timer(self._flood_timer_resolution)
		self.floodTimer.beat.connect(self._floodbeat)
		self.floodTimer.start()

		self.connected.emit( { "client": self, "server": self.server, "port": self.port }  )

		# Get the server to send nicks/hostmasks and all status symbols
		self._send("PROTOCTL UHNAMES NAMESX")

		# Send server password, if necessary
		if self.password:
			self._send(f"PASS {self.password}")

		# Send user information
		self._send(f"NICK {self.nickname}")
		self._send(f"USER {self.username} 0 0 :{self.realname}")

		self._buffer = ""
		while self._threadactive:

			try:
				# Get incoming server data
				line = self.socket.recv(4096)

				# Decode incoming server data
				try:
					# Attempt to decode with the selected encoding
					line2 = line.decode(self.encoding)
				except UnicodeDecodeError:
					try:
						# Attempt to decode with "latin1"
						line2 = line.decode('iso-8859-1')
					except UnicodeDecodeError:
						# Finally, if nothing else works, use windows default encoding
						line2 = line.decode("CP1252", 'replace')
				# Add incoming data to the internal buffer
				self._buffer = self._buffer + line2

			except socket.error:
				print("disconnection error")

				# Shutdown the connection
				self.socket.shutdown(socket.SHUT_RDWR)
				self.socket.close()

				self.stop()

			# Step through the buffer and look for newlines
			while True:
				newline = self._buffer.find("\n")

				# Newline not found, so we'll break and wait for more incoming data
				if newline == -1:
					break

				# Grab the incoming line
				line = self._buffer[:newline]

				# Remove the incoming line from the buffer
				self._buffer = self._buffer[newline+1:]

				tokens = line.split()

				# Return server ping
				if tokens[0].lower()=="ping":
					self._send("PONG " + tokens[1])
					data = {
						"client": self,
						"server": self.server,
						"port": self.port
					}
					self.ping.emit(data)
					break

				# Server welcome
				if tokens[1]=="001":
					data = {
						"client": self,
						"server": self.server,
						"port": self.port
					}
					self.registered.emit(data)
					break

				# Nick collision
				if tokens[1]=="433":
					oldnick = self.nickname
					if self.nickname!=self.alternate:
						self.nickname = self.alternate
						self._send(f"NICK {self.nickname}")
					else:
						self.nickname = self.nickname + "_"
						self._send(f"NICK {self.nickname}")
					data = {
						"client": self,
						"old": oldnick,
						"new": self.nickname
					}
					self.nick_collision.emit(data)
					break

				# Chat message
				if tokens[1].lower()=="privmsg":
					userhost = tokens.pop(0)
					userhost = userhost[1:]
					tokens.pop(0)
					target = tokens.pop(0)
					message = ' '.join(tokens)
					message = message[1:]
					
					p = userhost.split('!')
					if len(p)==2:
						nickname = p[0]
						host = p[1]
					else:
						nickname = p
						host = None

					msgdata = {
						"client": self,
						"nickname": nickname,
						"host": host,
						"target": target,
						"message": message
					}

					self.message.emit(msgdata)

					# CTCP action
					if "\x01ACTION" in message:
						message = message.replace("\x01ACTION",'')
						message = message[:-1]
						message = message.strip()
						msgdata["message"] = message
						self.action.emit(msgdata)
						# Exit so this doesn't trigger another message event
						break

					# Public/private chat
					if target.lower()==self.nickname.lower():
						# private message
						self.private.emit(msgdata)
					else:
						# public message
						self.public.emit(msgdata)
					break

				# User list end
				if tokens[1]=="366":
					channel = tokens[3]

					data = {
						"client": self,
						"channel": channel,
						"users": self._users[channel]
					}

					self.user_list.emit(data)
					self._users[channel] = []
					break

				# Incoming user list
				if tokens[1]=="353":
					data = line.split("=")

					parsed = data[1].split(':')
					channel = parsed[0].strip()
					users = parsed[1].split()

					if channel in self._users:
						self._users[channel] = self._users[channel] + users
						# Clean out duplicates
						self._users[channel] = list(set(self._users[channel]))
					else:
						self._users[channel] = users

					break

				# PART
				if tokens[1].lower()=="part":
					hasreason = True
					if len(tokens)==3: hasreason = False

					user = tokens.pop(0)
					user = user[1:]

					parsed = user.split("!")
					nickname = parsed[0]
					host = parsed[1]

					tokens.pop(0)	# remove message type

					channel = tokens.pop(0)

					if hasreason:
						reason = " ".join(tokens)
						reason = reason[1:]
					else:
						reason = ""

					data = {
						"client": self,
						"nickname": nickname,
						"host": host,
						"channel": channel,
						"reason": reason
					}
					self.user_part.emit(data)
					break

				# JOIN
				if tokens[1].lower()=="join":
					user = tokens[0]
					user = user[1:]
					channel = tokens[2]
					channel = channel[1:]

					p = user.split("!")
					nickname = p[0]
					host = p[1]

					data = {
						"client": self,
						"nickname": nickname,
						"host": host,
						"channel": channel
					}
					self.user_join.emit(data)
					break

				# QUIT
				if tokens[1].lower()=="quit":
					user = tokens.pop(0)
					user = user[1:]

					parsed = user.split("!")
					nickname = parsed[0]
					host = parsed[1]

					tokens.pop(0)	# remove message type

					if len(tokens)>0:
						reason = " ".join(tokens)
						reason = reason[1:]
					else:
						reason = ""

					data = {
						"client": self,
						"nickname": nickname,
						"host": host,
						"reason": reason
					}
					self.user_quit.emit(data)
					break

				# NICK
				if tokens[1].lower()=="nick":
					user = tokens.pop(0)
					user = user[1:]

					parsed = user.split("!")
					nickname = parsed[0]
					host = parsed[1]

					tokens.pop(0)	# remove msg type

					newnick = tokens.pop(0)
					newnick = newnick[1:]

					data = {
						"client": self,
						"nickname": nickname,
						"host": host,
						"new": newnick
					}
					self.nick_change.emit(data)
					break

				# INVITE
				if tokens[1].lower()=="invite":
					user = tokens.pop(0)
					user = user[1:]

					parsed = user.split("!")
					nickname = parsed[0]
					host = parsed[1]

					tokens.pop(0)	# remove message type
					tokens.pop(0)	# remove nick

					channel = tokens.pop(0)
					channel = channel[1:]

					data = {
						"client": self,
						"nickname": nickname,
						"host": host,
						"channel": channel
					}
					self.invite.emit(data)
					break

				# OPER
				if tokens[1]=="381":
					data = {
						"client": self,
						"server": self.server,
						"port": self.port
					}
					self.oper.emit(data)
					break

				# MOTD begins
				if tokens[1]=="375":
					self.motd = []
					break

				# MOTD content
				if tokens[1]=="372":
					tokens.pop(0)	# remove server name
					tokens.pop(0)	# remove message type
					tokens.pop(0)	# remove nickname
					data = " ".join(tokens)
					data = data[3:]
					data = data.strip()
					self.motd.append(data)
					break

				# MOTD ends
				if tokens[1]=="376":
					motd = "\n".join(self.motd)
					motd = motd.strip()
					self.server_motd.emit(motd)
					break

				# 004
				if tokens[1]=="004":
					self.hostname = tokens[3]
					self.software = tokens[4]
					self.server_hostname.emit(self.hostname)
					break

				# Error management
				if handle_errors(self,line): break

				#print("<- "+line)


	def stop(self):
		self.uptimeTimer.stop()
		self.floodTimer.stop()
		self._threadactive = False
		self.wait()

	def send(self,data):
		self._qsend(data)

	def privmsg(self,target,message):
		self._qsend("PRIVMSG "+target+" "+message)

	def join(self,channel,key=None):
		if key==None:
			self._qsend("JOIN "+channel)
		else:
			self._qsend("JOIN "+channel+" "+key)

	def part(self,channel,message=None):
		if message==None:
			self._qsend("PART "+channel)
		else:
			self._qsend("PART "+channel+" "+message)

	def quit(self,reason=None):
		if reason==None:
			self._qsend("QUIT")
		else:
			self._qsend("QUIT "+reason)

		self.socket.shutdown(socket.SHUT_RDWR)
		self.socket.close()
		self.stop()

	def _heartbeat(self):
		self.uptime = self.uptime + 1
		self.tick.emit(self.uptime)

	def _send_queue(self):
		if len(self._message_queue)>0:
			msg = self._message_queue.pop(0)
			self._send(msg)

	def _qsend(self,msg):
		if self.flood_protection:
			if (self._last_message_time + self.flood_protection_send_rate)<=self._flood_timer:
				self._send(msg)
			else:
				self._message_queue.append(msg)
		else:
			self._send(msg)

	def _floodbeat(self):
		self._flood_timer = self._flood_timer + self._flood_timer_resolution
		if self.flood_protection:
			if self._last_message_time==0:
				# send msg from queue
				self._send_queue()
			elif (self._last_message_time + self.flood_protection_send_rate)<=self._flood_timer:
				# send msg from queue
				self._send_queue()

	def _send(self,data):

		self._last_message_time = self._flood_timer

		sender = getattr(self.socket, 'write', self.socket.send)
		try:
			sender(bytes(data + "\r\n", self.encoding))
		except socket.error:
			print("send error")

			# Shutdown the connection and exit
			self.socket.shutdown(socket.SHUT_RDWR)
			self.socket.close()

			self.stop()

	def configure(self,**kwargs):

		for key, value in kwargs.items():

			if key=="verify_hostname":
				self._ssl_verify_hostname = value

			if key=="verify_certificate":
				self._ssl_verify_cert = value

			if key=="ssl":
				self.ssl = value
				if self.ssl:
					if SSL_AVAILABLE==False:
						raise RuntimeError('SSL/TLS is not available. Please install pyOpenSSL.')

			if key=="flood_protection":
				self.flood_protection = value

			if key=="flood_protection_send_rate":
				self.flood_protection_send_rate = value

			if key=="encoding":
				self.encoding = value

			if key=="password":
				self.password = value

			if key=="alternate":
				self.alternate = value

			if key=="nickname":
				self.nickname = value

			if key=="username":
				self.username = value

			if key=="realname":
				self.realname = value

			if key=="parent":
				self.parent = value

			if key=="nickname":
				self.nickname = value

			if key=="server":
				self.server = value

			if key=="port":
				self.port = value

class Timer(QThread):

	beat = pyqtSignal()

	def __init__(self,speed=1,parent=None):
		super(Timer, self).__init__(parent)
		self._threadactive = True
		self.speed = speed

	def run(self):
		while self._threadactive:
			time.sleep(self.speed)
			self.beat.emit()

	def stop(self):
		self._threadactive = False
		self.wait()

def emit_double_target_error(eobj,code,tokens):
	tokens.pop(0)	# remove server
	tokens.pop(0)	# reove message type
	tokens.pop(0)	# remove nick

	target = tokens.pop(0)
	target2 = tokens.pop(0)
	reason = ' '.join(tokens)
	reason = reason[1:]

	data = {
		"client": eobj,
		"code": int(code),
		"target": [target,target2],
		"reason": reason
	}

	eobj.error.emit(data)

def emit_target_error(eobj,code,tokens):
	tokens.pop(0)	# remove server
	tokens.pop(0)	# reove message type
	tokens.pop(0)	# remove nick

	target = tokens.pop(0)
	reason = ' '.join(tokens)
	reason = reason[1:]

	data = {
		"client": eobj,
		"code": int(code),
		"target": [target],
		"reason": reason
	}

	eobj.error.emit(data)

def emit_error(eobj,code,line):
	parsed = line.split(':')
	if len(parsed)>=2:
		reason = parsed[1]
	else:
		reason = "Unknown error"

	data = {
		"client": eobj,
		"code": int(code),
		"target": [],
		"reason": reason
	}

	eobj.error.emit(data)

def handle_errors(eobj,line):

	tokens = line.split()

	if tokens[1]=="400":
		data = {
			"client": eobj,
			"code": 400,
			"target": [],
			"reason": "Unknown error"
		}
		eobj.error.emit(data)
		return True

	if tokens[1]=="401":
		emit_target_error(eobj,"401",tokens)
		return True

	if tokens[1]=="402":
		emit_target_error(eobj,"402",tokens)
		return True

	if tokens[1]=="403":
		emit_target_error(eobj,"403",tokens)
		return True

	if tokens[1]=="404":
		emit_target_error(eobj,"404",tokens)
		return True

	if tokens[1]=="405":
		emit_target_error(eobj,"405",tokens)
		return True

	if tokens[1]=="406":
		emit_target_error(eobj,"406",tokens)
		return True

	if tokens[1]=="407":
		emit_target_error(eobj,"407",tokens)
		return True

	if tokens[1]=="409":
		emit_error(eobj,"409",line)
		return True

	if tokens[1]=="411":
		emit_error(eobj,"411",line)
		return True

	if tokens[1]=="412":
		emit_error(eobj,"412",line)
		return True

	if tokens[1]=="413":
		emit_target_error(eobj,"413",tokens)
		return True

	if tokens[1]=="414":
		emit_target_error(eobj,"414",tokens)
		return True

	if tokens[1]=="415":
		emit_target_error(eobj,"415",tokens)
		return True

	if tokens[1]=="421":
		emit_target_error(eobj,"421",tokens)
		return True

	if tokens[1]=="422":
		emit_error(eobj,"422",line)
		return True

	if tokens[1]=="423":
		emit_target_error(eobj,"423",tokens)
		return True

	if tokens[1]=="424":
		emit_error(eobj,"424",line)
		return True

	if tokens[1]=="431":
		emit_error(eobj,"431",line)
		return True

	if tokens[1]=="432":
		emit_target_error(eobj,"432",tokens)
		return True

	if tokens[1]=="436":
		emit_target_error(eobj,"436",tokens)
		return True

	if tokens[1]=="441":
		emit_double_target_error(eobj,"441",tokens)
		return True

	if tokens[1]=="442":
		emit_target_error(eobj,"442",tokens)
		return True

	if tokens[1]=="444":
		emit_target_error(eobj,"444",tokens)
		return True

	if tokens[1]=="445":
		emit_error(eobj,"445",line)
		return True

	if tokens[1]=="446":
		emit_error(eobj,"446",line)
		return True

	if tokens[1]=="451":
		emit_error(eobj,"451",line)
		return True

	if tokens[1]=="461":
		emit_target_error(eobj,"461",tokens)
		return True

	if tokens[1]=="462":
		emit_error(eobj,"462",line)
		return True

	if tokens[1]=="463":
		emit_error(eobj,"463",line)
		return True

	if tokens[1]=="464":
		emit_error(eobj,"464",line)
		return True

	if tokens[1]=="465":
		emit_error(eobj,"465",line)
		return True

	if tokens[1]=="467":
		emit_target_error(eobj,"467",tokens)
		return True

	if tokens[1]=="471":
		emit_target_error(eobj,"471",tokens)
		return True

	if tokens[1]=="472":
		emit_target_error(eobj,"472",tokens)
		return True

	if tokens[1]=="473":
		emit_target_error(eobj,"473",tokens)
		return True

	if tokens[1]=="474":
		emit_target_error(eobj,"474",tokens)
		return True

	if tokens[1]=="475":
		emit_target_error(eobj,"475",tokens)
		return True

	if tokens[1]=="476":
		emit_target_error(eobj,"476",tokens)
		return True

	if tokens[1]=="478":
		emit_double_target_error(eobj,"478",tokens)
		return True

	if tokens[1]=="481":
		emit_error(eobj,"481",line)
		return True

	if tokens[1]=="482":
		emit_target_error(eobj,"482",tokens)
		return True

	if tokens[1]=="483":
		emit_error(eobj,"483",line)
		return True

	if tokens[1]=="485":
		emit_error(eobj,"481",line)
		return True

	if tokens[1]=="491":
		emit_error(eobj,"491",line)
		return True

	if tokens[1]=="501":
		emit_error(eobj,"501",line)
		return True

	if tokens[1]=="502":
		emit_error(eobj,"502",line)
		return True

	return False
