#!/usr/bin/env python
# 20220314 jfm port_extender.py

# Python 2/3 compatibility imports
from __future__ import print_function

# standard library imports
import json

import gv  # Get access to SIP's settings, gv = global variables
from .io_devices import Devices

# import smbus required to control the io port hardware
blockedPlugin = False # assume that the needed module is available
try:
    import smbus
except ModuleNotFoundError:
    try:
        import smbus2 as smbus
    except ModuleNotFoundError:
        blockedPlugin = True  # missing smbus module

# smbus tool
def i2c_scan(i2c_bus, start_addr = 0x08, end_addr = 0xF7):
    devices_discovered = []
    for i in range(start_addr, end_addr+1):
        try:
            i2c_bus.write_quick(i)
            devices_discovered.append(i)
        except OSError as e:
            pass  # no device responded
    return devices_discovered  # list of addresses from successful handshake ACK


class PEX():

    def __init__(self):
        try:
            self._number_of_stations = len(gv.srvals)
            self.pex_c = self.load_pex_config()
            self._dev_configs = self.pex_c['dev_configs']  # list of preconfigured device(s)
            self._discovered_devices = []
            self._debug = self.pex_c['debug']
        except (TypeError, KeyError) as e:
            print(u'ERROR: PEX bad or missing hardware config')
            print(u'       PEX will create default config')
            print(e)
            self.pex_c = self.create_default_config()
            self._dev_configs = self.pex_c[u"dev_configs"]
            self._discovered_devices = []
            self._debug = True

    def create_default_device(self, bus_id=1, hw_addr=0x24, size=8, first=0, last=0):
        dev_conf = {}
        dev_conf[u"bus_id"] = bus_id
        dev_conf[u"hw_addr"] = hw_addr
        dev_conf[u"ic_type"] = "pcf8574"
        dev_conf[u"size"] = size
        dev_conf[u"first"] = first
        dev_conf[u"last"] = last
        return dev_conf

    def create_default_config(self):
        pex_conf = {}
        pex_conf[u"pex_status"] = u"unconfigured"
        pex_conf[u"warnmsg"] = ''
        pex_conf[u"dev_configs"] = [self.create_default_device()]
        pex_conf[u"discovered_devices"] = []
        pex_conf[u"num_configured_SIP_stations"] = 0
        pex_conf[u"default_smbus"] = 1
        pex_conf[u"supported_hardware"] = [u'pcf8574', u'pcf8575', u'mcp2308', u'mcp23017']
        pex_conf[u"ic_type"] = u'pcf8575'
        pex_conf[u"debug"] = "0"
        return pex_conf

    # Read in the pex config for this plugin from it's JSON file
    def load_pex_config(self):
        try:
            with open(u"./data/pex_config.json", u"r") as f:
                pex_config = json.load(f)  # Read the pex_config from file
        except IOError:  # If file does not exist or is broken create file with defaults.
            pex_config = self.create_default_config()
            self.save_pex_config(pex_config)
        return pex_config

    # Save the pex config for this plugin to it's JSON file
    def save_pex_config(self, pex_c):
        # jfm HERE
        # need to validate config before saving
        with open(u"./data/pex_config.json", u"w") as f:  # write the settings to file
            json.dump(pex_c, f, indent=4)

    def scan_for_ioextenders(self, bus_id):
        'Scan well known bus address range for supported hardware port extenders.'
        i2c_bus = smbus.SMBus(int(bus_id))
        i2c_start_addr = 0x20  # beginning i2c address for MCP23017 and pcf857x
        i2c_end_addr = 0x27  # last possible i2c address for MCP23017 and pcf857x
        self._discovered_devices = i2c_scan(i2c_bus, i2c_start_addr, i2c_end_addr)
        return self._discovered_devices


    def verify_device_handshake(self, bus_id, bus_addr: int):  # jfm static typing
        'Use SMbus ACK protocol for handshake to verify connectivity.'
        i2c_bus = smbus.SMBus(int(bus_id))
        i2c_start_addr = bus_addr  #  device to verify
        i2c_end_addr = bus_addr
        return (i2c_scan(i2c_bus, i2c_start_addr, i2c_end_addr))

    def alter_SIP_gpio_behavior(self):
        'Disable SIP gpio shift register if Port Extender is configured to use smbus.'
        if len(self._dev_configs):  # at least one interface board is configured
            # disable gpio_pins. We can discuss later if a mix of gpio and i2c should be possible
            gv.use_gpio_pins = False
        else:
            gv.use_gpio_pins = True

    def has_config_changed(self, conf):
        return self._dev_configs != conf['dev_configs'] or \
               self._number_of_stations != len(gv.srvals)

    def set_output(self, conf):
        'Maps the SIP Station Values to the configured hardware port(s).'
        if self.has_config_changed(conf):
            print(u"ERROR: PEX configuration changed. Need to reconfigure.")
            return
        elif self.pex_c['pex_status'] != "run":
            print(u'ERROR: PEX not in "run" mode. Need to reconfigure.')
            return

        # now use srvalues to set values of configured ports
        print("DeBug: PEX set outputs for {} ports.".format(len(gv.srvals)))
        # Map the srvalues to the device(s). The order that the devices are
        # listed in the config are the order for mapping. The first device
        # maps the first DeviceSize (8 or 16) ports to Station_1 through
        # Station_N (n=8 or 16).
        st = 0  # start index in successive slices
        sr_len = len(gv.srvals)
        device_count = 0  # jfm for debug track which device is selected
        for dev in self._dev_configs:
            device_count += 1
            port_size = dev[u"size"]
            hw_addr = dev["hw_addr"]
            bus_id = dev[u"bus_id"]
            ic_type = dev[u"ic_type"]
            result = 0
            n = 1
            stp = min(st + port_size, sr_len)  # last element in slice
            for i in range(st, stp):
                if gv.srvals[i] == 1:
                    result += n
                n *= 2  # arithmetic shift left one bit
            st = st + port_size  # ready for next slice
            if st > sr_len:
                print(f'Debug: PEX dev@0x{hw_addr:02X} has {st-sr_len} unused ports.')
                break
            port = Devices(bus_id, ic_type, hw_addr, alr=False)
            port.set_output(result)
            print("Debug: PEX set_output to {:04X} for device {}".format(result,device_count))
        if st < sr_len:  # ran out of devices to map before last srvals have been output
            print(u"ERROR: PEX too many Stations configured for configured io_extender hardware.")
            print(u"           Either reduce number of stations are add/configure additional")
            print(u"           io_extender hardware.")

