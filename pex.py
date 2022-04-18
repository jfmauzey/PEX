#!/usr/bin/env python

# Python 2/3 compatibility imports
from __future__ import print_function

# standard library imports
import json
import platform
from port_extender.port_extender import PEX

# local module imports
from blinker import signal
import gv  # Get access to SIP's settings, gv = global variables
from sip import template_render
from urls import urls  # Get access to SIP's URLs
import web
from webpages import ProtectedPage

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

# may be removed later but makes dev and testing possible without smbus
if platform.machine() == "armv6l" or platform.machine() == "armv7l":
    demo_mode = False

# load/create pex config using json permanent storage
pex = PEX()

# pex_c contains the configuration for the hardware and the configuration of the PEX controller.
#       Also works like a shared memory to exchange PEX UI display and update data.
pex_c = pex.pex_c

# disable gpio_pins. We can discuss later if a mix of gpio and i2c should be possible
gv.use_gpio_pins = False

if not SMBus_avail:
    pex_c[u"warnmsg"] = "Unable to load library. please follow instructions on the help page"
    print(u"\33[31mWARNING: SMBUS library NOT loaded,\nPCF857x plugin will NOT be activated.")
    print(u"See plugin help page for instructions.\33[0m")
else:
    pex_c[u"warnmsg"] = {}


#### output command when signal received ####
def on_zone_change(name, **kw):
    """ Send command when core program signals a change in station state."""

    if len(pex_c[u"dev_configs"]) != gv.sd[u"nbrd"]:
        print(u"pex plugin blocked due to incomplete configuration.")
        pex_c[u"warnmsg"] = "ERROR: Failure to set outputs. PEX needs to be configured."
        return
    try:
        pex.set_output(pex_c)
    except Exception as e:
        print(u"ERROR: PEX failed to set output.")
        print(repr(e))
        pex_c[u"warnmsg"] = "ERROR: Failure to set outputs. PEX needs to be configured."
        print("Debug: PEX that's ALL Folks.")

zones = signal(u"zone_change")
zones.connect(on_zone_change)


def notify_option_change(name, **kw):
    print(u"Option settings changed in gv.sd")
    if len(gv.srvals) != pex_c[u"num_SIP_stations"]: #config changed
        print(u"Num of boards changed in gv.sd")
        pex_c[u"dev_configs"] = pex.autogenerate_device_config(pex_c[u"default_ic_type"],
                                                               pex_c[u"default_smbus"])
        # update PEX status and number_configured_pex_ports
        pex_c[u"num_SIP_stations"] = len(gv.srvals)
        pex_c[u"num_PEX_stations"] = sum([dev[u"size"] for dev in pex_c[u"dev_configs"]],
                                              pex_c[u"num_PEX_stations"])
        pex_c[u"pex_status"] = u"configured"


option_change = signal(u"option_change")
option_change.connect(notify_option_change)

################################################################################
# Web pages:                                                                   #
################################################################################


class settings(ProtectedPage):
    """Load an html page for entering PEX settings."""

    def GET(self):
        pex_c[u"discovered_devices"] = pex.scan_for_ioextenders(pex_c[u"default_smbus"])
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
        if u"warnmsg" in pex_c:   # don't save temporary data
            pex_c[u"warnmsg"] == ""

        if u"bus" in qdict:
            pex_c[u"default_smbus"] = qdict[u"bus"]

        # Do we need ic_type in the PEX configuration. It's used as a
        # default value. Each device also has an ictype field that is
        # used for the PEX span when mapping SIP stations to ports.
        if u"ic_type" in qdict:
            pex_c[u"ic_type"] = qdict[u"ic_type"]
        else:
            pex_c[u"ic_type"] = pex_c[u"default_ic_type"]  # used for auto configure

        if u"debug" in qdict: 
            if qdict[u"debug"]=="on":
                pex_c[u"debug"] = "1"
            else:
                pex_c[u"debug"] = "0"
        else:
            pex_c[u"debug"] = "0"

        # jfm HERE
        # assumes that number of SIP configured boards is equal to the number of io extenders.
        # Result is that the PEX device configuration is automatically created to match
        # changes in the number of configured SIP stations. This code does not try to
        # map the devices discovered by the smbus scan to the list of configured devices.
        #if len(pex_c[u"dev_configs"]) != gv.sd[u"nbrd"]:  #  check if config changed
        #    if gv.sd[u"nbrd"] > len(pex_c[u"dev_configs"]):
        #        increase = gv.sd[u"nbrd"] - len(pex_c[u"dev_configs"])
        #        for i in range(increase):
        #            pex_c[u"dev_configs"].append(pex.create_device(bus, ))
        #    elif gv.sd[u"nbrd"] < len(pex_c[u"dev_configs"]):
        #        decrease = gv.sd[u"nbrd"] - len(pex_c[u"dev_configs"])
        #        pex_c[u"dev_configs"] = pex_c[u"dev_configs"][:decrease]
        #for i in range(gv.sd[u"nbrd"]):
        #    pex_c[u"dev_configs"][i][u"hw_addr"] = qdict[u"con" + str(i)]

        # jfm auto configure requires assuming a device type and assignment to SIP stattions.
        if len(pex_c[u"dev_configs"]) != gv.sd[u"nbrd"]:  #  check if config changed
            pex_c[u"pex_status"] = u"unconfigured"

        # save changes to permanent storage
        pex.save_config((pex_c))

        #raise web.seeother(u"/restart")
        raise web.seeother(u"/pex")

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
            print("demo: bus.write_byte(" + data["tst_addr"] + "," + data["tst_value"] + ")" )
        else:
            if SMBus_avail:
                bus = smbus.SMBus(int(data["tst_smbus"]))
                bus.write_byte(int(data["tst_addr"],16), int(data["tst_value"],16))
            else:
                print('Cannot test device due to missing library.')

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
            pex_c[u"discovered_devices"] = pex.scan_for_ioextenders(pex_c[u"default_smbus"])
        return template_render.pex(pex_c)

