#!/usr/bin/env python
# 20220314 jfm port_extender.py

# Python 2/3 compatibility imports
from __future__ import print_function

# standard library imports
import math
import json
import platform

# local library imports
import gv  # Access to SIP global variables

# PEX module imports
from port_extender.io_devices import IO_Device, i2c_scan

# The smbus module is required to control io port hardware.
# If module is missing, only simulated devices are supported.
SMBus_avail = True  # assume that the needed module is available
try:
    import smbus
except ModuleNotFoundError:
    try:
        import smbus2 as smbus
    except ModuleNotFoundError:
        SMBus_avail = False  # missing smbus module


# Use installed RAM size to determine which smbus to use.
def get_smbus_default():
    # This function only works for raspberry pi.
    if platform.machine() in ("armv6l", "armv7l"):  # machine is Raspberry pi
        ram_size = 0
        with open("/proc/meminfo", "r") as f:  # Privileged file open
            r = f.readline()  # every line has three fields
            while r:
                try:
                    if "MemTotal" in r:
                        t, d, u = r.split()  # Title, Data, Units
                        ram_size = int(d)
                        if u == "kB":
                            ram_size *= 1024
                        else:
                            print("ERROR: configuring SMBus ID. Unknown platform.")
                        break
                except ValueError:
                    pass
                r = f.readline()
        if ram_size > 256 * 1024:  # All pi's with more than 256 kB RAM use smbus 1
            default_smbus = "1"
        else:
            default_smbus = "0"  # Early pi's with 26 pin connectors only have 256 kB RAM use smbus 0
    else:
        default_smbus = "SimulatedBus"

    if not SMBus_avail:
        default_smbus = "SimulatedBus"
    return default_smbus


