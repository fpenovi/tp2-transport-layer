from abc import ABC, abstractmethod
import socket

def _get_max_representable_number(number_of_bytes, byteorder='little'):
    max_number = int(-1).to_bytes(number_of_bytes, byteorder=byteorder, signed=True)
    return int.from_bytes(max_number, byteorder=byteorder, signed=False)

class SafeSocket(ABC):
    TCP = socket.SOCK_STREAM
    UDP = socket.SOCK_DGRAM
    MSG_LEN_REPR_BYTES = 2    # number of bytes used to represent the length of a message
    MAX_MSG_LEN = _get_max_representable_number(MSG_LEN_REPR_BYTES)
    DEFAULT_READ_BUFF = 2048

    def __init__(self):
        self.sock = self._make_socket()
        # The SO_REUSEADDR socket option is set in order to immediately reuse previous
        # sockets which were bound on the same address and remained in TIME_WAIT state.
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    @staticmethod
    def socket(sock_type=TCP):
        return SafeSocketUDP() if sock_type == SafeSocket.UDP else SafeSocketTCP()

    def bind(self, address):
        self.sock.bind(address)

    def send(self, data):
        data = self._as_bytes(data)
        datalength = len(data)
        data = self._encode_length(datalength) + data   # concatenate msg length to start of data
        datalength = len(data)  # update length with added bytes
        print(f'send datalength: {datalength}')

        total_bytes_sent = 0
        while total_bytes_sent < datalength:
            bytes_sent = self._sock_send(data[total_bytes_sent:])
            total_bytes_sent += bytes_sent
            self._check_conn(bytes_sent)

        return total_bytes_sent

    def close(self):
        self.sock.close()

    def _make_socket(self, sock=None):
        return self._make_underlying_socket() if sock is None else self._wrap_socket(sock)

    def _wrap_socket(self, sock):
        safe_sock = self.__class__()    # Create new instance of child class
        safe_sock.sock = sock       # Set it's underlying socket
        return safe_sock

    # noinspection PyMethodMayBeStatic
    def _check_conn(self, bytes_handled):
        if bytes_handled == 0:
            raise ConnectionBroken('Connection closed by peer')

    # noinspection PyMethodMayBeStatic
    def _as_bytes(self, data):
        if isinstance(data, bytes):
            pass
        elif isinstance(data, str):
            data = data.encode()
        else:
            raise TypeError('Data must be bytes or str')

        if len(data) > self.MAX_MSG_LEN:
            raise ValueError(f'Data must be at most {self.MAX_MSG_LEN} bytes. Consider splitting into chunks.')

        return data

    # noinspection PyMethodMayBeStatic
    def _encode_length(self, datalength):
        return datalength.to_bytes(self.MSG_LEN_REPR_BYTES, byteorder='little', signed=False)

    # noinspection PyMethodMayBeStatic
    def _decode_length(self, lengthdata):
        return int.from_bytes(lengthdata, byteorder='little', signed=False)

    @abstractmethod
    def _make_underlying_socket(self):
        pass

    @abstractmethod
    def _sock_send(self, data):
        pass

    @abstractmethod
    def recv(self):
        pass

class SafeSocketTCP(SafeSocket):

    def _make_underlying_socket(self):
        return socket.socket(type=self.TCP)

    def connect(self, address):
        self.sock.connect(address)

    def listen(self):
        self.sock.listen()

    def accept(self):
        conn, addr = self.sock.accept()
        safe_conn = self._make_socket(sock=conn)
        safe_conn.sock = conn
        return safe_conn, addr

    def _sock_send(self, data):
        return self.sock.send(data)

    def recv(self):
        datalength = self.__read_safely(self.MSG_LEN_REPR_BYTES)   # Reads first 2 bytes with length of message
        datalength = self._decode_length(datalength)
        return self.__read_safely(datalength)

    def __read_safely(self, length):
        chunks = []
        total_bytes_recvd = 0

        while total_bytes_recvd < length:
            bufsize = min(length - total_bytes_recvd, self.DEFAULT_READ_BUFF)
            chunk = self.sock.recv(bufsize)
            self._check_conn(len(chunk))
            chunks.append(chunk)
            total_bytes_recvd += len(chunk)

        return b''.join(chunks)

class SafeSocketUDP(SafeSocket):

    def __init__(self):
        super().__init__()
        self.addr = None

    def _make_underlying_socket(self):
        return socket.socket(type=self.UDP)

    def accept(self, addr, server_addr):
        safe_conn = SafeSocket.socket(sock_type=SafeSocket.UDP)
        safe_conn.addr = addr
        return safe_conn

    def connect(self, addr):
        self.addr = addr

    def _sock_send(self, data):
        return self.sock.sendto(data, self.addr)

    def recv(self):
        # Reads first 2 bytes with length of message
        # socket.MSG_PEEK indicates that the datagram readed should stay in the UDP buffer
        datalength, addr = self.__read_safely(self.MSG_LEN_REPR_BYTES, socket.MSG_PEEK)
        datalength = self._decode_length(datalength)
        # Read all the datagram, including the first 2 bytes with length of message
        bytes, addr = self.__read_safely(self.MSG_LEN_REPR_BYTES + datalength)
        # Don't return the first 2 bytes with length of message
        return bytes[self.MSG_LEN_REPR_BYTES:], addr

    def __read_safely(self, length, *flags):
        chunks = []
        total_bytes_recvd = 0
        addr = None
        while total_bytes_recvd < length:
            bufsize = min(length - total_bytes_recvd, self.DEFAULT_READ_BUFF)
            # the last read of this datagram
            if length - total_bytes_recvd <= self.DEFAULT_READ_BUFF:
                # remove datagram from the udp buffer
                chunk, addr = self.sock.recvfrom(bufsize, *flags)
            else:
                # keep datagram in the udp buffet
                chunk, addr = self.sock.recvfrom(bufsize, socket.MSG_PEEK)
            self._check_conn(len(chunk))
            chunks.append(chunk)
            total_bytes_recvd += len(chunk)
        return b''.join(chunks), addr

class ConnectionBroken(RuntimeError):
    pass
