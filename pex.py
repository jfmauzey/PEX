#!/usr/bin/env python
#  pex.py -- Provides interface to io extender boards to replace the standard
#            SIP shift register for controlling the irrigation stations.
#  John Mauzey 230315
#
# Re-implementation of the user interface.
# Python 2/3 compatibility imports
from __future__ import print_function

# local module imports
import sys

import gv  # Get access to SIP's settings, gv = global variables
from blinker import signal
from sip import template_render
from urls import urls  # Get access to SIP's URLs
import web
from webpages import ProtectedPage
from webpages import showInFooter # Enable plugin to display status in UI footer

# PEX module imports
from port_extender.port_extender import PEX


# Add new url's to create the PEX plugin status and configuration views.
# fmt: off
urls.extend(
    [
        u"/pex", u"plugins.pex.Settings",
        u"/pex-cfs", u"plugins.pex.ConfigSave"
    ]
)

# Add this plugin to the plugins menu
gv.plugin_menu.append([u"pex", u"/pex"])

# Need to share five SIP variables. Possible concurrency issues
#   with main Timing loop thread and/or SIP UI sessions.
# gv.use_gpio_pins  -- Controls use of several GPIO pins on rpi platform.
#                   -- Accessed by Timing loop. May be changed by PEX.
# gv.srvals         -- SIP Array [S1, S2, S3 ..., Slast] containing io port values.
#                   -- Accessed by Timing loop.
#
# gv.sd[u"en"]      -- True if SIP in run or manual mode, else False.
#                   -- Accessed by Timing loop and SIP UI session.
# gv.sd[u"nst"]     -- Integer value of number of SIP stations.
#                   -- Accessed by Timing loop and SIP UI session.
# gv.sd[u"alr"]     -- True uses negative logic (ON=0, OFF=1).
#                   -- Accessed by Timing loop and SIP UI session.
#                   -- False uses positive logic (ON=1, OFF=0).
#                   -- Acronym Active Low Relay.


#  Create shared memory used by the controller and the webpy web server.
#  The Javascript callback from web server gets the current value of the
#  controller's status. The data is displayed in the footer of browser.
#  Called in response to GET /api/plugins.
#  uses a two-second polling window to synchronize.
#  Pex controller initializes, reads, and writes.

pex_footer1 = showInFooter()
pex_footer1.label = u"PEX Status"
pex_footer2 = showInFooter()
pex_footer2.label = u"Message"


#  Write to shared memory. The web server reads in response
#  to GET from /api/plugins.
def pex_footer_update(status, autoconf, msg):
    r = f'  Controller: {status}'
    r += f'    Autoconfig: {"enabled" if autoconf else "disabled"}'
    pex_footer1.val = r
    pex_footer2.val = f'{msg if len(msg) else "No message"}'

# Build and initialize the PEX controller
pex = PEX()

#  pex_c is the runtime data for the controller.
pex_c = pex.pex_c

#  Initialize the footer with the current status: Defined at startup.
pex_footer_update(pex_c[u"pex_status"], pex_c[u"auto_configure"], pex_c[u"warnmsg"])


# Output station settings to the IO Extneder(s) when signal received
def on_zone_change(name, **kw):
    """ Set state of all stations connected to the IO Extender(s) when core program signals
 a change in station state."""

    if pex_c[u"pex_status"] != u"enabled":
        print("PEX: Not in RUN mode.")
        pex_c[u"warnmsg"] = "ERROR: Failure to set outputs. PEX needs to be configured."
        return
    if pex_c[u"num_SIP_stations"] != gv.sd[u"nst"]:
        # HERE validate then attempt to reconfigure?
        print(u"pex configuration error: plugin blocked, not enough pex ports.")
        pex_c[u"warnmsg"] = "ERROR: Failure to set outputs. PEX needs to be configured."
        return
    if pex_c[u"config_status"] != u"configured":
        print(u"pex configuration error: plugin blocked, need to configure.")
        pex_c[u"warnmsg"] = "ERROR: Failure to set outputs. PEX needs to be configured."
        return
    try:
        print('DEBUG PEX: setting output')
        pex.set_output()
    except Exception as e:
        print(u"ERROR: PEX failed to set state of outputs.")
        print(repr(e))
        pex_c[u"warnmsg"] = "ERROR: Failure to set outputs. PEX needs to be configured."
        print("Debug: PEX that's ALL Folks.")

