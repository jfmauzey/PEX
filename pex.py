#!/usr/bin/env python
#  pex.py -- Provides interface to io extender boards to replace the standard
#            SIP shift register for controlling the irrigation stations.
#  John Mauzey 230315
#
# Re-implementation of the user interface.
# Python 2/3 compatibility imports
from __future__ import print_function

# standard library imports
import json
import platform

# local module imports
import gv  # Get access to SIP's settings, gv = global variables
from sip import template_render
from urls import urls  # Get access to SIP's URLs
import web
from webpages import ProtectedPage


# Add new url's to create the PEX plugin status and configuration views.
# fmt: off
urls.extend(
    [
        u"/pex", u"plugins.pex.settings",
    ]
)

# Add this plugin to the plugins menu
gv.plugin_menu.append([u"pex", u"/pex"])

pex_c = {u"pex_status": "Just born."}

################################################################################
# Web pages:                                                                   #
################################################################################


class settings(ProtectedPage):
    """Load an html page for entering PEX settings."""

    def GET(self):
        return template_render.pex(pex_c)
