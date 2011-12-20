import HTMLParser, re

from twisted.words.protocols import irc
from twisted.internet import protocol, task

from gitorious_mrq import feedreader, scrape

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

    def __init__(self, host, project, poll_interval):
        self.check_rss_task = task.LoopingCall(self.checkForUpdates)
        self.processor = GitoriousMergeRequestMessager(host, project, self.outputMessage)
        self.protocol = None
        self.host = host
        self.project = project
        self.poll_interval = poll_interval
        self.is_running = False
        self._open_merge_requests = None # None meaning invalid data

    def start(self):
        self.check_rss_task.start(self.poll_interval)
        self.is_running = True

    def stop(self):
        if self.is_running:
            self.check_rss_task.stop()
        self.is_running = False

    def checkForUpdates(self):
        # Check feed for activity
        feed = scrape.project_activity_feed_template % dict(host=self.host, project=self.project)
        f = feedreader.FeederFactory()
        d = f.start([feed], self.processNewRss)

    def processNewRss(self, parsed_feed):
        self.processor.processRss(parsed_feed)
        # There was some new activity, update our state
        self.triggerOpenMergeRequestsUpdate()
    
    def triggerOpenMergeRequestsUpdate(self):
        f = scrape.MergeRequestRetriever()
        d = f.start(self.host, self.project)
        d.addCallback(self.updateOpenMergeRequests)

    def updateOpenMergeRequests(self, mrqs):
        self._open_merge_requests = mrqs

    @property
    def open_merge_requests(self):
        if self._open_merge_requests is None:
            self.triggerOpenMergeRequestsUpdate()
        
        return self._open_merge_requests

    def outputMessage(self, message):
        # FIXME: should not have knowledge about the protocol
        # Instead pass in a callback that gets called here?
        # XXX: Probably better to have state update notifications
        # here, and let consumers subscribe to them
        self.protocol.msg(self.protocol.factory.channel, message.encode('ascii', 'ignore'))

def url_for_mrq(host, project, id):
    return scrape.mrq_page_url_template % {'host': host, 'project': project, 'id': id}

def format_mrq_status_listing(mrqs):

    output = []

    for mrq in mrqs:
        output.append('%s/%s: - %s - %s' % (mrq['repository'], mrq['id'], mrq['status'], mrq['summary']))

    return '\n'.join(output)



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

    def privmsg(self, user, channel, msg):

        if msg.strip().startswith(self.nickname):
            self.parseCommand(user, msg)

        else:
            # TODO: try to match discussion about merge requests
            # and enrich by adding link and summary
            pass

    def parseCommand(self, user, msg):
            msg = re.compile(self.nickname + "[:,]* ?", re.I).sub('', msg)

            split = msg.split()
            command = split[0]
            args = split[1:]

            # TODO: status command
            # list number of open merge requests, and
            # - which state they are in
            # - which repositories they are in

            # TODO: testing commands
            # test-feed-update: trigger update of activity feed
            # Should not be shown in list of valid commands

            commands = {}

            def command_help(command, args):
                """Print usage help."""

                valid_commands = commands.keys()
                valid_commands.remove('dance')
                self.respondToUser(user, 'Valid commands: %s' % ' '.join(valid_commands))

            def command_list(command, args):
                """List all open merge requests."""
                
                self.printOpenMergeRequests(user)

            def command_dance(command, args):
                # Easteregg. Even if it is only just Christmas
                self.respondToUser(user, "Norwegians don't dance")

            commands.update({
                'list': command_list,
                'help': command_help, 
                'dance': command_dance,
                'commands': command_help,
            })

            def unknown_command(command, args):
                self.respondToUser(user, 'Unknown command: "%s". Try "help" instead.' % command)

            cmd_func = commands.get(command, unknown_command)
            cmd_func(command, args)

    def respondToUser(self, user, msg):
        response_prefix = "%s: " % (user.split('!', 1)[0], )
        response = response_prefix + msg
        encoded = msg.encode('ascii', 'ignore')
        self.msg(self.factory.channel, encoded)

    def printOpenMergeRequests(self, user):
        mrqs = self.factory.bot.open_merge_requests
        if mrqs is None:
            # TODO: just handle this case properly: async call to
            # get new information from the monitor
            self.respondToUser(user, 'No data available...')
            return
        elif not mrqs:
            self.respondToUser(user, 'No open merge requests')
        else:
            self.respondToUser(user, 'Open merge requests:\n' + format_mrq_status_listing(mrqs))

    def joined(self, channel):
        print "Joined %s." % (channel,)
        self.factory.bot.start()

    def left(self, channel):
        print 'Left %s.' % (channel,)

class IrcBotFactory(protocol.ClientFactory):
    """Responsible for connecting to IRC, handling reconnects,
    and creating a protocol instance and associated business logic."""

    protocol = IrcProtocol

    def __init__(self, channel, nickname, host_url, project, poll_interval):

        self.channel = channel
        self.nickname = nickname

        self.bot = IrcBot(host_url, project, poll_interval)

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

