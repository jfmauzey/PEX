#!/usr/bin/env python
# 20230318 jfm io_devices.py

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


class SimulatedBus:
    def __init__(self):
        pass

    def write_byte(self, addr, data):
        #print(f'SimBus write byte to addr 0x{addr:02x} with 0x{data:02x}')
        print('SimBus write byte to addr 0x{:02x} with 0x{:02x}'.format(addr, data))

    def write_byte_data(self, addr, register, data):
        #print(f'SimBus write byte to addr 0x{addr:02x} register 0x{register:02x} with 0x{data:02x}')
        print('SimBus write byte to addr 0x{:02x} register 0x{:02x} with 0x{:02x}'.format(addr, register, data))

    def write_word_data(self, addr, register, data):
        #print(f'SimBus write word to 0x{addr:02x} register 0x{register:02x} data 0x{data:04x}')
        print('SimBus write word to 0x{:02x} register 0x{:02x} data 0x{:04x}'.format(addr, register, data))

    def write_quick(self, addr):  # Every tested addr will succeed.
        #print(f'SimBus write quick to 0x{addr:02x}')
        print('SimBus write quick to 0x{:02x}'.format(addr))


class IO_Extender:
    """This is the base class for all supported io_extender hardware."""
    def __init__(self, bus_id="1", dev_addr=0x20, alr=False):
        """Must configure port hardware. The mcp family must initialize the
        Data Direction Register (DDR) to set all ports as outputs. The pcf
        hardware has no DDR to control the port behavior. The pcf devices
        have a small current source that pulls the output high similar to
        a weak pullup on an open collector output. This interface only
        supports using the io extenders as outputs. Initialization needs
        only to be done once."""
        if bus_id == 'SimulatedBus':
            self._bus = SimulatedBus()
        else:
            self._bus = smbus.SMBus(int(bus_id))

        self._dev_addr = dev_addr  # view by using command line "i2cdetect -y bus"
        self._alr = alr

    def set_output(self, val):
        print(u'ERROR: PEX: Base class should never be called.')
        pass


class MCP23017(IO_Extender):
    '''The mcp23017 has 16 outputs that are capable of sinking or sourcing
    up to 25 mA each making it suitable to drive most relays regardless of
    whether the control logic is active high or active low.

    Power On initialization defaults all GPIO port pins as inputs.
    If alr (Active Low Relay) is False then preset outputs to "0"
    If alr (Active Low Relay) is True then preset outputs to "1"
    After presetting the outputs, program the GPIO pins for Bank A
    and Bank B to be outputs. This initializes the ports so that when
    the outputs are driven, they drive to the correct logic level.
    This insures that all outputs are preset to turn off the attached stations.'''

    def __init__(self, bus_id="1", dev_addr=0x20, alr=False):
        super().__init__(bus_id, dev_addr, alr)
        self._bankA = 0x12  # reg address for port GPIOA
        self._bankB = 0x13  # reg address for port GPIOB

        # preset the outputs before programming the DDR
        if self._alr:                       # Low true logic
            default_output_state = 0xffff  # all ones turns stations off
        else:
            default_output_state = 0x0000  # all zeroes turns stations off
        try:
            self._bus.write_word_data(dev_addr, self._bankA, default_output_state)
        except Exception as e:
            print("PEX: MCP23017: failed to write to the device 0x{:02X}".format(self._dev_addr))
            print(repr(e))

        # now program the device's direction control register so that all GPIO
        # pins are set to be outputs.
        a = 0x00              # reg address for IO Direction control port A
        b = 0x01              # reg address for IO Direction control port B
        self._bus.write_byte_data(dev_addr, a, 0x00)  # Bank A set as outputs
        self._bus.write_byte_data(dev_addr, b, 0x00)  # Bank B set as outputs

    def set_output(self, val):
        if self._alr:            # Low true logic
            val = ~val & 0xffff
        else:
            val = val & 0xffff
        print('DEBUG: PEX: MCP23017: set output port: 0x{:02X} to 0x{:04X}'.format(self._dev_addr, val))
        # starting address for word write is same as bank A
        self._bus.write_word_data(self._dev_addr, self._bankA, val)


