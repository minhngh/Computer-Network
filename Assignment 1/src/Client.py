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
    DESCRIBER = 4


class Client:
    NUMBER_BUTTONS = 5
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
        self.count_received = 0        #total frame that client received
        self.timeline = 0
        self.count_sended = 0    #server will send this value
        self.length_sended = 0   #server will send this value

        self.type = RequestType.SETUP
        self.event = None
        self.cseq = 0

    def init_ui(self):
        self.draw_frame()
        self.draw_statitics()
        self.draw_buttons()
        self.draw_describer()

    def draw_describer(self):
        self.describer = Label(self.master)
        self.describer.pack(fill=X)
    def draw_frame(self):
        self.label_video = Label(self.master)
        self.label_video.pack(fill = BOTH, expand = True)
        self.frame_button = Frame(self.master)
        self.frame_button.pack(fill = X, side = BOTTOM)
        for i in range(Client.NUMBER_BUTTONS):
            self.frame_button.columnconfigure(i, weight = 1)
    
    def draw_statitics(self):
        # if sended != 0:
        self.statitics = Label(self.master)
        self.statitics.pack(fill = X)
        
    def draw_buttons(self):
        self.btn_setup = Button(self.frame_button, text = 'Setup', command = self.click_setup)
        self.btn_play = Button(self.frame_button, text = 'Play', command = self.click_play)
        self.btn_pause = Button(self.frame_button, text = 'Pause', command = self.click_pause)
        self.btn_teardown = Button(self.frame_button, text = 'Teardown', command = self.click_teardown)
        self.btn_describer = Button(self.frame_button, text='Describer', command=self.click_describer)

        self.btn_setup.grid(row = 0, column = 1, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)
        self.btn_play.grid(row = 0, column = 2, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)
        self.btn_pause.grid(row = 0, column = 3, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)
        self.btn_teardown.grid(row = 0, column = 4, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)
        self.btn_describer.grid(row=0, column=0, sticky='EW', padx=Client.PADX, pady=Client.PADY)

    def click_describer(self):
        self.type = RequestType.DESCRIBER
        self.send_rtsp_request(RequestType.DESCRIBER)

    def click_setup(self):
        self.type = RequestType.SETUP
        if self.state == State.INIT:
            self.send_rtsp_request(RequestType.SETUP)
    def click_play(self):
        self.type = RequestType.PLAY
        if self.state == State.READY:
            self.send_rtsp_request(RequestType.PLAY)
    def click_pause(self):
        self.type = RequestType.PAUSE
        if self.state == State.PLAYING:
            self.send_rtsp_request(RequestType.PAUSE)
    def click_teardown(self):
        self.type = RequestType.TEARDOWN
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
        if requestType == RequestType.DESCRIBER:
            if self.event:
                if not self.event.is_alive():
                    self.event.start()
            else:
                self.event = threading.Thread(target = self.process_rtsp_request)
                self.event.start()

            self.cseq = self.cseq + 1
            request = "DESCRIBER " + str(self.fileName) +  " RTSP/1.0"+ "\n"+\
                    "CSeq: " + str(self.cseq) +"\n"+\
                'Port: '+str(self.serverPort) + ' IP: '+ str(self.serverAddr)

        elif requestType == RequestType.SETUP:
            self.event = threading.Thread(target = self.process_rtsp_request)
            if not self.event.is_alive():
                self.event.start()
            self.cseq = self.cseq + 1
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
                if self.type == RequestType.DESCRIBER:
                    print(data)
                    self.describer['text'] = '*****Describer Info*****\n' + data
                else:
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
                                self.describer['text'] = ''
                                self.state = State.INIT
                                self.reset()
                                self.display_cancel()
                                break

    def receive_rtp_packet(self):
        while True:
            start = time.time()
            try:
                data, clientAddr = self.rtp_socket.recvfrom(Client.RTP_BUFFER_SIZE)
                if data:
                    header, payload = RtpPacket.decode(data)
                    statitics = payload[:56]
                    end = time.time()
                    size = int.from_bytes(statitics[:28],'big')
                    sended = int.from_bytes(statitics[28:],'big')
                    self.count_received += 1
                    self.timeline += (end - start)
                    text = ""
                    if sended != 0:
                        text = '\tSTATITICS'
                        text += '\nLoss rate = {:.2f}%'.format((1 - (self.count_received-1)/sended)*100) 
                        text += '\nVideo data rate = {:.2f} (bps)'.format(size/self.timeline) 
                        text += f'\nNumber of frames = {sended}'
                    self.statitics.config(text = text,justify = 'left')
                    # self.statitics.config(text = str(end-start))
                    payload = payload[56:]
                    image = Image.open(io.BytesIO(payload))
                    imagetk = ImageTk.PhotoImage(image = image)
                    self.label_video.configure(image = imagetk)
                    self.label_video.image = imagetk
            except:
                if self.last_requesttype == RequestType.PAUSE:
                    print('[LOG]', 'Video is paused')
                break
    def reset(self):
        self.rtp_socket.close()
        self.rtsp_socket = None
        self.sessionId = None
        self.timeline = 0
        self.count_received = 0
        self.statitics.config(text = "")
    def display_cancel(self):
        showinfo('info', 'The video is cancelled')
        # Clear frame being displayed
        self.label_video.image = None