import HTMLParser, re

from twisted.words.protocols import irc
from twisted.internet import protocol, task

from gitorious_mrq import feedreader

FEED_POLL_INTERVAL = 5*60 # Every 5 minutes

class GitoriousMergeRequestMessager(object):
    """Process Gitorious RSS and report messages for new merge requests.

    Call processRss on it to let it process an updated RSS feed.
    For each new message, message_callback as passed in the constructor
    will be called."""

    @staticmethod
    def items_equal(item1, item2):
        return False

    def __init__(self, host, project, message_callback):
        self.callback = message_callback
        self.project = project
        self.host = host
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

        # Typical title
        """jonnor updated merge request maliit/maliit-buildbot-configuration #1&#x2192; State changed from Go ahead and merge to Updated"""

        # We are only interested in merge requests,
        # but not in comments on them (too noisy)
        title = item.get('title', '')

        if 'merge request' in title and not 'commented' in title:
            msg = '%s' % title

            h = HTMLParser.HTMLParser()
            msg = h.unescape(msg)

            mrq_link = '%(host)s/%(project)s/%(repository)s/merge_requests/%(mrq)s'

            # PERF: Could compile the RE
            regexp = r'.*(merge request %(project)s/(\S*)\s*#(\d*)).*' % {'project': self.project}
            print regexp
            match = re.match(regexp, msg)

            if match is None:
                print msg
                return msg

            string_to_linkify, repo, mrq_no = match.groups()

            linked_str = (mrq_link + ' ') % {'host': self.host, 'project': self.project, 'repository': repo, 'mrq': mrq_no}
            msg = msg.replace(string_to_linkify, linked_str)

        return msg

# TODO: fix up the design
# Issue: It is hard to add a monitor that is independent from the ircbot
# Mainly because IrcBot should not be owned by the IrcBotFactory
#
# Solution: Invert the ownership of IrcBot and IrcBotFactory
# Create class Monitor(IService)
# Make it have the responsibility IrcBot has now
# Have a getIrcBot() method that returns
#
# See http://twistedmatrix.com/documents/current/core/howto/tutorial/style.html

# NOTE: If there is a need to make this stuff 'general'
# one could refactor the responsibilities of the service into two aspects:
# IMrqStatusProvider - provides updates about (example impl: RSS feed, gitorious webhooks*)
# IMrqStatusNotifier - notifies about such updates (example impl: IRC, stdout, website)
#
# * if they ever materialize
#
# The Monitor service is then responsible for creating instances of such components
# and hooking them up to eachother.
#
# For this to work sanely there would need to be a generic data-structure
# describing the merge request. As long as the only way to get the data is RSS
# this is very likely not worth it.

class IrcBot(object):
    """Bot "business logic". Periodically polls the RSS feed and
    processes it."""

    # FIXME: we don't support multiple feeds, fix the API

    def __init__(self, host, project):
        self.check_rss_task = task.LoopingCall(self.checkRssFeed)
        self.processor = GitoriousMergeRequestMessager(host, project, self.outputMessage)
        self.protocol = None
        self.host = host
        self.project = project
        self.is_running = False

    def start(self):
        self.check_rss_task.start(FEED_POLL_INTERVAL)
        self.is_running = True

    def stop(self):
        if self.is_running:
            self.check_rss_task.stop()
        self.is_running = False

    def checkRssFeed(self):
        feed = '%s/%s.atom' % (self.host, self.project)
        f = feedreader.FeederFactory()
        d = f.start([feed], self.processNewRss)

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

    def __init__(self, channel, nickname, host_url, project):

        self.channel = channel
        self.nickname = nickname

        self.bot = IrcBot(host_url, project)

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

