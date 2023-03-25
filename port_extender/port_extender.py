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

    def create_device(self, bus_id="1", hw_addr=u"0x20", ic_type=u"pcf8574",
                      size=8, first=0, last=0):
        """Creates device using default parameters if none are specified."""
        return {u"bus_id": bus_id, u"hw_addr": hw_addr, u"ic_type": ic_type,
                u"size": size, u"first": first, u"last": last}

    def create_default_config(self):
        pex_conf = {}
        pex_conf[u"debug"] = "0"
        pex_conf[u"pex_status"] = u"disabled"  # enabled or disabled changed by PEX UI
        pex_conf[u"config_status"] = u"unconfigured"
        pex_conf[u"auto_configure"] = 0
        pex_conf[u"default_smbus"] = get_smbus_default()
        pex_conf[u"warnmsg"] = ''
        pex_conf[u"num_SIP_stations"] = gv.sd["nst"]
        pex_conf[u"SIP_alr"] = gv.sd['alr']
        pex_conf[u"num_PEX_stations"] = 0
        pex_conf[u"supported_hardware"] = [u'pcf8574', u'pcf8575', u'mcp2308', u'mcp23017']
        pex_conf[u"dev_configs"] = []  # List of installed io device extenders
        pex_conf[u"discovered_devices"] = []
        pex_conf[u"default_ic_type"] = u'mcp23017'  # Used by autoconfig
        pex_conf[u"ic_type"] = u'mcp23017'
        return pex_conf

    def create_device_ports(self, conf):
        """
        Create list of io devices. The configured order of the devices
        maps the SIP stations to actual hardware ports. The first device
        listed in the pex_conf['dev_configs'] maps the first slice of
        SIP stations to the io hardware.
        """
        ports = []
        for i in range(len(conf[u"dev_configs"])):
            bus_id = conf[u"dev_configs"][i][u"bus_id"]
            ic_type = conf[u"dev_configs"][i][u"ic_type"]
            hw_addr = int(conf[u"dev_configs"][i][u"hw_addr"], 16)
            port = IO_Device(bus_id, ic_type, hw_addr, gv.sd[u"alr"])
            ports.append(port)
        return ports

    # Read in the pex config for this plugin from it's JSON file or create a default config
    def load_config(self):
        try:
            with open(u"./data/pex_config.json", u"r") as f:
                pex_config = json.load(f)  # Read the pex_config from file
        except IOError:  # If file does not exist or is broken create file with defaults.
            pex_config = self.create_default_config()
            pex_config[u"dev_configs"] = self.autogenerate_device_config(
                pex_config[u"default_ic_type"], pex_config[u"default_smbus"])
            pex_config[u"num_PEX_stations"] = sum([dev[u"size"] for dev in pex_config[u"dev_configs"]])
            if pex_config[u"num_PEX_stations"] >= gv.sd["nst"]:
                pex_config[u"config_status"] = u"configured"
            else:
                pex_config[u"config_status"] = u"unconfigured"
            self.save_config(pex_config)

        else:  # HERE validate config
            if not (self.sanity_check_config(pex_config) and self.verify_hardware_config(pex_config)):
                if pex_config[u"auto_configure"]:
                    pex_config[u"dev_configs"] = self.autogenerate_device_config(pex_config[u"default_ic_type"],
                                                                                 pex_config[u"default_smbus"])
                    # update PEX config status and number_configured_pex_ports
                    pex_config[u"num_SIP_stations"] = gv.sd[u"nst"]
                    pex_config[u"num_PEX_stations"] = sum([dev[u"size"] for dev in pex_config[u"dev_configs"]])
                    if pex_config[u"num_PEX_stations"] >= pex_config[u"num_SIP_stations"]:
                        pex_config[u"config_status"] = u"configured"
                    else:
                        pex_config[u"config_status"] = u"unconfigured"
                else:
                    pex_config[u"config_status"] = u"unconfigured"
                    pex_config[u"num_SIP_stations"] = gv.sd[u"nst"]
                    pex_config[u"num_PEX_stations"] = 0
                    pex_config[u"dev_configs"] = []
                self.save_config(pex_config)
        pex_config[u"SIP_alr"] = gv.sd['alr']
        self.ports = self.create_device_ports(pex_config)

        return pex_config

    # Save the pex config for this plugin to it's JSON file
    def save_config(self, pex_c):
        # need to validate config before saving
        if not (self.sanity_check_config(pex_c) and self.verify_hardware_config(pex_c)):
            pex_c[u"config_status"] = "unconfigured"
            print("PEX: Attempt to save bad config to json file.")
            print("PEX:   Config data not saved to json file. Must configure first.")
        pex_c[u"SIP_alr"] = gv.sd['alr']  # can be changed by SIP option 'alr'
        with open(u"./data/pex_config.json", u"w") as f:  # write the settings to file
            json.dump(pex_c, f, indent=4)

    def autogenerate_device_config(self, ic_type, smbus_id):
        """
        The required number of io extender devices must be present in the
        scan results to successfully create the SIP to Port mapping.
         """
        discovered_devices = self.scan_for_ioextenders(smbus_id)

        if ic_type == u"pcf8574" or ic_type == u"mcp2308":
            port_span = 8
        else:
            port_span = 16

        srlen = gv.sd[u"nst"]
        num_devs_needed = math.ceil(srlen / port_span)
        if num_devs_needed > len(discovered_devices):
            print("ERROR: PEX cannot auto configure due to lack of detected io extenders.")
            print("       PEX requires {} io extender devices: Detected = {}".format(num_devs_needed,
                                                                                     len(discovered_devices)))
            print("       PEX must be configured and io extender devices must be detected.")
            return []  # no devices could use simulated devices

        conf_d = []  # list of autoconfigured io extender devices
        for port_id in range(num_devs_needed):  # port_id is zero based index for device mapping
            # create each device
            first = port_id * port_span    # Map span to SIP Station index -- One-based
            last = (port_id + 1) * port_span   # Only true when port_span is constant
            hw_addr = hex(discovered_devices[port_id])  # In discovered order
            conf_d.append(self.create_device(bus_id=smbus_id, hw_addr=hw_addr, ic_type=ic_type,
                                             size=port_span, first=first, last=last))

        return conf_d

    def sanity_check_config(self, conf):
        """Perform a self_consistency check of the inter-related entries in the configuration."""
        valid = True

        # Verify that this config satisfies the requirements of SIP config
        if conf[u"num_SIP_stations"] != gv.sd['nst']:
            valid = False
            print("PEX: sanity_check_config fails!")
            print("PEX: Number of configured SIP stations is {}".format(conf[u"num_SIP_stations"]))
            print("PEX: Number of required SIP stations is {}".format(gv.sd["nst"]))

        if conf[u"num_SIP_stations"] > conf[u"num_PEX_stations"]:
            valid = False
            print("PEX: Sanity check of config fails. Not enough PEX stations configured.")
            print("PEX: SIP stations: {}   PEX stations: {}".format(conf[u"num_SIP_stations"],
                                                                    conf[u"num_PEX_stations"]))
        # Verify that the individual device configs agrees with the total.
        pex_span = sum([dev[u"size"] for dev in conf[u"dev_configs"]])
        if pex_span != conf[u"num_PEX_stations"]:
            valid = False
            print("PEX: Sanity check of config fails. Not enough PEX io extenders configured.")
        return valid

    def verify_hardware_config(self, conf):
        if not len(conf[u"dev_configs"]):
            print("PEX: verify_hardware_config fails. No devices configured.")
            return False

        valid = True
        for i in range(len(conf[u"dev_configs"])):
            addr = int(conf[u"dev_configs"][i][u"hw_addr"], 16)
            if not self.verify_device_handshake(conf[u"default_smbus"], addr):
                valid = False
                print("PEX: verify_hardware_config -- device number {} no ACK handshake".format(i))
        return valid

    def scan_for_ioextenders(self, bus_id):
        'Scan well known bus address range for supported hardware port extenders.'
        i2c_start_addr = 0x20  # beginning i2c address for MCP230x and pcf857x
        i2c_end_addr = 0x27  # last possible i2c address for MCP230x and pcf857x
        return i2c_scan(bus_id, i2c_start_addr, i2c_end_addr)

    def verify_device_handshake(self, bus_id, bus_addr: int):  # jfm static typing
        """Use SMbus ACK protocol for handshake to verify connectivity."""
        i2c_start_addr = bus_addr  # device to verify
        i2c_end_addr = bus_addr
        result = len(i2c_scan(bus_id, i2c_start_addr, i2c_end_addr)) != 0
        return result

    def alter_SIP_gpio_behavior(self):
        """Disable SIP gpio shift register if Port Extender is configured to use smbus."""
        if self.pex_c[u"pex_status"] == u"enabled":
            # disable gpio_pins. We can discuss later if a mix of gpio and i2c should be possible
            gv.use_gpio_pins = False
        else:
            gv.use_gpio_pins = True

    def set_output(self):
        '''Maps the SIP Station Values to the configured hardware port(s).'''
        if self.pex_c[u"pex_status"] != "enabled":
            print(u'ERROR: PEX not enabled. Need to reconfigure.')
            return

        print("DeBug: PEX set outputs for {} ports.".format(gv.sd[u"nst"]))

        # use srvalues to set values of configured ports.
        # Map srvalues to the device(s). The order that the devices are
        # listed in the config are the order for mapping. The first device
        # maps the first DeviceSize (8 or 16) ports to Station_1 through
        # Station_N (N=8 or 16).
        #
        # Should look like:
        #   for dev in self.pex_c["dev_configs"]:
        #     slice_for_device = gv.srvals[dev.first, dev.last]
        #     res = 0
        #     for i,v in enuerate(slice_for_device[::-1]):  # reverse MSB of 16 or 8 bits
        #                                                   # SIP Station 1 --> first port output P1
        #                                                   # SIP Station('last') --> last port output P[ 8 | 16 ]
        #        if v: res |= 1<<i
        #     self.port.set_output(res]
        #
        # NOTE: the following code maps SIP Station 1 to the most significant bit of
        #       the data written to set the output value of the port register.
        st = 0  # start index in successive slices
        sr_len = gv.sd[u"nst"]  # could use len(gv.srvals)
        device_index = 0
        for dev in self.pex_c[u"dev_configs"]:  # For each device set outputs to SIP values
            port_size = dev[u"size"]
            result = 0
            n = 1
            stp = min(st + port_size, sr_len)  # last element in slice
            for i in range(st, stp):
                if gv.srvals[i] == 1:
                    result += n
                n *= 2  # arithmetic shift left one bit
            st = st + port_size  # ready for next slice
            if st > sr_len:
                hw_addr = int(dev["hw_addr"], 16)
                print(f'Debug: PEX dev@0x{hw_addr:02X} has {st - sr_len} unused ports.')
            self.ports[device_index].set_output(result)
            device_index += 1  # zero based list index + 1 == device id
            print("Debug: PEX set_output to {:04X} for device {}".format(result, device_index))
        if st < sr_len:  # ran out of devices to map before last srvals have been output
            print(u"ERROR: PEX too many Stations configured for configured io_extender hardware.")
            print(u"           Either reduce number of stations are add/configure additional")
            print(u"           io_extender hardware.")
