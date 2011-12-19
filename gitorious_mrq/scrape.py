import datetime

from BeautifulSoup import BeautifulSoup

from twisted.internet import protocol, defer
from twisted.web import client

project_page_url_template = '%(host)s/%(project)s'
project_activity_feed_template = '%(host)s/%(project)s.atom'
mrq_overview_page_url_template = '%(host)s/%(project)s/%(repo)s/merge_requests'
mrq_page_url_template = '%(host)s/%(project)s/%(repo)s/merge_requests/%(id)s'

class UTC(datetime.tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO

utc = UTC()


def scrape_mrq_status_from_mrq_page(html_page):
    """Returns a list of the open merge requests and their status."""

    merge_requests = []
    soup = BeautifulSoup(html_page)

    for row in soup('table')[0].tbody('tr'):
      tds = row('td')

      # print tds
      """[<td><a href="/maliit/maliit-framework/merge_requests/127">#127</a></td>,
      <td style="color:#0080ff"> New      </td>,
      <td><a href="/maliit/maliit-framework/merge_requests/127">Allow QML plugins to add custom import paths for QML files and QML modules </a> </td>,
      <td>master</td>,
      <td><a href="/~mikhas">mikhas</a></td>,
      <td><abbr class="timeago" title="2011-12-17T15:35:14Z">2011-12-17 15:35:14 UTC</abbr></td>]"""

      # Columns: ID, Status, Summary, Target branch, Creator, Age
      mrq_id = tds[0].a.string.strip('#')
      status = tds[1].string.strip()
      summary = tds[2].a.string
      target_branch = tds[3].string
      creator = tds[4].a.string
      creation = datetime.datetime.strptime(tds[5].abbr['title'], '%Y-%m-%dT%H:%M:%SZ')

      merge_requests.append({'id': mrq_id, 'status': status,
            'summary': summary, 'target_branch': target_branch,
            'creator': creator, 'creation': creation})

    return merge_requests

def scrape_repositories_from_project_page(html_page):
    """Returns a list of the repositories in this project."""

    repositories = []
    soup = BeautifulSoup(html_page)

    attribute_matching = {'class': 'repository-info'}
    for tag in soup(**attribute_matching):
        repositories.append(tag.h3.a.string)

    return repositories

def add_repo_info_to_mrqs(mrqs, repo):
    for mrq in mrqs:
        mrq['repository'] = repo

def open_merge_requests(host, project):

    mrqs = []

    project_url = project_page_url_template % dict(host=host, project=project)

    html = urllib2.urlopen(project_url).read()
    repositories = scrape_repositories_from_project_page(html)

    for repo in repositories:
        mrq_overview_url = mrq_overview_page_url_template % dict(host=host, project=project, repo=repo)
        html = urllib2.urlopen(mrq_overview_url)
        open_mrqs = scrape_mrq_status_from_mrq_page(html)
        add_repo_info_to_mrqs(open_mrqs, repo)
        mrqs.extend(open_mrqs)

    return mrqs

TIMEOUT=40

class MergeRequestRetrieverProtocol(object):
    def __init__(self):
        self.with_errors = 0
        self.error_list = []

    def gotError(self, traceback, extra_args):
        print traceback, extra_args
        self.with_errors += 1
        self.error_list.append(extra_args)

    def getPage(self, data, args):
        # TODO: be nice and use HTTP conditional GET to reduce load
        # http://fishbowl.pastiche.org/2002/10/21/http_conditional_get_for_rss_hackers/
        # http://www.phppatterns.com/docs/develop/twisted_aggregator
        return client.getPage(data, args, timeout=TIMEOUT)

    def start(self, host, project):

        project_url = project_page_url_template % dict(host=host, project=project)
        d = defer.succeed(project_url)

        d.addCallback(self.getPage, project_url)
        d.addErrback(self.gotError, (project_url, 'getting project page'))

        d.addCallback(self.scrapeProjectPage)
        d.addErrback(self.gotError, (project_url, 'scraping project page'))

        d.addCallback(self.processRepositoryList, host, project)
        d.addErrback(self.gotError, (project_url, ''))

        d.addCallback(self.unNestList)
        d.addErrback(self.gotError, (project_url, ''))

        return d

    def scrapeProjectPage(self, html):
        return scrape_repositories_from_project_page(html)

    def processRepositoryList(self, repositories, host, project):
        deferred_list = []

        for repo in repositories:
            mrq_overview_url = str(mrq_overview_page_url_template % dict(host=host, project=project, repo=repo))
            d = defer.succeed(mrq_overview_url)

            d.addCallback(self.getPage, mrq_overview_url)
            d.addErrback(self.gotError, (mrq_overview_url, 'retrieving %s' % mrq_overview_url))

            d.addCallback(self.scrapeMergeRequestPage, host, project, repo)
            d.addErrback(self.gotError, (mrq_overview_url, 'scraping merge requests for %s' % repo))

            deferred_list.append(d)

        return defer.gatherResults(deferred_list)

    def scrapeMergeRequestPage(self, html, host, project, repo):
        open_mrqs = scrape_mrq_status_from_mrq_page(html)
        add_repo_info_to_mrqs(open_mrqs, repo)
        return open_mrqs

    def unNestList(self, nested_list):
        flat = []
        for list in nested_list:
            flat.extend(list)
        return flat


    def printResult(self, data):
        print data


class MergeRequestRetriever(protocol.ClientFactory):
    protocol = MergeRequestRetrieverProtocol()

    def __init__(self):
        self.protocol.factory = self

    def start(self, project, host):
        return self.protocol.start(project, host)

if __name__ == '__main__':

    from twisted.internet import reactor

    client = MergeRequestRetriever()

    def print_mergerequests(data):
        print data

    d = client.start('http://gitorious.org', 'maliit')

    d.addCallback(print_mergerequests)

    reactor.run()


