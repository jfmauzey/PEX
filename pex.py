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
        u"/pex", u"plugins.pex.settings",
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


################################################################################
# Web pages:                                                                   #
################################################################################


class settings(ProtectedPage):
    """Load an html page showing the PEX home page."""

    def GET(self):
        pex_footer_update(pex_c[u"pex_status"], pex_c[u"auto_configure"],
                          pex_c[u"warnmsg"])
        return template_render.pex(pex_c, gv)
