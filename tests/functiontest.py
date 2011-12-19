import os

from twisted.web import server, resource, static
from twisted.internet import reactor, protocol

import gitorious_mrq
import gitorious_mrq.ircbot

"""Verify the essential functionality of the bot."""

# TODO: make into an automated test
# Either
# 1. Implement channels for Twisted Words IRC server
# 2. Find another Python IRC server implementation
#
# Then hook up the IRC server in code and verify behavior programatically

monitor_executable = 'gitorious-mrq-monitor'

class Feed(resource.Resource):
    isLead = True
    
    def __init__(self):
        resource.Resource.__init__(self)
        self.request_no = 0
    
    def render_GET(self, request):
        
        # FIXME: unhardcode, make more general
        self.request_no += 1
        if self.request_no > 4:
            self.request_no = 1
        return open("tests/data/maliit.atom.%d.txt" % self.request_no).read()


class MonitorProcessProtocol(protocol.ProcessProtocol):

    def __init__(self):
        pass


def run_mrq_monitor():
    
    args = [monitor_executable, 'maliit',
            '--host=http://localhost:8080', '--poll-interval=15', '--irc-channel=#gitorious-mrq-monitor-test',]
    executable = monitor_executable
    
    #executable = 'which'
    #args = [executable, 'gitorious-mrq-monitor']
    print args
    
    # Hook up child process file descriptions to the parent
    childFDs = { 0: 0, 1: 1, 2: 2}
    
    # FIXME: refactory gitorious-mrq-monitor such that we can call it directly as Python here?

    processProtocol = MonitorProcessProtocol()
    reactor.spawnProcess(processProtocol, executable, args=args, childFDs=childFDs, env=os.environ)

def setup_feedserver():

    root = static.File('./tests/data')
    feed = Feed()
    root.putChild("maliit.atom", feed)
    site = server.Site(root)
    reactor.listenTCP(8080, site)

def setup_monitor():
    reactor.callLater(3, run_mrq_monitor)

if __name__ == '__main__':

    setup_feedserver()  
    setup_monitor()

    reactor.run()
