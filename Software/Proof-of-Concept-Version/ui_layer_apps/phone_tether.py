# phone_tether.py

import socket
import pickle

class PhoneTether:
    """
    Sends small frames or JSON to your phone over TCP.
    Receives back JSON or primitives.
    """
    def __init__(self, host: str, port: int = 9999):
        self.host = host
        self.port = port

    def send(self, payload):
        """
        payload: any pickle-able object (e.g. frame crop, dict)
        returns: unpickled response from phone
        """
        data = pickle.dumps(payload, protocol=4)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.host, self.port))
            s.sendall(data)
            resp = b''
            while True:
                part = s.recv(4096)
                if not part: break
                resp += part
        return pickle.loads(resp)
