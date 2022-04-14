#!/usr/bin/env python
# 20220314 jfm port_exapnder.py

# Python 2/3 compatibility imports
from __future__ import print_function
import gv  # Get access to SIP's settings, gv = global variables

# import smbus required to control the io expander hardware
SMBus_avail = True  # assume that the needed module is available
try:
    import smbus
except ModuleNotFoundError:
    try:
        import smbus2 as smbus
    except ModuleNotFoundError:
        SMBus_avail = False  # missing smbus module

class IO_Extender():
    '''This is the base class for all supported io_extender hardware.'''
    def __init__(self, bus_id=1, ic_type="mcp23017", bus_addr=0x20,
                 initialize=False, alr=False):
        '''Must configure port hardwre. The mcp family must initialize the
        Data Direction Register (DDR) to set all ports as outputs. The pcf
        hardware has no DDR to control the port behavior. The pcf devices
        have a small current source that pulls the output high similar to
        a weak pullup on an open collector output. This interface only
        supports using the io extenders as outputs. Initialization needs
        only to be done once.'''
        self._bus_id = bus_id
        self._ic_type = ic_type
        self._bus_addr = bus_addr
        self._alr = alr

    def set_output(self, val):
        pass

class MCP23017(IO_Extender):
    '''The mcp23017 has 16 outputs that are capable of sinking or sourcing
    up to 25 mA each making it suitable to drive most relays regardless of
    whether the control logic is active high or active low.'''
    def __init__(self, bus_id=1, bus_addr=0x20, initialize = False, alr = False):
        super().__init__()
        self._bus = smbus.SMBus(self._bus_id)
        if initialize:
            #program DDR to all outputs and set outputs to low unless alr==True
            pass

    def set_output(self, val):
        if gv.sd[u"alr"] == 0:
            val = ~val & 0xffff
        else:
            val = val & 0xffff
        print('MCP23017: setting output to 0x{:04X}'.format(val))

class MCP2308(IO_Extender):
    '''The mcp2308 has 8 outputs that are capable of sinking or sourcing
    up to 25 mA each making it suitable to drive most relays regardless of
    whether the control logic is active high or active low.'''
    def __init__(self, bus_id=1, bus_addr=0x20, initialize = False, alr = False):
        super().__init__()
        self._bus = smbus.SMBus(self._bus_id)
        if initialize:
            #program DDR to all outputs and set outputs to low unless alr==True
            pass

    def set_output(self, val):
        if gv.sd[u"alr"] == 0:
            val = ~val & 0xff
        else:
            val = val & 0xff
        print('MCP2308: setting output to 0x{:02X}'.format(val))

class PCF8575(IO_Extender):
    '''The PCF8575 has 16 outputs that are capable of sinking
    up to 15 mA each making it suitable to drive most relays.'''
    def __init__(self, bus_id=1, bus_addr=0x20, initialize = False, alr = False):
        super().__init__()
        if initialize:
            #initialize outputs to high weakly driven
            pass

    def set_output(self, val):
        if gv.sd[u"alr"] == 0:
            val = ~val & 0xffff
        else:
            val = val & 0xffff
        print('PCF8575: setting output to 0x{:04X}'.format(val))

class PCF8574(IO_Extender):
    '''The PCF8574 has 8 outputs that are capable of sinking
    up to 15 mA each making it suitable to drive most relays.'''
    def __init__(self, bus_id=1, bus_addr=0x20, initialize = False, alr = False):
        super().__init__()
        self._bus = smbus.SMBus(self._bus_id)
        if initialize:
            #initialize outputs to high weakly driven
            pass

    def set_output(self, val):
        if gv.sd[u"alr"] == 0:
            val = ~val & 0xff
        else:
            val = val & 0xff
        print('pcf8574: setting output to 0x{:02X}'.format(val))

def Devices(bus_id=1, ic_type="pcf8574", bus_addr=0x20,
            initialize=False, alr=False):
    '''This is a factory to create the interface to the io extender.'''
    if ic_type == "mcp23017":
        return(MCP23017(bus_id, bus_addr, initialize, alr))
    elif ic_type == "mcp2308":
        return (MCP2308(bus_id, bus_addr, initialize, alr))
    elif ic_type == "pcf8575":
        return (PCF8575(bus_id, bus_addr, initialize, alr))
    elif ic_type == "pcf8574":
        return (PCF8574(bus_id, bus_addr, initialize, alr))
    else:
        print(u"ERROR: PEX unsupported device type requested {}".format(ic_type))