zones = signal(u"zone_change")
zones.connect(on_zone_change)


def notify_option_change(name, **kw):
    print(u"PEX: SIP Option settings changed. Check for need to reconfigure.")
    if gv.sd[u"nst"] != pex_c[u"num_SIP_stations"] or \
       gv.sd[u"alr"] != pex_c[u"SIP_alr"]:  # config changed
       print(u"PEX: SIP options changed. Reconfiguring IO Device setting.")
       pex_c[u"num_SIP_stations"] = gv.sd[u"nst"]
       pex_c[u"SIP_alr"] = gv.sd[u"alr"]
       if pex_c[u"auto_configure"]:
           pex_c[u"dev_configs"] = pex.autogenerate_device_config(pex_c[u"default_ic_type"],
                                                                  pex_c[u"default_smbus"])
           if len(pex_c[u"dev_configs"]):  # autogenerated configs exist only if successful
               pex_c[u"config_status"] = u"configured"
           else:
               pex_c[u"config_staus"] = u"unconfigured"  # Failure to auto-configure
               print(u"PEX: Failure to automagically configure. PEX is blocked from running.")

           # update PEX config status and number_configured_pex_ports
           pex_c[u"num_SIP_stations"] = gv.sd[u"nst"]
           pex_c[u"num_PEX_stations"] = sum([dev[u"size"] for dev in pex_c[u"dev_configs"]])
       else:
           print("PEX: Auto-configure disabled. Need to manually configure devices.")
           pex_c[u"config_staus"] = u"unconfigured"  # Must manually configure
           pex_c[u"num_PEX_stations"] = 0

       # Save modified configuration to permanent storage in json file
       pex.save_config(pex_c)

option_change = signal(u"option_change")
option_change.connect(notify_option_change)

################################################################################
# Web pages:                                                                   #
################################################################################


class Settings(ProtectedPage):
    """Load html page showing the PEX home page."""

    def GET(self):
        pex_footer_update(pex_c[u"pex_status"], pex_c[u"auto_configure"],
                          pex_c[u"warnmsg"])
        try:
            sp = template_render.pex(pex_c, gv)
        except Exception as e:
            print("PEX: Settings.GET.template_render: Error likely caused by bad data in config.")
            print(repr(e))
        return sp


class ConfigSave(ProtectedPage):
    """Load html page with the possibly modified PEX config settings."""

    def GET(self):
        qdict = (web.input())
        update_needed = False
        print(f'qdict= {qdict}', file=sys.stderr)
        if "enable_pex" in qdict:
            if pex_c[u"pex_status"] == "disabled":
                update_needed = True
            pex_c[u"pex_status"] = "enabled"
        else:
            if pex_c[u"pex_status"] == "enabled":
                update_needed = True
            pex_c[u"pex_status"] = "disabled"
        if "auto_configure" in qdict:
            if not pex_c[u"auto_configure"]:
                update_needed = True
            pex_c[u"auto_configure"] = 1
        else:
            if pex_c[u"auto_configure"]:
                update_needed = True
            pex_c[u"auto_configure"] = 0
        if "auto_ic" in qdict:
            if pex_c["default_ic_type"] != qdict["auto_ic"]:
                update_needed = True
            pex_c["default_ic_type"] = qdict["auto_ic"]
        if update_needed:
            pex.save_config(pex_c)  # save to permanent storage
        pex_footer_update(pex_c[u"pex_status"], pex_c[u"auto_configure"],
                          pex_c[u"warnmsg"])
        try:
            sp = template_render.pex(pex_c, gv)
            return sp
        except Exception as e:
            print("PEX: ConfigSave.GET.template_render: Error likely caused by bad data in config.")
            print(repr(e))
            return web.seeother(u"/")  # return to SIP home page