class MCP2308(IO_Extender):
    '''The mcp2308 has 8 outputs that are capable of sinking or sourcing
    up to 25 mA each making it suitable to drive most relays regardless of
    whether the control logic is active high or active low.
    Power On initialization defaults all GPIO port pins as inputs.
    If alr (Active Low Relay) is False then preset outputs to "0"
    If alr (Active Low Relay) is True then preset outputs to "1"
    After presetting the outputs, program the GPIO pins to be outputs.
    This initializes the port so that when the outputs are driven, they
    drive to the correct logic level. This insures that all outputs are
    preset to turn off the attached stations.'''

    def __init__(self, bus_id="1", dev_addr=0x20, alr=False):
        super().__init__(bus_id, dev_addr, alr)
        self._port = 0x09  # reg address for port

        # preset the outputs before programming the DDR
        if self._alr:                       # Low true logic
            default_output_state = 0xff  # all ones turns stations off
        else:
            default_output_state = 0x00  # all zeroes turns stations off
        try:
            self._bus.write_byte_data(dev_addr, self._port, default_output_state)
        except Exception as e:
            print("PEX: MCP2308: failed to write to the device 0x{:02X}".format(self._dev_addr))
            print(repr(e))

        # now program the device's direction control register so that all GPIO
        # pins are set to be outputs.
        iodir = 0x00          # reg address for IO Direction control register
        self._bus.write_byte_data(dev_addr, iodir, 0x00)  # All pins set as outputs
        pass

    def set_output(self, val):
        if self._alr:            # Low true logic
            val = ~val & 0xff
        else:
            val = val & 0xff
        #print('DEBUG: PEX: MCP2308: set output port: 0x{:02X} to 0x{:02X}'.format(self._dev_addr, val))
        self._bus.write_byte_data(self._dev_addr, self._port, val)


class PCF8575(IO_Extender):
    '''The PCF8575 has 16 outputs that are capable of sinking
    up to 15 mA each making it suitable to drive most relays.
    All data writes occur in pairs. The first write sets the
    lower byte and the second write sets the upper byte.'''
    def __init__(self, bus_id=1, dev_addr=0x20, alr=False):
        super().__init__(bus_id, dev_addr, alr)

        # Initialize outputs to turn stations off
        if self._alr:  # Low true logic
            default_output_state = 0xffff  # all ones turns stations off
        else:
            default_output_state = 0x0000  # all zeroes turns stations off
        val1 = (default_output_state & 0xff)         # Lower byte
        val2 = (default_output_state & 0xff00) >> 8  # Upper byte
        try:
            self._bus.write_byte(dev_addr, val1)
            self._bus.write_byte(dev_addr, val2)
        except Exception as e:
            print("PEX: PCF8575: failed to write to the device 0x{:02X}".format(self._dev_addr))
            print(repr(e))

    def set_output(self, val):
        if self._alr:            # Low true logic
            val = ~val & 0xffff
        else:
            val = val & 0xffff
        val1 = (val & 0xff)         # Lower byte
        val2 = (val & 0xff00) >> 8  # Upper byte
        #print('DEBUG: PEX: PCF8575: set output port: 0x{:02X} to 0x{:04X}'.format(self._dev_addr, val))
        self._bus.write_byte(self._dev_addr, val1)  # Write first 8 bits P7..P0
        self._bus.write_byte(self._dev_addr, val2)  # Write second 8 bits P17..P10


class PCF8574(IO_Extender):
    '''The PCF8574 has 8 outputs that are capable of sinking
    up to 15 mA each making it suitable to drive most relays.'''
    def __init__(self, bus_id=1, dev_addr=0x20, alr=False):
        super().__init__(bus_id, dev_addr, alr)

        # Initialize outputs to turn stations off
        if self._alr:  # Low true logic
            default_output_state = 0xff  # all ones turns stations off
        else:
            default_output_state = 0x00  # all zeroes turns stations off
        try:
            self._bus.write_byte(dev_addr, default_output_state)
        except Exception as e:
            print("PEX: PCF8574: failed to write to the device 0x{:02X}".format(self._dev_addr))
            print(repr(e))

    def set_output(self, val):
        if self._alr:          # Low true logic
            val = ~val & 0xff
        else:
            val = val & 0xff
        #print('DEBUG: PEX: PCF8574: set output port: 0x{:02X} to 0x{:02X}'.format(self._dev_addr, val))
        self._bus.write_byte(self._dev_addr, val)


def IO_Device(bus_id=1, ic_type="pcf8574", dev_addr=0x20, alr=False):
    '''This is a factory to create the device interface for the io extender.'''
    if ic_type == "mcp23017":
        return MCP23017(bus_id, dev_addr, alr)
    elif ic_type == "mcp2308":
        return MCP2308(bus_id, dev_addr, alr)
    elif ic_type == "pcf8575":
        return PCF8575(bus_id, dev_addr, alr)
    elif ic_type == "pcf8574":
        return PCF8574(bus_id, dev_addr, alr)
    else:
        print(u"ERROR: PEX unsupported device type requested {}".format(ic_type))


def supported_devices():
   return ("mcp23017","mcp2308","pcf8575", "pcf8574")


# smbus tool
def i2c_scan(i2c_bus_id, start_addr=0x08, end_addr=0xF7):
    devices_discovered = []
    if i2c_bus_id == "SimulatedBus":
        bus = SimulatedBus()
    else:
        bus = smbus.SMBus(int(i2c_bus_id))
    for i in range(start_addr, end_addr+1):
        try:
            bus.write_quick(i)
            devices_discovered.append(i)
        except OSError as e:
            pass  # no device responded
    return devices_discovered  # list of addresses from successful handshake ACK

