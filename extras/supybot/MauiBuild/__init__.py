import supybot
import supybot.world as world

__version__ = "0"

import config
import plugin
reload(plugin)

Class = plugin.Class
configure = config.configure
