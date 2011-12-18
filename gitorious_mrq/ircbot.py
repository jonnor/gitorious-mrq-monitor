import HTMLParser

from twisted.words.protocols import irc
from twisted.internet import protocol, task

from gitorious_mrq import feedreader

class GitoriousMergeRequestMessager(object):
    """Process Gitorious RSS and report messages for new merge requests.

    Call processRss on it to let it process an updated RSS feed.
    For each new message, message_callback as passed in the constructor
    will be called."""

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

            h = HTMLParser.HTMLParser()
            msg = h.unescape(msg)
            # - link to merge request

        return msg

class IrcBot(object):
    """Bot "business logic". Periodically polls the RSS feed and
    processes it."""

    # FIXME: we don't support multiple feeds, fix the API

    def __init__(self, feeds):
        self.check_rss_task = task.LoopingCall(self.checkRssFeed)
        self.processor = GitoriousMergeRequestMessager(self.outputMessage)
        self.protocol = None
        self.feeds = feeds
        self.is_running = False

    def start(self):
        self.check_rss_task.start(60*5) # Every 5 minutes
        self.is_running = True

    def stop(self):
        if self.is_running:
            self.check_rss_task.stop()
        self.is_running = False

    def checkRssFeed(self):
        f = feedreader.FeederFactory()
        d = f.start(self.feeds, self.processNewRss)

    def processNewRss(self, parsed_feed):
        self.processor.processRss(parsed_feed)

    def outputMessage(self, message):
        # FIXME: should not have knowledge about the protocol
        # Instead pass in a callback that gets called here?
        self.protocol.msg(self.protocol.factory.channel, message.encode('ascii', 'ignore'))

class IrcProtocol(irc.IRCClient):

    """Responsible for basic protocol handling,
    independent from the logic of the client. Joining the channel,
    and informing the business logic part about the current state.

    Note: This only has the lifetime of the connection/session,
    hence why the business logic is stored on the factory."""

    @property
    def nickname(self):
        return self.factory.nickname

    @property
    def lineRate(self):
        return 1 # Limit rate to 1 line per second

    def signedOn(self):
        self.join(self.factory.channel)
        print "Signed on as %s." % (self.factory.nickname,)

    def joined(self, channel):
        print "Joined %s." % (channel,)
        self.factory.bot.start()

    def left(self, channel):
        print 'Left %s.' % (channel,)

class IrcBotFactory(protocol.ClientFactory):
    """Responsible for connecting to IRC, handling reconnects,
    and creating a protocol instance and associated business logic."""

    protocol = IrcProtocol

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
        self.bot.stop()
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: (%s), reconnecting" % (reason,)
        self.bot.stop()
        connector.connect()

