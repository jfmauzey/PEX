#!/usr/bin/env python
#  pex.py -- Provides interface to io extender boards to replace the standard
#            SIP shift register for controlling the irrigation stations.
#  John Mauzey 230315
#
# Need to share four SIP variables. Possible concurrency issues
#   with main Timing loop thread and/or SIP UI sessions.
# gv.use_gpio_pins  -- Controls use of several GPIO pins on rpi platform.
#                   -- Accessed by Timing loop. May be changed by PEX.
# gv.srvals         -- SIP Array [S1, S2, S3 ..., Slast] containing io port values.
#                   -- Accessed by Timing loop.
#
# gv.sd[u"nst"]     -- Integer value of number of SIP stations.
#                   -- Accessed by Timing loop and SIP UI session.
# gv.sd[u"alr"]     -- True uses negative logic (ON=0, OFF=1).
#                   -- Accessed by Timing loop and SIP UI session.
#                   -- False uses positive logic (ON=1, OFF=0).
#                   -- Acronym Active Low Relay.

# Python 2/3 compatibility imports
from __future__ import print_function

# local module imports
import copy
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
        u"/pex-scan", u"plugins.pex.scan",
        u"/pex-cfs", u"plugins.pex.ConfigSave"
    ]
)

# Add this plugin to the plugins menu
gv.plugin_menu.append([u"pex", u"/pex"])

#  PEX footer
#  Create shared memory used by the SIP controller and the webpy web server.
#  The Javascript callback from web server gets the current value of the
#  controller's status. The data is displayed in the footer of the browser.
#  Called in response to GET /api/plugins.
#  uses a two-second polling window to synchronize.
#  Pex controller initializes and updates the footer.

# Initialize the PEX footer which appears at the bottom of all pages.
pex_footer1 = showInFooter()
pex_footer1.label = u"PEX Status"
pex_footer2 = showInFooter()
pex_footer2.label = u"Message"


#  Write to shared memory. The web server reads in response
#  to GET from /api/plugins.
def pex_footer_update(dmode, status, port_config, autoconf, msg):
    r = dmode
    r += u' {} - - - IO_Hardware: {}'.format(status, port_config)
    r += u' - - - Autoconfig: {}'.format("enabled" if autoconf else "disabled")
    pex_footer1.val = r
    pex_footer2.val = u'{}'.format(msg if len(msg) else "No message")

# Build and initialize the PEX controller
pex = PEX()

#  pex_c maintains the permanently saved configuration for the controller
#  and is the source for the configuration information displayed on the pex
#  web page.  Really just a shortcut to keep from typing "pex.pex_c".
pex_c = pex.pex_c

#  Initialize the footer with the current status: Defined at startup.
if pex_c[u"demo_mode"] or not pex.smbus_avail:
    dmode = u"DEMO_MODE"
else:
    dmode = u""
pex_footer_update(dmode, pex_c[u"pex_status"], pex.config_status,
                  pex_c[u"auto_configure"], pex.pex_msg)


# PEX hooks two blinker signals from SIP:
#   1. on_zone_change() signal from SIP to change values of output ports.
#   2. notify_option_change() signal from SIP notifying pex that the
#      configuration has changed.

# Output station settings to the IO Extneder(s) when signal received
def on_zone_change(name, **kw):
    """ Set state of all stations connected to the IO Extender(s) whew SIP signals
        a change in station state."""

    if pex_c[u"pex_status"] != u"enabled":
        print("PEX: Failure to set outputs because it is DISABLED and not in RUN mode.")
        pex.pex_msg = "ERROR: Failure to set outputs because PEX is DISABLED!."
        if pex_c[u"demo_mode"] or not pex.smbus_avail:
            dmode = u"DEMO_MODE"
        else:
            dmode = u""
        pex_footer_update(dmode, pex_c[u"pex_status"], pex.config_status,
                          pex_c[u"auto_configure"], pex.pex_msg)
        return
    if pex.config_status != u"configured":
        print(u"PEX configuration error: plugin blocked, need to configure.")
        pex.pex_msg = "ERROR: Failure to set outputs. PEX needs to be configured."
        if pex_c[u"demo_mode"] or not pex.smbus_avail:
            dmode = u"DEMO_MODE"
        else:
            dmode = u""
        pex_footer_update(dmode, pex_c[u"pex_status"], pex.config_status,
                          pex_c[u"auto_configure"], pex.pex_msg)
        return
    try:
        pex.set_output()
    except Exception as e:
        print(u"ERROR: PEX failed to set state of outputs.")
        print(repr(e))
        pex.pex_msg = "ERROR: Failure to set outputs. PEX needs to be configured."
        if pex_c[u"demo_mode"] or not pex.smbus_avail:
            dmode = u"DEMO_MODE"
        else:
            dmode = u""
        pex_footer_update(dmode, pex_c[u"pex_status"], pex.config_status,
                          pex_c[u"auto_configure"], pex.pex_msg)

zones = signal(u"zone_change")
zones.connect(on_zone_change)


