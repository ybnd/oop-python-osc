import asyncio
import threading
import collections

def dispatchOSC(cls):
    """ Register a class-level method dispatching class """
    cls._class_handlers = {}
    cls._class_handlers[cls.__name__] = {}

    for methodname in dir(cls):
        method = getattr(cls, methodname)
        if hasattr(method, '_registered'):
            # cls._OSC_handler_registry[cls.__name__].update(
            #     {method._address: method}
            # )
            if method._owning_class not in cls._class_handlers:
                cls._class_handlers.update(
                    {method._owning_class: {}}
                )
            if method._address[0] != "/":
                method._address = "/" + method._address

            cls._class_handlers[method._owning_class].update(
                {method._address: method}
            )

    return cls

def handleOSC(**kwargs): #
        # todo: it would be better to actually define some 'static' kwargs...
            # i.e.: alias, pass_address, ...

    """ Register a method as an OSC handler

             Usage: @handleOSC()
                    @handleOSC(address = 'alias')
                    @handleOSC(kwarg1 = 1, kwarg2 = 'a', ...) -> constant keyword arguments ~ pythonosc (use case??)
     # todo address must be provided as kwarg, otherwise something happens to the method's reference
    """
    def wrapper(func):
        if 'alias' in kwargs:
            func._address = kwargs['alias']
            del kwargs['alias']
        else:
            func._address = "/" + func.__name__

        if 'pass_address' in kwargs:
            func._pass_address = kwargs['pass_address']
            del kwargs['pass_address']
        else:
            func._pass_address = False

        if 'priority' in kwargs:
            func._priority = kwargs['priority']
            del kwargs['priority']

        func._kwargs = kwargs
        func._registered = True  # todo: less generic name than _registered
        func._owning_class = func.__qualname__.split('.')[0]

        return func
    return wrapper

MethodHandler = collections.namedtuple(
    typename = 'MethodHanler', 
    field_names = ('callback', 'instance', 'args')
)

@dispatchOSC
class DynamicRegistrar:
    """ Instance-level method registering class

            Intercepts all instance attributes: if an instance attribute (value) is registered as an OSC dispatcher,
            add update self._handler_registry with value._handler_registry

            Subclass DispatchingObject to define dynamic OSC containers.
    """

    def __init__(self):
        self._instance_handlers = {}
        self._instance_handlers[self.__class__.__name__] = {}
        """ Add self reference to handlers registered at the class level! """
        for implementation in self._class_handlers:
            for method in self._class_handlers[implementation]:
                if not isinstance(self._class_handlers[implementation][method], tuple):
                    if implementation not in self._instance_handlers.keys():
                        self._instance_handlers[implementation] = {}
                    self._instance_handlers[implementation][method] = (
                        (self._class_handlers[implementation][method], self)
                    )

    def __setattr__(self, key, value):
        if hasattr(value, '_instance_handlers'):
            # Already registered as (method, instance)
            for implementation in value._instance_handlers.keys():
                    for address in value._instance_handlers[implementation]:
                        reference = value._instance_handlers[implementation][address]
                        self._instance_handlers[self.__class__.__name__].update(
                            {"/" + key + address: reference}
                        )
        elif hasattr(value, '_class_handlers'):
            # Need to register (method, instance)
            for implementation in value._class_handlers.keys():
                for address in value._class_handlers[implementation]:
                    method = value._class_handlers[implementation][address]
                    self._instance_handlers[self.__class__.__name__].update(
                        {"/" + key + address: (method, value)}
                    )

        super(DynamicRegistrar, self).__setattr__(key, value)