class PEX:

    def __init__(self):
        self.ports = []  # list of io-extender devices
        self.pex_c = self.load_config()
        self.warn_msg = ""
        self._debug = self.pex_c['debug']
        self.set_SIP_gpio_behavior()

    def create_device(self, bus_id="1", dev_addr=u"0x20", ic_type=u"pcf8574",
                      size=8, first=0, last=0, unused=0):
        """Creates device configuration using default parameters if none are specified."""
        return {u"bus_id": bus_id, u"dev_addr": dev_addr, u"ic_type": ic_type,
                u"size": size, u"first": first, u"last": last, u"unused": unused}

    def create_default_config(self):
        pex_conf = {
            u"debug": "0",
            u"pex_status": u"disabled",  # enabled or disabled changed by PEX UI
            u"config_status": u"unconfigured",
            u"auto_configure": 0,
            u"demo_mode": 0,
            u"default_smbus": get_smbus_default(),
            u"SMBus_avail": SMBus_avail,
            u"default_ic_type": u'mcp23017',  # Used by autoconfig
            u"warnmsg": '',
            u"SIP_alr": gv.sd['alr'],
            u"num_SIP_stations": gv.sd[u"nst"],  # Needed to determine if SIP options change
            u"num_PEX_stations": 0,
            u"supported_hardware": [u'pcf8574', u'pcf8575', u'mcp2308', u'mcp23017'],
            u"dev_configs": [],  # List of installed io device extenders
            u"discovered_devices": [],
        }
        return pex_conf

    def create_device_ports(self, conf):
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
        except json.decoder.JSONDecodeError:  # if file is broken create file using defaults
            print("PEX: JSON Error reading config file found. Creating default config file.")
            pex_config = self.create_default_config()

        finally:  # Validate the config loaded from storage or from defaults.
            if not self.validate_config(pex_config):
                print("PEX: Error bad config file. Creating default config file.")
                pex_config = self.create_default_config()
            if pex_config[u"auto_configure"]:
                pex_config[u"dev_configs"] = self.autogenerate_device_config(pex_config)
                pex_config[u"num_PEX_stations"] = sum(dev[u"size"] for dev in pex_config[u"dev_configs"])
            if pex_config[u"num_PEX_stations"] >= gv.sd[u"nst"]:
                pex_config[u"config_status"] = u"configured"
            else:
                pex_config[u"config_status"] = u"unconfigured"
            if self.verify_hardware_config(pex_config):
                pex_config[u"num_PEX_stations"] = sum([dev[u"size"] for dev in pex_config[u"dev_configs"]])
                if pex_config[u"num_PEX_stations"] >= gv.sd[u"nst"]:
                    pex_config[u"config_status"] = u"configured"
                else:
                    pex_config[u"config_status"] = u"unconfigured"
            else:
                pex_config[u"config_status"] = u"unconfigured"
        self.ports = self.create_device_ports(pex_config)

        self.save_config(pex_config)
        return pex_config

    # Save the pex config for this plugin to it's JSON file
    def save_config(self, pex_c):
        # need to validate config before saving
        if not (self.validate_config(pex_c) and self.verify_hardware_config(pex_c)):
            pex_c[u"config_status"] = "unconfigured"
        with open(u"./data/pex_config.json", u"w") as f:  # write the settings to file
            json.dump(pex_c, f, indent=4)

    def autogenerate_device_config(self, pex_c):
        """
        The required number of io extender devices must be present in the
        scan results to successfully create the SIP to Port mapping.
         """

        smbus_id = pex_c[u"default_smbus"]
        ic_type = pex_c[u"default_ic_type"]
        if ic_type in "pcf8574 mcp2308":
                port_span = 8
        else:
            port_span = 16

        num_devs_needed = math.ceil(gv.sd[u"nst"] / port_span)
        discovered_devices = self.scan_for_ioextenders(pex_c, num_devs_needed)
        pex_c[u"discovered_devices"] = discovered_devices  # Saved for PEX-UI
        if num_devs_needed > len(discovered_devices):
            print("ERROR: PEX requires {} io extender devices: Detected = {}".format(num_devs_needed,
                                                                                     len(discovered_devices)))
            print(f"      PEX Autoconfigure  Device type: {ic_type}  Port span: {port_span}")
            print("ERROR: PEX Cannot auto configure due to lack of detected io extenders.")
            print("       PEX Must be configured and io extender devices must be detected.")
            return []  # no devices

        conf_d = []  # list of autoconfigured io extender devices
        for dev_id in range(num_devs_needed):  # In discovery order
            # create each device
            first = dev_id * port_span        # Map device span to SIP Station slice
            last = (dev_id + 1) * port_span   # Only works when port_span is constant
            if last > gv.sd[u"nst"]:  # Unused ports are not used by SIP
                unused = last - gv.sd[u"nst"]
                last = last - gv.sd[u"nst"]
            else:
                unused = 0
            dev_addr = hex(discovered_devices[dev_id])
            conf_d.append(self.create_device(bus_id=smbus_id, dev_addr=dev_addr, ic_type=ic_type,
                                             size=port_span, first=first, last=last, unused=unused))

        return conf_d

    def validate_config(self, conf):
        """Perform a self_consistency check of the inter-related entries in the configuration."""
        valid = True

        # Validate that the config dictionary has the required keys
        for k in self.create_default_config().keys():
            if not k in conf:
                valid = False
                print('PEX: Bad config loaded from ./data/pex_config.json missing key {}'.format(k))
        # TODO: Verify that conf dictionary values are of the proper type (e.g. int, str, etc.)
        return valid

    def verify_hardware_config(self, conf):
        if not len(conf[u"dev_configs"]):
            print("PEX: verify_hardware_config fails. No devices configured.")
            return False

        valid = True
        for i, dev in enumerate(conf[u"dev_configs"]):
            addr = int(dev[u"dev_addr"], 16)
            if not self.verify_device_handshake(dev[u"bus_id"], addr):
                valid = False
                print("PEX: verify_hardware_config -- device number {} no ACK handshake".format(i))

        # Verify that the individual device configs agrees with the total.
        pex_span = sum([dev[u"size"] for dev in conf[u"dev_configs"]])
        if pex_span != conf[u"num_PEX_stations"]:
            valid = False
            print("PEX: Verify hardware config fails. Not enough PEX io extenders configured.")

        # Verify that this config satisfies the requirements of SIP config
        if gv.sd[u"nst"] > conf[u"num_PEX_stations"]:
            valid = False
            print("PEX: Validate hardware config fails. Not enough PEX stations configured.")
            print("PEX: SIP stations: {}   PEX stations: {}".format(gv.sd["nst"],
                                                                    conf[u"num_PEX_stations"]))
        return valid

    def scan_for_ioextenders(self, pex_c, num_devs_needed):
        'Scan well known bus address range for supported hardware port extenders.'
        bus_id = pex_c[u"default_smbus"]
        i2c_start_addr = 0x20  # beginning i2c address for MCP230x and pcf857x
        if pex_c[u"demo_mode"]:
            i2c_end_addr = i2c_start_addr + num_devs_needed
            pex_c[u"default_smbus"] = "SimulatedBus"
        else:
            i2c_end_addr = 0x27  # last possible i2c address any MCP230x and pcf857x
        return i2c_scan(bus_id, i2c_start_addr, i2c_end_addr)

    def verify_device_handshake(self, bus_id, bus_addr):
        """Use SMbus ACK protocol for handshake to verify connectivity."""
        i2c_start_addr = bus_addr  # device to verify
        i2c_end_addr = bus_addr
        result = len(i2c_scan(bus_id, i2c_start_addr, i2c_end_addr)) != 0
        return result

    def set_SIP_gpio_behavior(self):
        """Disable SIP gpio shift register if Port Extender is configured to use smbus."""
        if self.pex_c[u"pex_status"] == u"enabled":
            gv.use_gpio_pins = True
        else:
            gv.use_gpio_pins = False

    def set_output(self):
        '''Maps the SIP Station Values to the configured hardware port(s).
          The order that the devices are listed in the config are the order
          for mapping. The first device maps the first DeviceSize (8 or 16)
          ports to Station_1 through Station_N (N=8 or 16).'''

        if self.pex_c[u"pex_status"] != "enabled":
            print(u'ERROR: PEX not enabled. Need to reconfigure.')
            print(u'       Updating port outputs is disabled.')
            return

        print("DeBug: PEX set outputs for {} ports.".format(gv.sd[u"nst"]))

        for dev_id, dev in enumerate(self.pex_c[u"dev_configs"]):  # For each device set outputs to SIP values
            slice_for_dev = gv.srvals[dev[u"first"]:dev[u"last"]]
            res = 0
            for i,v in enumerate(slice_for_dev[::]):
                if v:
                    res |= 1 << i
            self.ports[dev_id].set_output(res)
            print("Debug: PEX set_output to {:04X} for device {}".format(res, dev_id))
