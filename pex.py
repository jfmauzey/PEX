#!/usr/bin/env python

# Python 2/3 compatibility imports
from __future__ import print_function

# standard library imports
import json
import subprocess
from sys import modules
import time
import platform
from port_extender.port_extender import PEX

# import smbus
SMBus_avail = False
try:
    import smbus
    SMBus_avail = True
except ModuleNotFoundError:
    try:
        import smbus2 as smbus
        SMBus_avail = True
    except ModuleNotFoundError:
        pass



# local module imports
from blinker import signal
import gv  # Get access to SIP's settings, gv = global variables
from sip import template_render
from urls import urls  # Get access to SIP's URLs
import web
from webpages import ProtectedPage

# Add a new url to open the data entry page.
# fmt: off
urls.extend(
    [
        u"/pex", u"plugins.pex.settings",
        u"/pexj", u"plugins.pex.settings_json",
        u"/pexu", u"plugins.pex.update",
        u"/pext", u"plugins.pex.test",
        u"/pex_scan", u"plugins.pex.scan"
    ]
)

# Add this plugin to the plugins menu
gv.plugin_menu.append([u"pex", u"/pex"])

demo_mode = True

if platform.machine() == "armv6l"  or platform.machine() == "armv7l":  # may be removed later but makes dev and testing possible without smbus
    demo_mode = False

pex = PEX()

# Read in the pex config for this plugin from it's JSON file
pex_c = pex.pex_c

i2c_bus_id = int(pex_c[u"default_smbus"])
io_extender_boards = pex.scan_for_ioextenders(i2c_bus_id)

# disable gpio_pins. We can discuss later if a mix of gpio and i2c should be possible
gv.use_gpio_pins = False

pex_c[u"discovered_devices"] = []

if not SMBus_avail:
    pex_c[u"warnmsg"] = "Unable to load library. please follow instructions on the help page"
    print(u"\33[31mWARNING: SMBUS library NOT loaded,\nPCF857x plugin will NOT be activated.")
    print(u"See plugin help page for instructions.\33[0m")
else:
    pex_c[u"warnmsg"] = {}


# for future use. No test devices available at the moment.
modbits=8   # default number op io pins on i2c module
if (pex_c[u"ic_type"]=="pcf8575"):
    modbits=16


#### output command when signal received ####
def on_zone_change(name, **kw):
    """ Send command when core program signals a change in station state."""
    if not SMBus_avail:
        print("pex plugin blocked due to missing library")
        return

    if len(pex_c[u"dev_configs"]) != gv.sd[u"nbrd"]:
        print("pex plugin blocked due to incomplete settings")
        return

    if demo_mode==False:
        bus = smbus.SMBus(int(pex_c[u"default_smbus"]))

    i2c_bytes = []

    for b in range(gv.sd[u"nbrd"]):
        byte = 0xFF
        for s in range(8): # for each virtual board
            sid = b * 8 + s  # station index in gv.srvals           
            if gv.output_srvals[sid]:  # station is on
                byte = byte ^ (1 << s) # use exclusive or to set station bit to 0
        #print("adding byte: ", hex(byte))
        i2c_bytes.append(byte)

    # jfm HERE
    # assumes that the number of boards is equal to number of configured io extenders
    for s in range(gv.sd[u"nbrd"]):
        if demo_mode:
            print("demo: bus.write_byte_data(" + pex_c[u"dev_configs"][s][u"hw_addr"] + ",0," + hex(i2c_bytes[s]) + ")" )
            print("demo: bus.write_byte(" + pex_c[u"dev_configs"][s][u"hw_addr"] + "," + hex(i2c_bytes[s]) + ")" )
            print("demo: bus.write_byte(" + str(int(pex_c[u"dev_configs"][s][u"hw_addr"],16)) + "," + hex(i2c_bytes[s]) + ")" )
        else:
            # the real stuff here
            try:
                if pex_c[u"debug"]=="1":
                  print("bus.write_byte(" + str(int(pex_c[u"dev_configs"][s][u"hw_adr"],16)) + "," + hex(i2c_bytes[s]) + ")" )

                bus.write_byte(int(pex_c[u"dev_configs"][s][u"hw_addr"], 16), i2c_bytes[s])
            except ValueError:
                print("ValueError: have you any i2c device configured?")
                pass
            except OSError:
                print("OSError: All i2c devices entered correctly?")
                pass

            


