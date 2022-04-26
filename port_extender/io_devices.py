#!/usr/bin/env python
# 20220314 jfm port_exapnder.py

# Python 2/3 compatibility imports
from __future__ import print_function

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
    """This is the base class for all supported io_extender hardware."""
    def __init__(self, bus_id=1, ic_type="mcp23017", bus_addr=0x20,
                 initialize=False, alr=False):
        """Must configure port hardwre. The mcp family must initialize the
        Data Direction Register (DDR) to set all ports as outputs. The pcf
        hardware has no DDR to control the port behavior. The pcf devices
        have a small current source that pulls the output high similar to
        a weak pullup on an open collector output. This interface only
        supports using the io extenders as outputs. Initialization needs
        only to be done once."""
        self.bus_id = bus_id
        self.bus = smbus.SMBus(bus_id)
        self.addr = bus_addr  # view by using command line "i2cdetect -y bus"
        self.alr = alr
        self.ic_type = ic_type

    def set_output(self, val):
        pass

class MCP23017(IO_Extender):
    '''The mcp23017 has 16 outputs that are capable of sinking or sourcing
    up to 25 mA each making it suitable to drive most relays regardless of
    whether the control logic is active high or active low.

    Power On initializion programs all GPIO port pins as inputs.
    If alr (Active Low Relay) is False then preset outputs to "1"
    If alr (Active Low Relay) is True then preset outputs to "0"
    After presetting the outputs program the GPIO pins for Bank A
    and Bank B to be outputs. This initializes the ports so that when
    the outputs are driven, they drive to the correct logic level.
    Note: writing a word of data (16 bits) addreses both bank A and bank B.'''

    def __init__(self, bus_id=1, bus_addr=0x20, initialize = False, alr = False):
        #super().__init__()
        self.bus_id = bus_id
        self.bus = smbus.SMBus(bus_id)
        self.addr = bus_addr  # view by using command line "i2cdetect -y bus"
        self.alr = alr
        self.ic_type = "mcp23017"
        self.bankA = 0x12  # reg address for port GPIOA
        self.bankB = 0x13  # reg address for port GPIOB

        # preset the outputs before programming the DDR
        if self.alr:                       # Low true logic
            default_output_state = 0xffff  # all ones turns stations off
        else:
            default_output_state = 0x0000  # all zeroes turns stations off
        try:
            self.bus.write_word_data(bus_addr, self.bankA, default_output_state)
        except Exception as e:
            print("PEX: io_devices: failed to write to the device 0x{:02X}".format(bus_addr))
            print(repr(e))


        #now program the devices direction control register so that all GPIO
        #pins are set to be oututs.
        a = 0x00              # reg address for IO Direction control port A
        b = 0x01              # reg address for IO Direction control port B
        self.bus.write_byte_data(bus_addr, a, 0x00)  # Bank A set as outputs
        self.bus.write_byte_data(bus_addr, b, 0x00)  # Bank B set as outputs

    def set_output(self, val):
        if self.alr:            # Low true logic
            val = ~val & 0xffff
        else:
            val = val & 0xffff

        print('PEX: MCP23017: setting output to 0x{:04X}'.format(val))
        #starting address for word write is same as bank A
        self.bus.write_word_data(self.addr, self.bankA, val)

class MCP2308(IO_Extender):
    '''The mcp2308 has 8 outputs that are capable of sinking or sourcing
    up to 25 mA each making it suitable to drive most relays regardless of
    whether the control logic is active high or active low.'''
    def __init__(self, bus_id=1, bus_addr=0x20, initialize = False, alr = False):
        super().__init__()
        self._bus = smbus.SMBus(self.bus_id)
        if initialize:
            #program DDR to all outputs and set outputs to low unless alr==True
            pass

    def set_output(self, val):
        if self.alr:            # Low true logic
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
        if self.alr:            # Low true logic
            val = ~val & 0xffff
        else:
            val = val & 0xffff
        print('PCF8575: setting output to 0x{:04X}'.format(val))

class PCF8574(IO_Extender):
    '''The PCF8574 has 8 outputs that are capable of sinking
    up to 15 mA each making it suitable to drive most relays.'''
    def __init__(self, bus_id=1, bus_addr=0x20, initialize = False, alr = False):
        super().__init__()
        self._bus = smbus.SMBus(self.bus_id)
        if initialize:
            #initialize outputs to high weakly driven
            pass

    def set_output(self, val):
        if self.alr:          # Low true logic
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
