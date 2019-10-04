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

QIRC_VERSION = "0.01"

class QIRC(QThread):

	ping = pyqtSignal()
	connected = pyqtSignal(dict)
	registered = pyqtSignal(dict)
	nick_collision = pyqtSignal(dict)
	message = pyqtSignal(dict)
	public = pyqtSignal(dict)
	private = pyqtSignal(dict)
	action = pyqtSignal(dict)
	tick = pyqtSignal(int)

	userlist = pyqtSignal(dict)

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
					self.ping.emit()
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

					self.userlist.emit(data)
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