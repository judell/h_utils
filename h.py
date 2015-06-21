"""
/activity

/feed?tags=[TAG]

/urlfeed?url=[URL]

/multi_tag?tags=[TAG1,TAG2]
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


def multi_tag(request):
    tags = urlparse.parse_qs(request.query_string)['tags'][0]
    tags = tags.split(',')
    tags = [t.strip() for t in tags]
    tags = [urllib.quote(t) for t in tags]
    args = ['tags=' + a for a in tags]
    args = '&'.join(args)
    j = call_search_api(args)
    body = make_multi_tag(j,tags)
    return Response(body.encode('utf-8'))

def dispatch(request):
    q = urlparse.parse_qs(request.query_string)
    if q.has_key('method'):
        if q['method'][0] == 'urlfeed':
            return urlfeed(request)
        if q['method'][0] == 'feed':
            return feed(request)
        if q['method'][0] == 'activity':
            return activity(request)
        if q['method'][0] == 'multi_tag':
            return multi_tag(request)

def make_multi_tag(j,tags):
    rows = j['rows']
    html = """<html>
<head>
 <style>
 body { font-family:verdana;margin:.5in }
 h1 { font-weight: bold; margin-bottom:10pt }
 p.attribution { font-size: smaller; }
 </style>
<body>%s</body>
</html>
""" 
    s = '<h1>Search for tags: ' + ','.join(tags) + '</h1>'
    s += '<h2>found ' + str(len(rows)) + '</h2><hr>'
    for row in rows:
        raw = HypothesisRawAnnotation(row)
        updated = raw.updated
        user = raw.user
        uri = raw.uri
        text = raw.text
        tags = raw.tags
        s += '<p><a href="%s">%s</a></p>' % ( uri, uri)
        s += '<p>%s</p>' % text
        tags = ['<a href="' + host_port + '/?method=multi_tag&tags=' + urllib.quote(t) + '">' + t + '</a>' for t in tags]
        s += '<p class="attribution">%s - %s - %s</p>' % ( user, updated, ', '.join(tags))
        s += '<hr>'
    #return (html % s).encode('utf-8')
    return (html % s)

def feed(request):
    facet = 'tags'
    value = urlparse.parse_qs(request.query_string)[facet][0]
    h_url = 'https://hypothes.is/api/search?tags=' + value
    return feed_helper(h_url, facet, value)

def urlfeed(request):
    facet = 'url'
    value = urlparse.parse_qs(request.query_string)[facet][0]
    h_url = 'https://hypothes.is/api/search?uri=' + value
    return feed_helper(h_url, facet, value)

def feed_helper(h_url, facet, value):
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
    j = HypothesisUtils().call_search_api()
    body = make_activity(j)

    return Response(body.encode('utf-8'))

def make_activity(j):
    users = defaultdict(int)
    days = defaultdict(int)
    rows = j['rows']
    for row in rows:
        raw = HypothesisRawAnnotation(row)
        created = row.updated[0:19]
        day = created[0:10]
        days[day] += 1
        user = row.user
        users[user] += 1
        uri = row.uri

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
        url = alt_stream + '/stream.alt?user=' +  uname
        s += '<div><a target="_new" title="see annotation activity" href="%s">%s</a>: %s</div>' % (url, uname, user[1])

    return html % s

def make_feed(j, facet, value):
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
    config.add_route('dispatch', '/')
    config.add_view(dispatch, route_name='dispatch')

    config.add_route('feed', '/feed')
    config.add_view(feed, route_name='feed')

    config.add_route('urlfeed', '/urlfeed')
    config.add_view(urlfeed, route_name='urlfeed')

    config.add_route('activity', '/activity')
    config.add_view(activity, route_name='activity')

    config.add_route('multi_tag', '/multi_tag')
    config.add_view(multi_tag, route_name='multi_tag')

    config.add_route('alt_stream', '/stream.alt')
    config.add_view(HypothesisStream.alt_stream, route_name='alt_stream')

    config.add_route('alt_stream_js', '/stream.alt.js')
    config.add_view(HypothesisUtils.alt_stream_js, route_name='alt_stream_js')

    app = config.make_wsgi_app()
    server = make_server(host, port, app)
    server.serve_forever()
    



 


  
 
