from tkinter import Button, Label, Frame
from tkinter import LEFT, BOTTOM, BOTH, X
from tkinter.messagebox import showinfo, showerror,askyesno
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
    DESCRIBE = 4
    STOP = 10


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
        self.timeline = 0
        self.total_size = 0
        self.count_sended = 0    #server will send this value
        self.length_sended = 0   #server will send this value
        self.type = RequestType.SETUP
        self.event = None
        self.cseq = 0
        self.start = 0
        self.begin_pause = 0
        self.pause_time = 0
        self.is_pausing = False
        self.receive_frame = []
        self.loss = 0
        self.has_play = False
        self.send_rtsp_request(RequestType.SETUP) #send request Setup when init

    def init_ui(self):
        self.draw_frame()
        self.draw_statitics()
        self.draw_buttons()
        # self.draw_describe()

    # def draw_describe(self):
    #     self.describe = Label(self.master)
    #     self.describe.pack(fill=X)
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
        #self.btn_setup = Button(self.frame_button, text = 'Setup', command = self.click_setup)
        self.btn_play = Button(self.frame_button, text = 'Play', command = self.click_play)
        self.btn_pause = Button(self.frame_button, text = 'Pause', command = self.click_pause)
        #self.btn_teardown = Button(self.frame_button, text = 'Teardown', command = self.click_teardown)
        self.btn_describe = Button(self.frame_button, text='Describe', command=self.click_describe)
        self.btn_stop = Button(self.frame_button, text = 'Stop', command = self.click_stop)


        #self.btn_setup.grid(row = 0, column = 1, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)
        self.btn_play.grid(row = 0, column = 1, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)
        self.btn_pause.grid(row = 0, column = 2, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)
        #self.btn_teardown.grid(row = 0, column = 4, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)
        self.btn_describe.grid(row=0, column=0, sticky='EW', padx=Client.PADX, pady=Client.PADY)
        self.btn_stop.grid(row = 0, column = 3, sticky = 'EW', padx = Client.PADX, pady = Client.PADY)


    def click_describe(self):
        if self.rtsp_socket:
            self.type = RequestType.DESCRIBE
            self.send_rtsp_request(RequestType.DESCRIBE)

    def click_setup(self):
        if self.state == State.INIT:
            self.type = RequestType.SETUP
            self.send_rtsp_request(RequestType.SETUP)
    def click_play(self):
        if self.state == State.INIT:
            yesno = askyesno('Connection Over Time', 'Do you want to reconnect?') # Yes / No
            if yesno == True:
                self.send_rtsp_request(RequestType.SETUP)
        if self.state == State.READY:
            self.type = RequestType.PLAY
            self.has_play = True
            self.send_rtsp_request(RequestType.PLAY)
    def click_pause(self):
        if self.state == State.PLAYING:
            self.type = RequestType.PAUSE
            self.send_rtsp_request(RequestType.PAUSE)
    def click_teardown(self):
        if self.state == State.READY or self.state == State.PLAYING:
            self.type = RequestType.TEARDOWN
            self.send_rtsp_request(RequestType.TEARDOWN)
    def click_stop(self):
        if self.state != State.INIT and self.has_play:
            self.type = RequestType.STOP
            self.send_rtsp_request(RequestType.STOP)
    def setup_connection(self):
        self.rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtsp_socket.connect((self.serverAddr, self.serverPort))
        self.client_host = self.rtsp_socket.getsockname()[0]
    def send_rtsp_request(self, requestType):
        self.last_requesttype = requestType
        if self.rtsp_socket is None:
            self.setup_connection()
        if requestType == RequestType.DESCRIBE:
            if self.event:
                if not self.event.is_alive():
                    self.event.start()
            else:
                self.event = threading.Thread(target = self.process_rtsp_request)
                self.event.start()

            self.cseq = self.cseq + 1
            request = "DESCRIBE " + str(self.fileName) +  " RTSP/1.0"+ "\n"+\
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
        elif requestType == RequestType.STOP:
            self.cseq += 1
            request = f'STOP {self.fileName} RTSP/1.0\nCseq: {self.cseq}\nSession: {self.sessionId}'
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
                if self.type == RequestType.DESCRIBE:
                    print(data)
                    showinfo("Describe Infomation", data)
                    # self.describe['text'] = '*****Describe Info*****\n' + data
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
                            elif self.last_requesttype == RequestType.STOP:
                                self.state = State.READY
                                self.total_size = 0
                                self.timeline = 0
                                self.receive_frame = []
                                self.is_pausing = True
                                self.begin_pause = time.time()
                                t = threading.Thread(target=self.count_not_request_time, args=())
                                t.start()
                            elif self.last_requesttype == RequestType.TEARDOWN:
                                #self.describe['text'] = ''
                                self.state = State.INIT
                                self.display_cancel()
                                self.reset()
                                self.has_play = False
                                break

    def receive_rtp_packet(self):
        if self.start == 0:
            self.start = time.time()
        while True:
            try:
                data, clientAddr = self.rtp_socket.recvfrom(Client.RTP_BUFFER_SIZE)
                if data:
                    header, payload = RtpPacket.decode(data)
                    now = time.time()

                    frame_nbr = header[2]*256 + header[3]
                    self.receive_frame.append(frame_nbr)
                    if frame_nbr < max(self.receive_frame):
                        self.loss += 1
                    if self.is_pausing:
                        self.is_pausing = False
                        self.pause_time += now - self.begin_pause
                    self.timeline = (now - self.start) - self.pause_time
                    
                    self.total_size += len(payload)

                    text = '\tSTATISTICS'
                    text += '\nLoss rate = {:.2f}%'.format(self.loss/len(self.receive_frame)*100) 
                    text += '\nVideo data rate = {:.2f} (bps)'.format(self.total_size/self.timeline) 
                    text += f'\nNumber of frames = {len(self.receive_frame)}'
                    self.statitics.config(text = text,justify = 'left')

                    image = Image.open(io.BytesIO(payload))
                    imagetk = ImageTk.PhotoImage(image = image)
                    self.label_video.configure(image = imagetk)
                    self.label_video.image = imagetk
            except:
                if self.last_requesttype == RequestType.PAUSE:
                    print('[LOG]', 'Video is paused')
                    self.begin_pause = time.time()
                    self.is_pausing = True
                elif self.state == State.PLAYING:
                    showinfo('info', 'The video is ended')
                    # Clear frame being displayed
                    self.label_video.image = None
                    self.statitics.config(text = "")
                    self.state = State.READY
                    self.receive_frame = []
                break
    def reset(self):
        self.rtp_socket.close()
        self.rtsp_socket.shutdown(socket.SHUT_RDWR)
        self.rtsp_socket.close()
        self.rtp_socket = self.rtsp_socket = None
        self.sessionId = None
        self.timeline = 0
        self.statitics.config(text = "")
        self.state = State.INIT
        # self.loss = 0
        self.receive_frame = []
    def display_cancel(self):
        showinfo('info', 'The video is cancelled')
        # Clear frame being displayed
        self.label_video.image = None
    def count_not_request_time(self):
        count = 0
        while self.state == State.READY:
            print(str(9-count) + 's left to disconnect' ) #count time :))
            time.sleep(1)
            count += 1
            if count >=10:
                print('Disconnect!')
                self.last_requesttype = RequestType.TEARDOWN
                self.send_rtsp_request(RequestType.TEARDOWN)
                break
