from pythonosc.osc_server import ThreadingOSCUDPServer, BlockingOSCUDPServer
from collections import Iterable
from pythonosc.osc_message_builder import OscMessageBuilder

import struct
import socket
from abc import ABCMeta, abstractmethod

from ooposc.virtualsocket import VirtualSocket
from ooposc.register import DynamicRegistrar, dispatchOSC, handleOSC

from pythonosc import dispatcher
from pythonosc import osc_packet
import socketserver

import time
import asyncio
import threading

import collections

import re

import logging


class OSCInterface:
    __metaclass__ = ABCMeta

    @abstractmethod
    def __init__(self, app, address, send_portport):
        """ Instantiate an OSC interface class """
        raise NotImplementedError

    @abstractmethod
    def address(self):
        """ Return own (receiving) address """
        raise NotImplementedError

    @abstractmethod
    def handle(self):
        """ Handle incoming requests """
        raise NotImplementedError

    @abstractmethod
    def send(self, osc_address, values, address = None, port = None):
        """
        Send an OSC message.
            - calls build.osc(osc_address, values) -> message
                - if address & port provided:
                    call unicast(message, address, port)
                - else: call multicast(message)

        :param osc_address:
        :param values:
        :param address:
        :param port:
        :return:
        """
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def build_osc(osc_address, values):
        """
        Build an OSC message
        :param osc_address:     OSC address (e.g. '/filter', '/LED/toggle', ...)
        :param values:          List of values. Will be encoded into
                                OSC-compatible types internally.
        :return:                message (bytes)
        """
        raise NotImplementedError

    @abstractmethod
    def multicast(self, message):
        """ Multicast an OSC message """
        raise NotImplementedError

    @abstractmethod
    def unicast(self, message, address, port):
        """ Unicast an OSC message """
        raise NotImplementedError

MethodHandler = collections.namedtuple(
    typename = 'MethodHandler',
    field_names = ('callback', 'instance', 'args')
)

class MethodDispatcher(dispatcher.Dispatcher):
    def _init__(self):
        dispatcher.Dispatcher.__init__(self)
        self._default_instance = None

    def map_method(self, address, handler, instance, *args):
        self._map[address].append(MethodHandler(handler, instance, list(args)))

    def handlers_for_address(self, address_pattern):
        """yields Handler namedtuples matching the given OSC pattern.
                Copied from python-osc todo: add which release!
        """
        # First convert the address_pattern into a matchable regexp.
        # '?' in the OSC Address Pattern matches any single character.
        # Let's consider numbers and _ "characters" too here, it's not said
        # explicitly in the specification but it sounds good.
        escaped_address_pattern = re.escape(address_pattern)
        pattern = escaped_address_pattern.replace('\\?', '\\w?')
        # '*' in the OSC Address Pattern matches any sequence of zero or more
        # characters.
        pattern = pattern.replace('\\*', '[\w|\+]*')
        # The rest of the syntax in the specification is like the re module so
        # we're fine.
        pattern = pattern + '$'
        pattern = re.compile(pattern)
        matched = False

        for addr, handlers in self._map.items():
            if (pattern.match(addr)
                    or (('*' in addr)
                        and re.match(
                                addr.replace('*', '[^/]*?/*'),
                                address_pattern
                            )
                    )
            ):
                yield from handlers
                matched = True

        if not matched and self._default_handler:
            logging.debug('No handler matched but default handler present, '
                          'added it.')
            yield MethodHandler(
                self._default_handler, self._default_instance, []
            )

    def set_default_handler(self, handler):
        """Sets the default handler.

        Must be a function with the same constaints as with the self.map method
        or None to unset the default handler.
        """
        self._default_handler = handler


