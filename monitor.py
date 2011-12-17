from twisted.words.protocols import irc
from twisted.internet import protocol, task

class GitoriousMergeRequestMessager(object):

    @staticmethod
    def items_equal(item1, item2):
        return False

    def __init__(self, message_callback):
        self.callback = message_callback
        self.old_items = []

        # Used to avoid outputting RSS items that exists in the feed
        # at startup
        self.first_run = True

    def getNewItems(self, parsed_feed):
        items = parsed_feed.get('items', [])

        new_items = []
        for item in items:
            if not item in self.old_items:
                new_items.append(item)

        self.old_items = items
        return new_items

    def processRss(self, parsed_feed):
        new_items = self.getNewItems(parsed_feed)

        for item in new_items:
            msg = self.itemToMessage(item)
            if msg and not self.first_run:
                self.callback(msg)

        self.first_run = False

    def itemToMessage(self, item):

        msg = None

        # We are only interested in merge requests,
        # but not in comments on them (too noisy)
        title = item.get('title', '')
        if 'merge request' in title and not 'commented' in title:
            msg = '%s' % title

            # TODO: more pretty output
            # - escape HTML entities
            # - link to merge request

        return msg

class IrcBot(object):

    def __init__(self, feeds):
        self.check_rss_task = task.LoopingCall(self.checkRssFeed)
        self.processor = GitoriousMergeRequestMessager(self.outputMessage)
        self.protocol = None
        self.feeds = feeds

    def connected(self):
        self.check_rss_task.start(60*5)

    def disconnected(self):
        self.check_rss_task.stop()

    def checkRssFeed(self):
        f = FeederFactory()
        d = f.start(self.feeds, self.processNewRss)

    def processNewRss(self, parsed_feed):
        self.processor.processRss(parsed_feed)

    def outputMessage(self, message):
        self.protocol.msg(self.protocol.factory.channel, str(message))

class IrcProtocol(irc.IRCClient):

    @property
    def nickname(self):
        return self.factory.nickname

    @property
    def lineRate(self):
        return 1 # Limit rate to 1 line per second

    def signedOn(self):
        print "Signed on as %s." % (self.factory.nickname,)
        self.join(self.factory.channel)

    def joined(self, channel):
        print "Joined %s." % (channel,)
        self.factory.bot.connected()

    def left(self, channel):
        print 'Left %s.' % (channel,)

class IrcBotFactory(protocol.ClientFactory):

    def __init__(self, channel, nickname, feeds):
        self.channel = channel
        self.nickname = nickname
        self.feeds = feeds

        self.bot = IrcBot(feeds)

    def buildProtocol(self, addr):
        protocol = IrcProtocol()
        protocol.factory = self
        self.bot.protocol = protocol
        return protocol

    def clientConnectionLost(self, connector, reason):
        print "Lost connection (%s), reconnecting." % (reason,)
        self.bot.disconnected()
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: (%s), reconnecting" % (reason,)
        self.bot.disconnected()
        connector.connect()


from twisted.internet import reactor, protocol, defer
from twisted.web import client

import feedparser

import time, sys, StringIO

TIMEOUT = 30 # Timeout in seconds for the web request

class FeederProtocol(object):
    def __init__(self):
        self.parsed = 1
        self.with_errors = 0
        self.error_list = []

    def gotError(self, traceback, extra_args):
        print traceback, extra_args
        self.with_errors += 1
        self.error_list.append(extra_args)

    def parseFeed(self, feed):
        try:
            parsed = feedparser.parse(StringIO.StringIO(feed))
        except TypeError:
            parsed = feedparser.parse(StringIO.StringIO(str(feed)))
        return parsed

    def getPage(self, data, args):
        return client.getPage(args, timeout=TIMEOUT)

    def printStatus(self, data=None):
        print "Reading feed"

    def start(self, feeds, callback):
        d = defer.succeed(self.printStatus())
        for feed in feeds:

            # Fetch page
            d.addCallback(self.getPage, feed)
            d.addErrback(self.gotError, (feed, 'getting'))

            # Parse the feed
            d.addCallback(self.parseFeed)
            d.addErrback(self.gotError, (feed, 'parsing'))

            # Process it
            d.addCallback(callback)
            d.addErrback(self.gotError, (feed, 'processing'))

        return d

class FeederFactory(protocol.ClientFactory):
    protocol = FeederProtocol()
    def __init__(self):
        self.protocol.factory = self

    def start(self, feeds, callback):
        return self.protocol.start(feeds, callback)


from twisted.internet import reactor

if __name__ == "__main__":

    # RSS
    feed_url = 'http://gitorious.org/maliit.atom'

    # Irc bot
    channel = '#maliit'
    botname = 'maliit-gitorious'
    server = 'irc.freenode.net'
    port = 6667
    reactor.connectTCP(server, port, IrcBotFactory(channel, botname, [feed_url]))

    # Go!
    reactor.run()
