from twisted.internet import protocol, defer
from twisted.web import client

import feedparser

import time, sys, StringIO

TIMEOUT = 90 # Timeout in seconds for the web request

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
        # TODO: be nice and use HTTP conditional GET to reduce load
        # http://fishbowl.pastiche.org/2002/10/21/http_conditional_get_for_rss_hackers/
        # http://www.phppatterns.com/docs/develop/twisted_aggregator
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