@dispatchOSC  # todo: if everything's inheriting from this anyway, why do we need this?
class OSCApp(DynamicRegistrar):
    """ Method registering & dispatching class

            Maps all registered OSC handler methods to a pythonosc Dispatcher
    """
    def __init__(self, name):
        DynamicRegistrar.__init__(self)
        self.name = name
        self._dispatcher = MethodDispatcher()
        self._map_methods()

    def _map_methods(self):
        """ Maps OSC handler methods from self._handler_registry to a Dispatcher (adapted from pythonosc) """
        implementations = [self.__class__.__name__]
        for base in self.__class__.__bases__:
            implementations.append(base.__name__)

        if not '_mapped' in self._instance_handlers.keys():
            self._instance_handlers['_mapped'] = {}

        for implementation in implementations: # todo: clean up!
            try:
                if not implementation in self._instance_handlers['_mapped'] \
                        and implementation in self._instance_handlers.keys():
                    self._instance_handlers['_mapped'][implementation] = {}

                handlers = self._instance_handlers[implementation].items()
                for address, handler in list(handlers):
                    if address not in self._instance_handlers['_mapped'][implementation]:
                        if isinstance(handler, tuple):  # handler is a (method, instance)
                            method = handler[0]
                            instance = handler[1]
                        else:
                            method = handler  # made obsolete by RegisteringObject.__init__()...
                            instance = self

                        self._dispatcher.map_method(address, method, instance, method._kwargs)

                        self._instance_handlers['_mapped'][implementation].update(
                            {address: self._instance_handlers[implementation].pop(address)}
                        )
            except KeyError:
                pass  # no methods registered for OSC in this class

    def map_function(self, address, handler, *args):
        self._dispatcher.map(address, handler, args)

    def _call_handlers_for_packet(self, data, client_address):
        """ Call OSC handler methods by packet's OSC address (adapted from python-osc todo: add version) """
        try:
            packet = osc_packet.OscPacket(data)
            # todo: search nested objects at this level: for all dispatching objects in self:
            # todo: MAKE THIS _call_handlers for all subobjects and _call_handlers_for_packet for all others.
            for timed_msg in packet.messages:
                now = time.time()
                handlers = self._dispatcher.handlers_for_address( # todo: or maybe override this thing even
                    timed_msg.message.address)
                if not handlers:
                    continue
                # If the message is to be handled later, then so be it.
                if timed_msg.time > now:
                    time.sleep(timed_msg.time - now)
                for handler in handlers:
                    method = handler.callback
                    if hasattr(handler, 'instance'):
                        instance = handler.instance
                        # if len(handler.args): # todo: assuming this will never be used
                        #     method(instance, handler.args, *timed_msg.message)
                        if method._pass_address:
                            method(instance, client_address, *timed_msg.message)
                        else:
                            method(instance, *timed_msg.message)
                    else:
                        # if handler.args == True: # todo: assuming this will never be used
                        #     method(handler.args, *timed_msg.message)
                        if method._pass_address:
                            method(client_address, *timed_msg.message)
                        else:
                            method(*timed_msg.message)
        except osc_packet.ParseError:
            print('Parse Error!')
            pass

    def __setattr__(self, key, value):
        """ Add attribute and re-map all registered methods """
        # todo: don't need a full remap
        DynamicRegistrar.__setattr__(self, key, value)
        if hasattr(value, '_instance_handler_registry'):
            self._map_methods()

    def connect(self, address, send_port, OSCServer = OSCInterface):
        self.server = OSCServer(self, address, send_port)

    def handle(self):
        self.server.handle()


def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


class ParallelApp:
    __INSTANCES__ = []

    def __init__(self, app: OSCApp):
        self.__INSTANCES__.append(self)

        self.__LOOP__ = asyncio.new_event_loop()
        self.__THREAD__ = threading.Thread(
            target = start_loop, args = (self.__LOOP__,)
        )
        self.__THREAD__.start()

        self._app = app

        self._do_listen = True
        self.listen()

    def background(self, method):
        self.__LOOP__.call_soon_threadsafe(method)

    def await_event(self):
        self._app.handle()
        if self._do_listen:
            self.await_event()

    def listen(self):
        self.background(self.await_event)

    def quit(self):
        for instance in self.__INSTANCES__:
            instance.__LOOP__.stop()


