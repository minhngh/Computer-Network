from tkinter import Button, Label, Frame
from tkinter import LEFT, BOTTOM, BOTH, X
from tkinter.messagebox import showinfo, showerror
import threading
import socket
from PIL import Image, ImageTk
import io
from RtpPacket import RtpPacket
from enum import Enum
import time

class State(Enum):
    INIT = 0
    READY = 1
    PLAYING = 2
class RequestType(Enum):
    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3


class Client:
    NUMBER_BUTTONS = 4
    PADX = 5
    PADY = 7
    RTP_BUFFER_SIZE = 15 * 1024
    RTSP_BUFFER_SIZE = 256
    def __init__(self, root, serverAddr, serverPort, rtpPort, fileName):
        self.master = root
        self.serverAddr = serverAddr
        self.serverPort = int(serverPort)
        self.rtpPort = int(rtpPort)
        self.fileName = fileName
        self.sessionId = None
        self.state = State.INIT
        self.setup_connection()
        self.init_ui()
        self.recivedFrames = []  #statistic
        self.count_received = 0        #total frame that client received
        self.timeline = []
        self.count_sended = 0    #server will send this value
        self.length_sended = 0   #server will send this value
    def init_ui(self):
        self.draw_frame()
        self.draw_buttons()
    def draw_frame(self):
        self.label_video = Label(self.master)
        self.label_video.pack(fill = BOTH, expand = True)
        self.frame_button = Frame(self.master)
        self.frame_button.pack(fill = X, side = BOTTOM)
        for i in range(Client.NUMBER_BUTTONS):
            self.frame_button.columnconfigure(i, weight = 1)
        
    def draw_buttons(self):
        self.btn_setup = Button(self.frame_button, text = 'Setup', command = self.click_setup)
        self.btn_play = Button(self.frame_button, text = 'Play', command = self.click_play)
        self.btn_pause = Button(self.frame_button, text = 'Pause', command = self.click_pause)
        self.btn_teardown = Button(self.frame_button, text = 'Teardown', command = self.click_teardown)

        self.btn_setup.grid(row = 0, column = 0, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)
        self.btn_play.grid(row = 0, column = 1, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)
        self.btn_pause.grid(row = 0, column = 2, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)        
        self.btn_teardown.grid(row = 0, column = 3, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)

    def click_setup(self): 
        if self.state == State.INIT:
            self.send_rtsp_request(RequestType.SETUP)
    def click_play(self):
        if self.state == State.READY:
            self.send_rtsp_request(RequestType.PLAY)
    def click_pause(self): 
        if self.state == State.PLAYING:
            self.send_rtsp_request(RequestType.PAUSE)
    def click_teardown(self): 
        if self.state == State.READY or self.state == State.PLAYING:
            self.send_rtsp_request(RequestType.TEARDOWN)
    
    def setup_connection(self):
        self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtsp_socket.connect((self.serverAddr, self.serverPort))
        self.client_host = self.rtsp_socket.getsockname()[0]
    def send_rtsp_request(self, requestType):
        self.last_requesttype = requestType
        if self.rtsp_socket is None:
            self.setup_connection()
        if requestType == RequestType.SETUP:
            threading.Thread(target = self.process_rtsp_request).start()
            self.cseq = 1
            request = f'SETUP {self.fileName} RTSP/1.0\nCSeq: {self.cseq} \nTransport: RTP/UDP; client_port= {self.rtpPort}'
        elif requestType == RequestType.PLAY:
            self.cseq += 1
            request = f'PLAY {self.fileName} RTSP/1.0\nCseq: {self.cseq}\nSession: {self.sessionId}'
        elif requestType == RequestType.PAUSE:
            self.cseq += 1
            request = f'PAUSE {self.fileName} RTSP/1.0\nCseq: {self.cseq}\nSession: {self.sessionId}'
        elif requestType == RequestType.TEARDOWN:
            self.cseq += 1
            request = f'TEARDOWN {self.fileName} RTSP/1.0\nCseq: {self.cseq}\nSession: {self.sessionId}'
        self.rtsp_socket.send(request.encode())
    def open_rtp_port(self):
        self.rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtp_socket.settimeout(.5)
        try:
            self.rtp_socket.bind((self.client_host, self.rtpPort))
        except socket.timeout:
            showerror('error', '[TIME_OUT] failed for opening rtp port')
        print('[LOG] Rtp port is opened successfully')
    def process_rtsp_request(self):
        while True:
            data = self.rtsp_socket.recv(Client.RTSP_BUFFER_SIZE).decode()
            if data:
                request = data.split('\n')
                print(request)
                seqNum = int(request[1].split()[1])
                if seqNum == self.cseq:
                    sessionId = int(request[-1].split()[1])
                    if self.sessionId is None:
                        self.sessionId = sessionId
                    status_code = int(request[0].split()[1])
                    if self.sessionId == sessionId and status_code == 200:
                        if self.last_requesttype == RequestType.SETUP:
                            self.open_rtp_port()
                            self.state = State.READY
                        elif self.last_requesttype == RequestType.PLAY:
                            threading.Thread(target = self.receive_rtp_packet).start()
                            self.state = State.PLAYING
                        elif self.last_requesttype == RequestType.PAUSE:
                            self.state = State.READY
                        elif self.last_requesttype == RequestType.TEARDOWN:
                            self.state = State.INIT
                            self.count_sended = int(request[-3].split()[1])
                            self.length_sended = int(request[-3].split()[1])
                            self.display_statistics()
                            self.reset()
                            self.display_cancel()
                            break

    def receive_rtp_packet(self):
        while True:
            try:
                start = time.time()
                data, clientAddr = self.rtp_socket.recvfrom(Client.RTP_BUFFER_SIZE)
                if data:
                    header, payload = RtpPacket.decode(data)
                    self.recivedFrames.append(header[2]*256 + header[3])
                    image = Image.open(io.BytesIO(payload))
                    imagetk = ImageTk.PhotoImage(image = image)
                    self.label_video.configure(image = imagetk)
                    self.label_video.image = imagetk
                end = time.time()
                self.timeline.append(end-start)
            except:
                if self.last_requesttype == RequestType.PAUSE:
                    print('[LOG]', 'Video is paused')
                break
    def reset(self):
        self.rtp_socket.close()
        self.rtsp_socket = None
        self.sessionId = None
    def display_cancel(self):
        showinfo('info', 'The video is cancelled')
        # Clear frame being displayed
        self.label_video.image = None

    def display_statistics(self):
        print(f'\nStatitics of Session ID = {self.sessionId}:')
        self.count_received = len(self.recivedFrames)
        if self.count_sended != 0:
            print(f'\tLoss rate = 1 - {self.count_received} / {self.count_sended} = {(1 - self.count_received/self.count_sended) *100}%')
            totaltime = sum(self.timeline)
            print(f'\tVideo data rate = Video_size / Total time = {self.length_sended/totaltime} (bps)')
        
        else:
            print('\tLoss rate = SERVER DID NOT SEND ANYTHING ')
        print('='*50+'\n')