#!/usr/bin/env python
# 20220314 jfm port_extender.py

# Python 2/3 compatibility imports
from __future__ import print_function

# standard library imports
import math
import json
import copy
import platform

# local library imports
import gv  # Access to SIP global variables

# PEX module imports
from port_extender.io_devices import IO_Device, supported_devices, i2c_scan

# The smbus module is required to control io port hardware.
# If module is missing, only simulated devices are supported.
SMBus_avail = True
try:
    import smbus
except ModuleNotFoundError:
    try:
        import smbus2 as smbus
    except ModuleNotFoundError:
        SMBus_avail = False  # missing smbus module

# PEX disables the default SIP bit banged Shift Register interface.
if SMBus_avail:
    gv.use_gpio_pins = False


# Use installed RAM size to set the smbus value.
# This function only works for raspberry pi.
def get_smbus_default():
    if SMBus_avail and platform.machine() in ("armv6l", "armv7l"):  # machine is rpi
        ram_size = 0
        with open("/proc/meminfo", "r") as f:
            r = f.readline()  # every line has three fields
            while r:
                if "MemTotal" in r:
                    t, d, u = r.split()  # Title, Data, Units
                    ram_size = int(d)
                    if u == "kB":
                        ram_size *= 1024
                    break
                r = f.readline()
        if ram_size > 256 * 1024:  # All pi's with more than 256 kB RAM use smbus 1
            default_smbus = "1"
        else:
            default_smbus = "0"  # Early pi's with 26 pin connectors only have 256 kB RAM use smbus 0
    else:
        default_smbus = "SimulatedBus"
    return default_smbus