class UDPMethodHandler(socketserver.BaseRequestHandler):
    """ Handle UDP requests. Points back to receiving OSCApp for attribute access. """
    def __init__(self, client_address, request, server, app: OSCApp):
        self._app = app
        socketserver.BaseRequestHandler.__init__(
            self, client_address, request, server
        )
        # self.client_port = client_port

    def handle(self):
        self._app._call_handlers_for_packet(self.request[0], self.client_address)



class Multicast():
    __MULTICAST_GROUP__ = "239.0.0.1"
    __MULTICAST_PORT__ = 5001

class MulticastPythonOSC(ThreadingOSCUDPServer, Multicast, OSCInterface):

    """
    Based on python-osc https://github.com/attwad/python-osc

        * Implement receive & send on a single interface
        * Multicasting support
    """

    def __init__(self, app: OSCApp, address = '', send_port = ''):
        self.allow_reuse_address = True

        ThreadingOSCUDPServer.__init__(
            self, (address, self.__MULTICAST_PORT__), app._dispatcher
        )
        self.RequestHandlerClass = UDPMethodHandler
        self._app = app

        # Set up server for Multicasting
        mreq = struct.pack(
            "4sl", socket.inet_aton(self.__MULTICAST_GROUP__), socket.INADDR_ANY
        )
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)


        # Set up client for Multicasting
        # self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # self.send_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # self.send_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        # self.send_socket.bind((address, send_port))

        self._address = self.server_address # todo: this is dumb support for mutual inheritance from VirtualSocket...

    @staticmethod
    def build_osc(osc_address, values):
        """ Copied from pythonosc.udp_client """
        builder = OscMessageBuilder(address = osc_address)
        if not isinstance(values, Iterable) or isinstance(values, (str, bytes)):
            values = [values]
        for val in values:
            builder.add_arg(val)
        content = builder.build()
        return content.dgram

    def finish_request(self, request, client_address):
        """ Override finish_request() to allow class method dispatching """
        self.RequestHandlerClass(request, client_address, self, self._app)

    # def get_request(self):
    #     """ Keep client address as (address, port) tuple """
    #     data, client_addr = self.socket.recvfrom(self.max_packet_size)

    def send(self, osc_address, values = None, address = None, port = None):
        if values is None:
            message = self.build_osc(osc_address, [])
        else:
            message = self.build_osc(osc_address, values)

        if address is None and port is None:
            self.multicast(message)
        else:
            self.unicast(message, address, port)

    def multicast(self, message: bytes):
        self.socket.sendto(
            message, (self.__MULTICAST_GROUP__, self.__MULTICAST_PORT__)
        )

    def unicast(self, message, address, port):
        self.socket.sendto(message, (address, port))

    def handle(self):
        ThreadingOSCUDPServer.handle_request(self)


class VirtualMulticastPythonOSC(VirtualSocket, MulticastPythonOSC):

    """
    Simulate a random IP address to allow sending & of multicast messages on a single system

        VirtualSocket encodes / decodes each message into:
            message = {sender address = *address*, message = *actual message*}

            todo: also unicast
    """

    def __init__(self, app: OSCApp, recv_address, send_port):
        VirtualSocket.__init__(self)
        MulticastPythonOSC.__init__(self, app, recv_address, send_port)

    def get_request(self):
        """ Intercept & decode request, pass along """
        data, sender_address = self.socket.recvfrom(self.max_packet_size)

        if sender_address != self.real_address:
            return (data, self.socket), sender_address
        else:
            data, sender_address = self.decode(data)
            data = bytes(data.encode('utf-8')) # deal with JSON bytes() shenanigans
            if sender_address != self.address:
                return (data, self.socket), sender_address
            else:
                pass

    def build_osc(self, osc_address, values):
        message = MulticastPythonOSC.build_osc(osc_address, values)
        return self.encode(message)

    # def handle(self):
    #     try:
    #         ThreadingOSCUDPServer.handle_request(self)
    #     except TypeError:
    #         pass # todo: why is this here?
