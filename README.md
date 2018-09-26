# oop-python-osc
Object-oriented API for python-osc

### Features
- A more advanced re-implementation of the [python-osc](https://github.com/attwad/python-osc) address <-> callback dispatcher
- Allow OSC callbacks to refer to and/or modify object attributes
- Register methods (or functions) as OSC message callbacks with decorators
- DispatchingObject class: automatically map registered OSC callback methods to MethodDispatcher
- Automatic class- instance-level registering of OSC methods allows for high modularity through inheritance from and nesting of DispatchingObject instances. 
- [WIP] -- implement OSC containers as nested DispatchingObject instances
