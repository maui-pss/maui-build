import supybot.conf as conf
import supybot.registry as registry

def configure(advanced):
    conf.registerPlugin("MauiBuild", True)

MauiBuild = conf.registerPlugin("MauiBuild")