def notify_option_change(name, **kw):
    print(u"PEX: SIP Option settings changed. Check for need to reconfigure.")
    if pex_c[u"pex_status"] != u"enabled":
        return
    if gv.sd[u"nst"] != pex.num_SIP_stations or \
       gv.sd[u"alr"] != pex.SIP_alr:  # config changed
       print(u"PEX: SIP options changed. Reconfiguring IO Device setting.")
       pex.num_SIP_stations = gv.sd[u"nst"]
       pex.SIP_alr = gv.sd[u"alr"]
       if pex_c[u"auto_configure"]:
           pex_c[u"dev_configs"] = pex.auto_config(pex_c)
           pex_c[u"num_PEX_stations"] = sum(dev[u"size"] for dev in pex_c[u"dev_configs"])
           if len(pex_c[u"dev_configs"]):  # autogenerated configs exist only if successful
               pex.config_status = u"configured"
               pex_c[u"num_PEX_stations"] = sum([dev[u"size"] for dev in pex_c[u"dev_configs"]])
               pex.pex_msg = u"IO Ports Successfully reconfigured."
           else:
               pex.config_status = u"unconfigured"  # Failure to auto-configure
               print(u"PEX: Failure to automagically configure. PEX is blocked from running.")
               pex_c[u"num_PEX_stations"] = 0
               pex.pex_msg = u"ERROR: Autoconfigure failed."
       else:
           print("PEX: Auto-configure disabled. Need to manually configure devices.")
           pex.config_staus = u"unconfigured"  # Must manually configure
           pex_c[u"num_PEX_stations"] = 0
           pex.pex_msg = u"ERROR: Must manually reconfigure PEX."

       # Save modified configuration to permanent storage in json file
       pex.save_config(pex_c)
       if pex_c[u"demo_mode"] or not pex.smbus_avail:
           dmode = u"DEMO_MODE"
       else:
           dmode = u""
       pex_footer_update(dmode, pex_c[u"pex_status"], pex.config_status,
                         pex_c[u"auto_configure"], pex.pex_msg)

option_change = signal(u"option_change")
option_change.connect(notify_option_change)

################################################################################
# Web pages:                                                                   #
################################################################################


class Settings(ProtectedPage):
    """Load html page showing the PEX home page."""

    def GET(self):
        if pex_c[u"demo_mode"] or not pex.smbus_avail:
            dmode = u"DEMO_MODE"
        else:
            dmode = u""
        pex_footer_update(dmode, pex_c[u"pex_status"], pex.config_status,
                          pex_c[u"auto_configure"], pex.pex_msg)
        try:
            sp = template_render.pex(pex, pex_c, pex.edit_conf, gv)
        except Exception as e:
            print("PEX: Settings.GET.template_render: Error likely caused by bad data in config.")
            print(repr(e))
            pex_c[u"pex_status"] = u"disabled"
            pex.pex_msg = u"ERROR PEX: bad config"
        return sp  # Possible that sp is not defined if error occurred


class ConfigSave(ProtectedPage):
    """Load html page with the possibly modified PEX config settings."""

    def GET(self):
        global pex, pex_c
        qdict = (web.input())
        update_needed = False
        pex_e = pex.edit_conf
        print('qdict= {}'.format(qdict), file=sys.stderr)
        if "enable_pex" in qdict:
            if pex_e[u"pex_status"] == "disabled":
                update_needed = True
            pex_e[u"pex_status"] = "enabled"
        else:
            if pex_e[u"pex_status"] == "enabled":
                update_needed = True
            pex_e[u"pex_status"] = "disabled"
        if "auto_configure" in qdict:
            if not pex_e[u"auto_configure"]:
                update_needed = True
            pex_e[u"auto_configure"] = 1
        else:
            if pex_e[u"auto_configure"]:
                update_needed = True
            pex_e[u"auto_configure"] = 0
        if "auto_ic" in qdict:
            if pex_e["default_ic_type"] != qdict["auto_ic"]:
                update_needed = True
            pex_e["default_ic_type"] = qdict["auto_ic"]
        if "demo_mode" in qdict:
            if not pex_e[u"demo_mode"]:
                update_needed = True
            pex_e[u"demo_mode"] = 1
        else:
            if pex_e[u"demo_mode"]:
                update_needed = True
            pex_e[u"demo_mode"] = 0
        if update_needed:
            pex.save_config(pex_e)  # save to permanent storage
            del(pex)  # Do some cleanup by explicitly deleting the controller
            pex = PEX()  # Restart
            pex_c = pex.pex_c

        if pex_c[u"demo_mode"] or not pex.smbus_avail:
            dmode = u"DEMO_MODE"
        else:
            dmode = u""
        pex_footer_update(dmode, pex_c[u"pex_status"], pex.config_status,
                          pex_c[u"auto_configure"], pex.pex_msg)
        try:
            sp = template_render.pex(pex, pex_c, pex.edit_conf, gv)
            return sp
        except Exception as e:
            print("PEX: ConfigSave.GET.template_render: Error likely caused by bad data in config.")
            print(repr(e))
            return web.seeother(u"/")  # return to SIP home page

class scan(ProtectedPage):
    """
    i2c scan page
    """

    def GET(self):
        pex.discovered_devices = pex.scan_for_ioextenders(pex_c)
        try:
            sp = template_render.pex(pex, pex_c, pex.edit_conf, gv)
            return sp
        except Exception as e:
            print("PEX: scan.GET.template_render: Error likely caused by bad data in config.")
            print(repr(e))
            return web.seeother(u"/")  # return to SIP home page

