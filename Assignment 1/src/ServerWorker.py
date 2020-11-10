from random import randint
import sys, traceback, threading, socket

from VideoStream import VideoStream
from RtpPacket import RtpPacket
import os

class ServerWorker:
	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'
	DESCRIBER = 'DESCRIBER'
	STOP = 'STOP'
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT

	OK_200 = 0
	FILE_NOT_FOUND_404 = 1
	CON_ERR_500 = 2
	
	clientInfo = {}
	
	def __init__(self, clientInfo):
		self.clientInfo = clientInfo
		
	def run(self):
		threading.Thread(target=self.recvRtspRequest).start()
	
	def recvRtspRequest(self):
		"""Receive RTSP request from the client."""
		connSocket = self.clientInfo['rtspSocket'][0]
		while True:
			#Change from 256 to 512
			data = connSocket.recv(512)
			if data:
				print("Data received:\n" + data.decode("utf-8"))
				self.processRtspRequest(data.decode("utf-8"))
	
	def processRtspRequest(self, data):
		"""Process RTSP request sent from the client."""
		# Get the request type
		request = data.split('\n')
		line1 = request[0].split(' ')
		requestType = line1[0]
		
		# Get the media file name
		filename = line1[1]
		
		# Get the RTSP sequence number 
		seq = request[1].split(' ')

		if requestType == self.DESCRIBER:
			if self.state == self.INIT:
				print("processing DESCRIBER\n")
				port = request[2].split(' ')[1]
				address = request[2].split(' ')[3]
				try:
					self.replyRtspDescriber(self.OK_200, seq[1], filename, port, address)
				except IOError:
					self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
		# Process SETUP request
		if requestType == self.SETUP:
			if self.state == self.INIT:
				# Update state
				print("processing SETUP\n")
				
				try:
					self.clientInfo['videoStream'] = VideoStream(filename)
					self.state = self.READY
				except IOError:
					print('SETUP ERROR')
					self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
				
				# Generate a randomized RTSP session ID
				self.clientInfo['session'] = randint(100000, 999999)
				
				# Send RTSP reply
				self.replyRtsp(self.OK_200, seq[1])
				
				# Get the RTP/UDP port from the last line
				self.clientInfo['rtpPort'] = request[2].split(' ')[3]
		
		# Process PLAY request 		
		elif requestType == self.PLAY:
			if self.state == self.READY:
				print("processing PLAY\n")
				self.state = self.PLAYING
				
				# Create a new socket for RTP/UDP
				self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
				self.replyRtsp(self.OK_200, seq[1])
				
				# Create a new thread and start sending RTP packets
				self.clientInfo['event'] = threading.Event()
				self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
				self.clientInfo['worker'].start()
		
		# Process PAUSE request
		elif requestType == self.PAUSE:
			if self.state == self.PLAYING:
				print("processing PAUSE\n")
				self.state = self.READY
				
				self.clientInfo['event'].set()
			
				self.replyRtsp(self.OK_200, seq[1])

		elif requestType == self.STOP:
			print("processing STOP\n")
			self.state = self.READY
			
			self.clientInfo['event'].set()
		
			self.replyRtsp(self.OK_200, seq[1])
			self.clientInfo['videoStream'].reset()

		# Process TEARDOWN request
		elif requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")
			if self.clientInfo.get('event', False):
				self.clientInfo['event'].set()
			
			
			self.replyRtsp(self.OK_200, seq[1])
			
			# Close the RTP socket
			if self.clientInfo.get('rtpSocket', False):
				self.clientInfo['rtpSocket'].close()
			self.state = self.INIT
			
	def sendRtp(self):
		"""Send RTP packets over UDP."""
		while True:
			self.clientInfo['event'].wait(0.05) 
			
			# Stop sending if request is PAUSE or TEARDOWN
			if self.clientInfo['event'].isSet(): 
				break 
				
			data,framelength = self.clientInfo['videoStream'].nextFrame()
			if data: 
				frameNumber = self.clientInfo['videoStream'].frameNbr()

				if 'framelength' in self.clientInfo:
					self.clientInfo['framelength'].append(framelength)
				else: self.clientInfo['framelength'] = [framelength]

				if 'sended' in self.clientInfo:
					self.clientInfo['sended'].append(frameNumber)
				else:
					self.clientInfo['sended'] = []
				size = sum(self.clientInfo['framelength']).to_bytes(28,'big')
				count = len(self.clientInfo['sended']).to_bytes(28,'big')
				data = size + count + data
				# address = self.clientInfo['rtspSocket'][1][0]
				# port = int(self.clientInfo['rtpPort'])
				# self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address,port))
				try:
					address = self.clientInfo['rtspSocket'][1][0]
					port = int(self.clientInfo['rtpPort'])
					self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address,port))
				except:
					print("Connection Error")
					#print('-'*60)
					#traceback.print_exc(file=sys.stdout)
					#print('-'*60)

	def makeRtp(self, payload, frameNbr):
		"""RTP-packetize the video data."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		marker = 0
		pt = 26 # MJPEG type
		seqnum = frameNbr
		ssrc = 0 
		
		rtpPacket = RtpPacket()
		
		rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
		
		return rtpPacket.getPacket()
		
	def replyRtsp(self, code, seq):
		"""Send RTSP reply to the client."""
		if code == self.OK_200:
			#print("200 OK")
			reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
			# if ('sended' in self.clientInfo) & ('framelength' in self.clientInfo):
			# 	length = sum(self.clientInfo['framelength'])
			# 	reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSended: ' + str(len(self.clientInfo['sended'])) + '\nLength: ' + str(length) + '\nSession: ' + str(self.clientInfo['session']) 
			
			connSocket = self.clientInfo['rtspSocket'][0]
			connSocket.send(reply.encode())

		# Error messages
		elif code == self.FILE_NOT_FOUND_404:
			print("404 NOT FOUND")
		elif code == self.CON_ERR_500:
			print("500 CONNECTION ERROR")


	def replyRtspDescriber(self,code,seq, filename, port, address):
		if code == self.OK_200:
			# print("200 OK")
			file_stats = os.stat(filename)

			reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\n' + \
			'Content-Base: ' + str(filename) + '\n' + 'Content-Type: application/sdp\n'+\
			'Content-Length: ' + str(file_stats.st_size)+ '\n\n'+ \
			'm=video '+ port + ' RTP/AVP 26\n'+ \
			'c=IN IP4 ' + address + '\n'+\
			'a=rtpmap:26 JPEG/90000' +'\n'+\
			"""a=StreamName:string;"hinted video track" """


			connSocket = self.clientInfo['rtspSocket'][0]
			connSocket.send(reply.encode())

		# Error messages
		elif code == self.FILE_NOT_FOUND_404:
			print("404 NOT FOUND")
		elif code == self.CON_ERR_500:
			print("500 CONNECTION ERROR")