
import sys

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

from qirc import QIRC

NICKNAME = "qirc_client"
CHANNEL = "#qirc"

def writeChat(nickname,message):
	INTERFACE.channelChatDisplay.append("<b>"+nickname+"</b>: "+message)
	INTERFACE.channelChatDisplay.moveCursor(QTextCursor.End)

class Interface(QMainWindow):

	def writeUserlist(self,userlist):
		self.channelUserDisplay.clear()

		for user in userlist:
			ui = QListWidgetItem()
			ui.setText(user.nickname)
			self.channelUserDisplay.addItem(ui)

	def writeText(self,data):
		self.channelChatDisplay.append("<i>"+data+"</i>")
		self.channelChatDisplay.moveCursor(QTextCursor.End)

	def writeChat(self,nickname,text):
		self.channelChatDisplay.append("<b>"+nickname+"</b>: "+text)
		self.channelChatDisplay.moveCursor(QTextCursor.End)

	def handleUserInput(self):
		user_input = self.userTextInput.text()
		self.userTextInput.setText('')

		tokens = user_input.split(' ')

		if len(tokens)>=2:
			if tokens[0].lower()=="/join":
				if len(tokens)==2:
					channel = tokens[1]
					self.ircClient.part(CHANNEL)
					self.ircClient.join(channel)
					return
				elif len(tokens)>2:
					tokens.pop(0)
					channel = tokens.pop(0)
					key = ' '.join(tokens)
					self.ircClient.part(CHANNEL)
					self.ircClient.join(channel,key)
					return

		self.ircClient.privmsg(CHANNEL,user_input)
		self.writeChat(NICKNAME,user_input)

	def closeEvent(self, event):
		self.close()
		sys.exit()

	def __init__(self,parent=None):
		super(Interface, self).__init__(parent)

		self.channel = ""

		self.setWindowTitle("QIRC Example")

		self.channelChatDisplay = QTextBrowser(self)
		self.channelChatDisplay.setObjectName("channelChatDisplay")
		self.channelChatDisplay.setFocusPolicy(Qt.NoFocus)

		self.channelUserDisplay = QListWidget(self)
		self.channelUserDisplay.setObjectName("channelUserDisplay")
		self.channelUserDisplay.installEventFilter(self)
		self.channelUserDisplay.setFocusPolicy(Qt.NoFocus)

		self.userTextInput = QLineEdit(self)
		self.userTextInput.setObjectName("userTextInput")
		self.userTextInput.returnPressed.connect(self.handleUserInput)

		self.horizontalSplitter = QSplitter(Qt.Horizontal)
		self.horizontalSplitter.addWidget(self.channelChatDisplay)
		self.horizontalSplitter.addWidget(self.channelUserDisplay)
		self.horizontalSplitter.setSizes([475,125])

		self.verticalSplitter = QSplitter(Qt.Vertical)
		self.verticalSplitter.addWidget(self.horizontalSplitter)

		self.verticalSplitter.addWidget(self.userTextInput)
		self.verticalSplitter.setSizes([575,25])

		finalLayout = QVBoxLayout()
		finalLayout.addWidget(self.verticalSplitter)

		x = QWidget()
		x.setLayout(finalLayout)
		self.setCentralWidget(x)

		self.userTextInput.setFocus()

		self.ircClient = QIRC(server="localhost",port=6667,nickname=NICKNAME)

		self.ircClient.server_connect.connect(self.gotConnected)
		self.ircClient.server_register.connect(self.gotRegistered)
		self.ircClient.nick_collision.connect(self.gotCollision)
		self.ircClient.message_public.connect(self.gotPublic)
		self.ircClient.message_private.connect(self.gotPrivate)
		self.ircClient.message_action.connect(self.gotAction)
		self.ircClient.user_list.connect(self.gotUserlist)
		self.ircClient.server_error.connect(self.gotError)

		self.ircClient.tick.connect(self.tick)

		self.ircClient.user_join.connect(self.gotJoin)

		self.ircClient.start()

	def gotJoin(self,joindata):
		if joindata["nickname"].lower()==NICKNAME.lower():
			global CHANNEL
			CHANNEL = joindata["channel"]
			self.writeText("Joined "+CHANNEL)

	def tick(self,uptime):
		self.channelChatDisplay.update()
		self.channelUserDisplay.update()

	def gotError(self,errordata):
		print(errordata)

	def gotUserlist(self,userdata):
		self.channelUserDisplay.clear()
		ops = []
		voiced = []
		normal = []
		for user in userdata["users"]:
			p = user.split('!')
			if len(p)==2:
				nick = p[0]
			else:
				nick = user

			if '@' in nick:
				ops.append(nick)
			elif '+' in nick:
				voiced.append(nick)
			else:
				normal.append(nick)

		sortedusers = ops + voiced + normal
		for user in sortedusers:
			ui = QListWidgetItem()
			ui.setText(user)
			self.channelUserDisplay.addItem(ui)

		self.channelUserDisplay.repaint()


	def gotAction(self,msgdata):
		self.writeText("<b>"+msgdata["nickname"]+"</b> "+msgdata["message"])
		self.ircClient.join("#flarp")

	def gotPublic(self,msgdata):
		self.writeChat(msgdata["nickname"],msgdata["message"])

	def gotPrivate(self,msgdata):
		self.writeChat("PRIVATE "+msgdata["nickname"],msgdata["message"])

	def gotCollision(self,msgdata):
		self.writeText("Your nickname is now "+msgdata["new"])

	def gotRegistered(self,msgdata):
		self.writeText("Registered with "+msgdata["server"]+":"+str(msgdata["port"])+"!")
		self.writeText("Joining "+CHANNEL)
		self.ircClient.join(CHANNEL)

	def gotConnected(self,msgdata):
		self.writeText("Connected to "+msgdata["server"]+":"+str(msgdata["port"])+"!")

# app = QApplication(sys.argv)
app = QApplication([])
app.setFont(QFont("Consolas",10))
INTERFACE = Interface()

if __name__ == '__main__':

	INTERFACE.show()

	sys.exit(app.exec())