zones = signal(u"zone_change")
zones.connect(on_zone_change)

################################################################################
# Web pages:                                                                   #
################################################################################


class settings(ProtectedPage):
    """Load an html page for entering PEX"""

    def GET(self):
        pex_c[u"discovered_devices"] = []
        return template_render.pex(pex_c)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header(u"Access-Control-Allow-Origin", u"*")
        web.header(u"Content-Type", u"application/json")
        return json.dumps(pex_c)


class update(ProtectedPage):
    """Save user input to pex.json file"""

    def GET(self):
        global pex_c
        qdict = web.input()
        if u"discovered_devices" in pex_c:   # don't save temporary data
            del pex_c[u"discovered_devices"]
        if u"warnmsg" in pex_c:   # don't save temporary data
            del pex_c[u"warnmsg"]

        # jfm HERE
        # assumes that number of SIP configured boards is equal to the number of io extenders
        if (
            len(pex_c[u"dev_configs"]) != gv.sd[u"nbrd"]
        ):  #  if number of boards has changed, adjust length of adr lists
            if gv.sd[u"nbrd"] > len(pex_c[u"dev_configs"]):
                increase = [""] * (gv.sd[u"nbrd"] - len(pex_c[u"dev_configs"]))
                pex_c[u"dev_configs"].extend(increase)
            elif gv.sd[u"nbrd"] < len(pex_c[u"dev_configs"]):
                pex_c[u"dev_configs"] = pex_c[u"dev_configs"][: gv.sd[u"nbrd"]]
        for i in range(gv.sd[u"nbrd"]):
            pex_c[u"dev_configs"][i] = qdict[u"con" + str(i)]
        if u"bus" in qdict:
            pex_c[u"default_smbus"] = qdict[u"bus"]
        else:
            pex_c["default_smus"] = 1

        if u"ictype" in qdict:
            pex_c[u"ic_type"] = qdict[u"ictype"]
        else:
            pex_c[u"ic_type"] = "pcf8574"

        if u"debug" in qdict: 
            if qdict[u"debug"]=="on":
                pex_c[u"debug"] = "1"
            else:
                pex_c[u"debug"] = "0"
        else:
            pex_c[u"debug"] = "0"

        with open(u"./data/pex_config.json", u"w") as f:  # write the settings to file
            json.dump(pex_c, f, indent=4)
        raise web.seeother(u"/restart")

class test(ProtectedPage):
    """ test i2c from setup plugin page"""

    # not used, might be usefull when called from browser?
    def GET(self):
        data = web.input()
        print("pcf-test-begin")
        for k, v in data.items():
          print(k, v)
        print("pct-test-end")

    def POST(self):
        data = web.input()
        print("pcf-post-test-begin")
        for k, v in data.items():
          print(k, v)
        if demo_mode:
            print("demo: bus.write_byte(" + data["tst_adres"] + "," + data["tst_value"] + ")" )
        else:
            bus = smbus.SMBus(int(data["tst_smbus"]))
            bus.write_byte(int(data["tst_adres"],16), int(data["tst_value"],16))

        print("pct-post-test-end")
        web.seeother(u"/pex")



class scan(ProtectedPage):
    """
    i2c scan page
    """

    def GET(self):
        global pex_c
        global demo_mode
        #data = web.input()
        if demo_mode:
            pex_c[u"discovered_devices"] = [0x27,0x25,0x20]
        else:
            pex_c[u"discovered_devices"] =  pex.scan_for_ioextenders(pex_c[u"default_smbus"])
        return template_render.pex(pex_c)

