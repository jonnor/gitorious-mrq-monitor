import os

from zope.interface import implements

from twisted.web import server, resource, static
from twisted.internet import reactor, protocol, defer

from twisted.cred import portal, checkers, error, credentials
from twisted.words.protocols import irc
from twisted.words import service



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


class TestIRCUser(service.IRCUser):

    def connectionMade(self):
        self.realm = self.factory.realm
        self.hostname = self.realm.name

    def irc_NICK(self, prefix, params):
        nickname = params[0].decode('ascii', 'ignore')

        password = 'anonymous'

        print self.irc_PRIVMSG

        self.password = password
        self.logInAs(nickname, password)
       
        pass

    #def irc_NICKSERV_PRIVMSG(self, msg):
        # Disable NickServ asking for password        
     #   pass

    #def irc_PRIVMSG(self, prefix, params):
    #    pass

class TestIRCFactory(service.IRCFactory):
    protocol = TestIRCUser

    def buildProtocol(self, addr):
        protocol = TestIRCUser()
        protocol.factory = self
        return protocol

class DummyCredChecker:
    implements(checkers.ICredentialsChecker)
    credentialInterfaces = (credentials.IAnonymous, 
                            credentials.IUsernamePassword, 
                            credentials.IUsernameHashedPassword)

    def requestAvatarId(self, credentials):

        return defer.succeed(credentials.username)

def run_mrq_monitor():
    
    args = [monitor_executable, 'maliit',
            '--host=http://localhost:8080', '--poll-interval=15',
            '--irc-channel=#gitorious-mrq-monitor-test', '--irc-server=localhost', '--irc-nick=subject']
    executable = monitor_executable
    
    #executable = 'which'
    #args = [executable, 'gitorious-mrq-monitor']
    print args
    
    # Hook up child process file descriptions to the parent
    childFDs = { 0: 0, 1: 1, 2: 2}
    
    # FIXME: refactory gitorious-mrq-monitor such that we can call it directly as Python here?

    processProtocol = MonitorProcessProtocol()
    reactor.spawnProcess(processProtocol, executable, args=args, childFDs=childFDs, env=os.environ)

class TestIrcClient(irc.IRCClient):

    @property
    def nickname(self):
        return self.factory.nickname

    @property
    def channel(self):
        return self.factory.channel

    @property
    def lineRate(self):
        return 1 # Limit rate to 1 line per second

    def signedOn(self):
        self.join(self.channel)
        print "Tester: Signed on as %s." % (self.nickname,)

    def privmsg(self, user, channel, msg):
        print user, channel, msg

    def joined(self, channel):
        #print "Joined %s." % (channel,)
        pass

    def left(self, channel):
        #print 'Left %s.' % (channel,)
        pass

class TestIrcClientFactory(protocol.ClientFactory):

    protocol = TestIrcClient

    def __init__(self, channel, nickname):

        self.channel = channel
        self.nickname = nickname

    def buildProtocol(self, addr):
        protocol = TestIrcClient()
        protocol.factory = self
        return protocol

    def clientConnectionLost(self, connector, reason):
        print "Lost connection (%s), reconnecting." % (reason,)
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: (%s), reconnecting" % (reason,)
        connector.connect()

def setup_webserver():
    root = static.File('./tests/data')
    feed = Feed()
    root.putChild("maliit.atom", feed)
    site = server.Site(root)
    reactor.listenTCP(8080, site)

def setup_ircserver():
    realm = service.InMemoryWordsRealm('localhost')
    cred_checker = DummyCredChecker()
    portal_ = portal.Portal(realm, [cred_checker])
    factory = TestIRCFactory(realm, portal_)
    reactor.listenTCP(6667, factory)

def setup_irctestclient():
    factory = TestIrcClientFactory('#gitorious-mrq-monitor-test', 'tester')
    reactor.connectTCP('localhost', 6667, factory)

def setup_monitor():
    reactor.callLater(3, run_mrq_monitor)

if __name__ == '__main__':

    setup_webserver()  
    setup_ircserver()
    setup_irctestclient()
    setup_monitor()

    reactor.run()
