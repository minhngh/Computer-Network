import time

class RtpPacket:
    HEADER_SIZE = 12
    def __init__(self):
        self.header = bytearray(RtpPacket.HEADER_SIZE)
    def encode(self, version, padding, extension, cc, seqnum, marker, pt, ssrc, payload):
        self.header[0] = (version << 6) & 0xC0;
        self.header[1] = pt & 0x80;
        self.header[2] = seqnum >> 8;
        self.header[3] = seqnum & 0xFF;
        time_t = int(time.time())
        self.header[4] = time_t >> 24;
        self.header[5] = (time_t >> 16) & 0xFF;
        self.header[6] = (time_t >> 8) & 0xFF;
        self.header[7] = time_t & 0xFF;
        self.payload = payload
    def getPacket(self): 
        return self.header + self.payload
    
    @staticmethod
    def decode(packet):
        return packet[:RtpPacket.HEADER_SIZE], packet[RtpPacket.HEADER_SIZE:]