class PEX:

    def __init__(self):
        self.ports = []  # Runtime configured io-extender devices. Not saved in pex.json.
        self.pex_msg = ""
        self.num_SIP_stations = gv.sd[u"nst"]  # Needed to determine if SIP options change
        self.SIP_alr = gv.sd['alr']  # Needed to determine if SIP options change
        self.supported_devices = supported_devices()
        self.smbus_avail = SMBus_avail
        self.default_smbus = get_smbus_default()
        self.config_status = u"unconfigured"
        self.pex_c = self.load_config()  # Load config from data/pex.json
        self.edit_conf = copy.deepcopy(self.pex_c)  # Initialize the copy for editing.

    def create_device(self, bus_id="1", dev_addr=u"0x20", ic_type=u"mcp23017",
                      size=8, first=0, last=0, unused=0):
        return {u"bus_id": bus_id, u"dev_addr": dev_addr, u"ic_type": ic_type,
                u"size": size, u"first": first, u"last": last, u"unused": unused}

    def create_default_config(self):
        # This configuration dictionary is saved in pex.json.
        return {
            u"pex_status": u"enabled",  # enabled or disabled changed by PEX UI
            u"auto_configure": 1,
            u"demo_mode": 0,
            u"default_ic_type": u'mcp23017',  # Used by autoconfig and config editor
            u"num_PEX_stations": 0,
            u"dev_configs": [],  # List of manually configured io devices
        }

    def create_device_ports(self, conf):
        # Runtime configuration not saved in pex.json.
        """
        Create list of io devices. The configured order of the devices
        maps the SIP stations to actual hardware ports. The first device
        listed in the pex_conf['dev_configs'] maps the first slice of
        SIP stations to the io hardware.
        """
        ports = []
        for dev in conf[u"dev_configs"]:
            bus_id = dev[u"bus_id"]
            ic_type = dev[u"ic_type"]
            dev_addr = int(dev[u"dev_addr"], 16)
            port = IO_Device(bus_id, ic_type, dev_addr, gv.sd[u"alr"])
            ports.append(port)
        return ports

    # Read the saved pex config for this plugin from it's JSON file or create a default config
    def load_config(self):
        pex_config = {}
        try:
            with open(u"./data/pex_config.json", u"r") as f:
                pex_config = json.load(f)  # Read the pex_config from file
        except IOError:  # If file does not exist create file using defaults.
            print("PEX: No config file found. Creating default config file.")
            pex_config = self.create_default_config()
            self.save_config(pex_config)
        except json.decoder.JSONDecodeError:  # if file is broken create file using defaults
            print("PEX: JSON Error found reading config file. Creating default config file.")
            pex_config = self.create_default_config()
            self.save_config(pex_config)

        finally:  # Validate the config loaded from storage or from defaults.
            if not self.validate_config(pex_config):
                print("PEX: Error bad config file. Creating default config file.")
                pex_config = self.create_default_config()
                self.save_config(pex_config)

            if pex_config[u"pex_status"] == "disabled":
                return pex_config

            if pex_config[u"demo_mode"]:
                self.default_smbus = "SimulatedBus"

            if pex_config[u"auto_configure"]:
                pex_config[u"dev_configs"] = self.auto_config(pex_config)
                pex_config[u"num_PEX_stations"] = sum(dev[u"size"] for dev in pex_config[u"dev_configs"])
            else:  # Verify saved config
                if self.verify_hardware_config(pex_config):
                    pex_config[u"num_PEX_stations"] = sum(dev[u"size"] for dev in pex_config[u"dev_configs"])

            if pex_config[u"num_PEX_stations"] < gv.sd[u"nst"]:
                self.config_status = u"unconfigured"
                print(u"PEX: Not enough io extender ports configured.")
                self.pex_msg = u"PEX configuration Error. No Workee!."
            else:
                self.config_status = u"configured"
                self.ports = self.create_device_ports(pex_config)
                self.pex_msg = u"PEX running no errors."
        return pex_config

    # Save the pex config for this plugin to it's JSON file
    def save_config(self, pex_c):
        if self.validate_config(pex_c):
            if pex_c[u"auto_configure"]:
                pex_c[u"dev_configs"] = []
                self.config_status = "configured"
            elif self.verify_hardware_config(pex_c):
                self.config_status = "configured"
            else:
                self.config_status = "unconfigured"
        else:
            self.config_status = "unconfigured"
        with open(u"./data/pex_config.json", u"w") as f:  # write the settings to file
            json.dump(pex_c, f, indent=4)

    def auto_config(self, pex_c):
        """
        The required number of io extender devices must be present in the
        scan results to successfully create the SIP to PEX Port mapping.
        """

        smbus_id = self.default_smbus
        ic_type = pex_c[u"default_ic_type"]
        if ic_type in "pcf8574 mcp2308":
            port_span = 8
        else:  # "pcf8575 mcp23017"
            port_span = 16

        num_devs_needed = math.ceil(gv.sd[u"nst"] / port_span)
        discovered_devices = self.scan_for_ioextenders(pex_c)
        if num_devs_needed > len(discovered_devices):
            print("ERROR: PEX requires {} io extender devices: Detected = {}".format(num_devs_needed,
                                                                                     len(discovered_devices)))
            print("      PEX Autoconfigure  Device type: {}  Port span: {}".format(ic_type, port_span))
            print("ERROR: PEX Cannot auto configure due to lack of detected io extenders.")
            print("       PEX Must be configured and io extender devices must be detected.")
            return []  # no devices

        conf_d = []  # list of autoconfigured io extender devices
        for dev_id in range(num_devs_needed):  # In discovery order
            # create each device
            first = dev_id * port_span    # Map device span to SIP Station slice
            last = (dev_id + 1) * port_span   # Each port span is the same
            if last > gv.sd[u"nst"]:          # Unused ports are not used by SIP
                unused = last - gv.sd[u"nst"]
                last = gv.sd[u"nst"]
            else:
                unused = 0
            dev_addr = discovered_devices[dev_id]
            conf_d.append(self.create_device(bus_id=smbus_id, dev_addr=dev_addr, ic_type=ic_type,
                                             size=port_span, first=first, last=last, unused=unused))
        return conf_d

    def validate_config(self, conf):
        """Perform a self_consistency check of the configuration.
           Does not check validate the io device config."""
        valid = True

        # Validate that the config dictionary has the required keys
        def_keys = self.create_default_config().keys()
        for k in def_keys:  # Verify required fields are present in loaded conf
            if not k in conf:
                valid = False
                print('PEX: Bad config loaded from ./data/pex_config.json missing key {}'.format(k))
        for k in conf.keys():  # Warn if extra fields are present in loaded conf
            if not k in def_keys:
                print('PEX: Warning: Unused keys found in config loaded from ./data/pex_config.json conf["{}"]'.format(k))
        # TODO: Verify that conf dictionary values are of the proper type (e.g. int, str, etc.)
        return valid

    def verify_hardware_config(self, conf):
        if not len(conf[u"dev_configs"]):
            print("PEX: verify_hardware_config fails. No devices configured.")
            return False

        valid = True
        # Verify communication with each device.
        for i, dev in enumerate(conf[u"dev_configs"]):
            addr = int(dev[u"dev_addr"], 16)
            if not self.verify_device_handshake(dev[u"bus_id"], addr):
                valid = False
                print("PEX: verify_hardware_config: NO ACK from device:{} at addr: {:02x} ".format(i, addr))

        # Verify that the individual device configs agrees with the total.
        pex_span = sum([dev[u"size"] for dev in conf[u"dev_configs"]])
        if pex_span != conf[u"num_PEX_stations"]:
            valid = False
            print('PEX: Verify hardware config fails. Error in "size".')

        # Verify that this config satisfies the requirements of SIP config
        if gv.sd[u"nst"] > conf[u"num_PEX_stations"]:
            valid = False
            print("PEX: Validate hardware config fails. Not enough PEX stations configured.")
            print("PEX: SIP stations: {}   PEX stations: {}".format(gv.sd["nst"],
                                                                    conf[u"num_PEX_stations"]))
        # TODO: Verify that "first".."last" for each device agrees with "size" and offset position.
        return valid

    def scan_for_ioextenders(self, pex_c):
        'Scan well known bus address range for supported hardware port extenders.'
        bus_id = self.default_smbus
        i2c_start_addr = 0x20  # beginning i2c address for MCP230x and pcf857x
        i2c_end_addr = 0x27  # last possible i2c address for any MCP230x and pcf857x
        results = i2c_scan(bus_id, i2c_start_addr, i2c_end_addr)
        hex_results = [hex(i) for i in results]
        return hex_results

    def verify_device_handshake(self, bus_id, bus_addr):
        """Use SMbus ACK protocol for handshake to verify connectivity."""
        i2c_start_addr = bus_addr  # device to verify
        i2c_end_addr = bus_addr
        result = len(i2c_scan(bus_id, i2c_start_addr, i2c_end_addr)) != 0
        return result

    def set_output(self):
        '''Maps the SIP Station Values to the configured hardware port(s).
          The order that the devices are listed in the config are the order
          for mapping. The first device maps the first DeviceSize (8 or 16)
          ports to Station_1 through Station_N (N=8 or 16).'''

        #print("DEBUG: PEX set outputs for {} ports.".format(gv.sd[u"nst"]))

        for dev_id, dev in enumerate(self.pex_c[u"dev_configs"]):  # For each device set outputs to SIP values
            slice_for_dev = gv.srvals[dev[u"first"]:dev[u"last"]]
            res = 0
            for i,v in enumerate(slice_for_dev[::]):
                if v:
                    res |= 1 << i
            self.ports[dev_id].set_output(res)
            #print("DEBUG: PEX set_output to {:04X} for device {}".format(res, dev_id))
