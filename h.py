"""
/activity
/feed?tags=[TAG]
/urlfeed?url=[URL]
"""

import json, urllib, requests, re, traceback, types, pyramid
from h_util import *
from collections import defaultdict
from datetime import datetime
from feedgen.feed import FeedGenerator
import urlparse, operator

host = 'localhost'
#host = 'h.jonudell.info'
port = 8080
host_port = 'http://' + host + ':' + str(port)
alt_stream = 'https://alt-stream.dokku.hypothes.is'

def feed(request):
    """Temporary until official H Atom feed."""
    facet = 'tags'
    value = urlparse.parse_qs(request.query_string)[facet][0]
    h_url = 'https://hypothes.is/api/search?tags=' + value
    return feed_helper(h_url, facet, value)

def urlfeed(request):
    """Temporary until official H Atom feed."""
    facet = 'url'
    value = urlparse.parse_qs(request.query_string)[facet][0]
    h_url = 'https://hypothes.is/api/search?uri=' + value
    return feed_helper(h_url, facet, value)

def feed_helper(h_url, facet, value):
    """Temporary until official H Atom feed."""
    s = requests.get(h_url).text.decode('utf-8')
    j = json.loads(s)
    body = make_feed(j, facet, value)
    r = Response(body.encode('utf-8'))
    r.content_type = 'application/xml'
    return r

def _feed(request,facet):

    value = urlparse.parse_qs(request)[facet][0]
    if facet == 'tag':
        h_url = 'https://hypothes.is/api/search?tags=' + value
    if facet == 'url':
        h_url = 'https://hypothes.is/api/search?uri=' + value
    s = requests.get(h_url).text.decode('utf-8')
    j = json.loads(s)
    body = make_feed(j, facet, value)
    return Response(body.encode('utf-8'))

def activity(request):
    """Quick and dirty report on recent activity: users/day, most-active users."""
    j = HypothesisUtils().search()
    body = make_activity(j)
    return Response(body.encode('utf-8'))

def make_activity(j):
    """Activity report."""
    users = defaultdict(int)
    days = defaultdict(int)
    rows = j['rows']
    for row in rows:
        raw = HypothesisRawAnnotation(row)
        created = raw.updated
        day = created[0:10]
        days[day] += 1
        user = raw.user
        users[user] += 1
        uri = raw.uri

    days = sorted(days.items(), key=operator.itemgetter(0,1), reverse=True)

    users = sorted(users.items(), key=operator.itemgetter(1,0), reverse=True)

    html = """
<html>
<head><style>
body { font-family: verdana; margin: .2in; }
</style></head>
<body>
<h1>Hypothesis recent 200 annotations</h1>
%s
</body>
</html>
 """
    s = '<p>days: %s </p>' % len(days)
    for day in days:
        s += '<div>%s: %s</div>' % (day[0], day[1])

    s += '<p>users: %s</p>' % len(users)
    for user in users:
        uname = re.sub('.+\\:','',user[0])
        uname = re.sub('@.+','',uname)
        url = alt_stream + '/stream.alt?by_url=no&user=' +  uname
        s += '<div><a target="_new" title="see annotation activity" href="%s">%s</a>: %s</div>' % (url, uname, user[1])

    return html % s

def make_feed(j, facet, value):
    """Temporary until official H Atom feed."""
    url = host_port + '/'
    rows = j['rows']
    fg = FeedGenerator()
    fg.title('h stream for ' + facet + ' ' + value)
    fg.description('desc')
    fg.link(href='%s' % (url), rel='self')
    fg.id(url)
    for r in rows:
        raw = HypothesisRawAnnotation(r)
        user = raw.user
        uri = raw.uri
        doc_title = raw.doc_title
        title = 'note by %s on "%s" (%s)' % ( user, doc_title, uri )
        fe = fg.add_entry()
        fe.title(title)
        fe.link(href="https://hypothes.is/a/%s" % r['id'])
        fe.id("https://hypothes.is/a/%s" % r['id'])
        fe.author({'name': r['user']})
        content = ''
        if r.has_key('text'):
            content += ': ' + r['text']
        if r.has_key('tags'):
            content += ' [tags: %s]' % ','.join(r['tags'])
        fe.content(content)
    str = fg.atom_str(pretty=True)
    return str

if __name__ == '__main__':

    from wsgiref.simple_server import make_server
    from pyramid.config import Configurator
    from pyramid.response import Response

    config = Configurator()

    config.add_route('feed', '/feed')
    config.add_view(feed, route_name='feed')

    config.add_route('urlfeed', '/urlfeed')
    config.add_view(urlfeed, route_name='urlfeed')

    config.add_route('activity', '/activity')
    config.add_view(activity, route_name='activity')

    config.add_route('alt_stream', '/stream.alt')
    config.add_view(HypothesisStream.alt_stream, route_name='alt_stream')

    config.add_route('alt_stream_js', '/stream.alt.js')
    config.add_view(HypothesisUtils.alt_stream_js, route_name='alt_stream_js')

    app = config.make_wsgi_app()
    server = make_server(host, port, app)
    server.serve_forever()
    



 


  
 
