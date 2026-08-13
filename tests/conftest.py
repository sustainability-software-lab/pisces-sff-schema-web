# -*- coding: utf-8 -*-
# Present so pytest anchors its rootdir at tests/ regardless of the working
# directory a tier is run from. Intentionally empty of fixtures: the tiers share
# no runtime fixtures (each test builds what it needs), and unittest discovery
# ignores this file. A shared fixture, if one is ever needed, belongs here.
