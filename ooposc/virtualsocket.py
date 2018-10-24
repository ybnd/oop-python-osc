import json
import warnings
from random import randint

class VirtualSocket:
    __ADDRESSES__ = []

    def __init__(self):
        self.set_address()

    @property
    def address(self):
        if not hasattr(self, '_mock_address'):
            self.set_address()
        return self._mock_address

    @property
    def real_address(self):
        if hasattr(self, '_address'):
            return self._address

    def set_address(self):
        address = f"v192.168.{randint(0,255)}.{randint(0,255)}"
        port = randint(50000, 60000)

        if address not in self.__ADDRESSES__:
            self.__ADDRESSES__.append(address)
            self._mock_address = (address, port)
        else:
            self.set_address()

    def decode(self, data):
        """ Check if incoming data is formatted correctly """
        try:
            vsm_bundle = json.loads(data)
            assert isinstance(vsm_bundle, dict)
            assert sorted(list(vsm_bundle.keys())) \
                   == sorted(['sender_address', 'to_address', 'data'])

        except (json.decoder.JSONDecodeError, AssertionError):
            warnings.warn(f"{data} is not a valid VirtualSocketMessage")
            return None

        if vsm_bundle['to_address'] == self.address \
                or vsm_bundle['to_address'] == None:
            return vsm_bundle['data'], tuple(vsm_bundle['sender_address'])
        else:
            return bytes(''), ('', 0)

    def encode(self, data, to_address = None):
        """ Format outgoing data """
        # todo: checks on address / data?
        if type(data) == bytes:
            data = data.decode('utf-8')
        return json.dumps(
            {
                'sender_address': self.address, 
                'to_address': to_address, 
                'data': data
            }
        ).encode()


def __decode_VSM__(data: (str, bytes)):
    """ Check if incoming data is formatted correctly """
    try:
        vsm_bundle = json.loads(data)
        assert isinstance(vsm_bundle, dict)
        assert sorted(list(vsm_bundle.keys())) \
               == sorted(['sender_address', 'data'])

    except (json.decoder.JSONDecodeError, AssertionError):
        warnings.warn(f"{data} is not a valid VirtualSocketMessage")
        return None

    return vsm_bundle['data'], vsm_bundle['sender_address']

def __encode_VSM__(data: (str, bytes), address: str):
    """ Format outgoing data """
    # todo: checks on address / data?
    if type(data) == bytes:
        data = data.decode('utf-8')
    return json.dumps({'sender_address': address, 'data': data}).encode()

