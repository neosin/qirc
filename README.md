<p align="center">
	<img src="https://github.com/nutjob-laboratories/qirc/raw/master/documentation/images/logo_250.png"><br>
	<a href="https://github.com/nutjob-laboratories/qirc/blob/master/documentation/QIRC_Class_Documentation.pdf"><b>Documentation for QIRC 0.0131</b></a><br>
</p>

# QIRC
QIRC is a Python 3 class for PyQt5 that is a full, multi-threaded IRC client.

# Example
This is a _very_ simple graphical IRC client. It will connect to a server as soon as it starts up, joins a channel, and allows the user to chat with the people in that channel.
```python
import sys
from qirc import QIRC

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

SERVER = "localhost"
PORT = 6667
NICKNAME = "qirc_example"
CHANNEL = "#qirc"

class SimpleClient(QMainWindow):

	def __init__(self,parent=None):
		super(SimpleClient, self).__init__(parent)

		# Build the graphical interface
		self.channelChatDisplay = QTextBrowser(self)
		self.channelUserDisplay = QListWidget(self)
		self.userTextInput = QLineEdit(self)
		self.userTextInput.returnPressed.connect(self.handleUserInput)

		self.horizontalSplitter = QSplitter(Qt.Horizontal)
		self.horizontalSplitter.addWidget(self.channelChatDisplay)
		self.horizontalSplitter.addWidget(self.channelUserDisplay)
		self.horizontalSplitter.setSizes([475,125])

		self.verticalSplitter = QSplitter(Qt.Vertical)
		self.verticalSplitter.addWidget(self.horizontalSplitter)
		self.verticalSplitter.addWidget(self.userTextInput)
		self.verticalSplitter.setSizes([575,25])

		clientLayout = QVBoxLayout()
		clientLayout.addWidget(self.verticalSplitter)

		clientInterface = QWidget()
		clientInterface.setLayout(clientLayout)
		self.setCentralWidget(clientInterface)

		# Create instance of QIRC
		self.client = QIRC(server=SERVER,port=PORT,nickname=NICKNAME)

		# Set up signals
		self.client.registered.connect(self.clientRegistered)
		self.client.public.connect(self.publicMessage)
		self.client.user_list.connect(self.userList)

		# Connect!
		self.client.start()

	def handleUserInput(self):
		# Get chat text from the GUI
		user_input = self.userTextInput.text()
		self.userTextInput.setText('')

		# Send the chat text to the server
		self.client.privmsg(CHANNEL,user_input)

		# Display the outgoing chat text
		self.channelChatDisplay.append("<b>"+NICKNAME+"</b>: "+user_input)
		self.channelChatDisplay.moveCursor(QTextCursor.End)

	def clientRegistered(self,serverdata):
		self.client.join(CHANNEL)

	def publicMessage(self,msgdata):
		self.channelChatDisplay.append("<b>"+msgdata["nickname"]+"</b>: "+msgdata["message"])
		self.channelChatDisplay.moveCursor(QTextCursor.End)

	def userList(self,userdata):
		self.channelUserDisplay.clear()
		for user in userdata["users"]:
			ui = QListWidgetItem()
			ui.setText(user)
			self.channelUserDisplay.addItem(ui)

if __name__ == '__main__':

	app = QApplication([])
	app.setFont(QFont("Consolas",10))

	qtclient = SimpleClient()
	qtclient.show()

	sys.exit(app.exec())
```
