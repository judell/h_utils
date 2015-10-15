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

#host = 'localhost'
host = 'h.jonudell.info'
port = 8080
host_port = 'http://' + host + ':' + str(port)
alt_stream = 'http://h.jonudell.info:5000'

def group_urls(request):
    group = urlparse.parse_qs(request.query_string)['group'][0]
    api_call = "https://hypothes.is/api/search?limit=200&group=" + group
    h = HypothesisUtils(username='judell',password='hy$qvr')
    h.login()
    headers = {'Authorization': 'Bearer ' + h.token, 'Content-Type': 'application/json;charset=utf-8' }
    r = requests.get(api_call, headers=headers)
    text = r.text.decode('utf-8')
    obj = json.loads(text)
    rows = obj['rows']
    urls = defaultdict(int)
    users = defaultdict(int)
    for row in rows:
        raw = HypothesisRawAnnotation(row)
        urls[raw.uri] += 1
        users[raw.user] += 1

    urls_as_html = ''
    url_keys = urls.keys()
    url_keys.sort()
    for url in url_keys:
        urls_as_html += '<p><a href="%s">%s</a> (%s)</p>' % (url, url, urls[url])

    users_as_html = ''
    user_keys = users.keys()
    user_keys.sort()
    for user in user_keys:
        users_as_html += '<p>%s (%s)</p>' % (user, users[user])

    html = """
<html>
<head><style>
body { font-family: verdana; margin: .5in; }
</style></head>
<body>
<h1>Annotated URLs for group %s</h1>
%s
<h1>Users active in group %s</h1>
%s
</body>
</html>
 """ % ( group, urls_as_html, group, users_as_html)
    r = Response(html.encode('utf-8'))
    r.content_type = 'text/html'
    return r

def count(request):
    url = urlparse.parse_qs(request.query_string)['url'][0]
    api_call = "https://hypothes.is/api/search?uri=" + url
    r = requests.get(api_call);
    text = r.text.decode('utf-8')
    obj = json.loads(text)
    html = str(obj['total'])
    r = Response(html.encode('utf-8'))
    r.content_type = 'text/html'
    return r

def gsearch(request):
    text = urlparse.parse_qs(request.query_string)['text'][0]
    print request.query_string
    print 'text: ' + text
    html = '<https://groups.google.com/a/list.hypothes.is/forum/#!search/%s>' % text
    print html
    r = Response(html.encode('utf-8'))
    r.content_type = 'text/html'
    return r

def annos_for_url(request):
    url = urlparse.parse_qs(request.query_string)['url'][0]
    api_call = "https://hypothes.is/api/search?limit=200&uri=" + url
    r = requests.get(api_call);
    text = r.text.decode('utf-8')
    obj = json.loads(text)
    rows = obj['rows']
    html = """
<html>
<head><style>
body { font-family: verdana; margin: .5in; }
</style></head>
<body>
<h1>Hypothesis annotations for %s</h1>
%s
</body>
</html>
 """
    annos = {}
    for row in rows:
        raw = HypothesisRawAnnotation(row)
        annos[raw.id] = { 'user':raw.user, 'start':raw.start, 'end':raw.end, 'prefix':raw.prefix, 'exact':raw.exact, 'suffix':raw.suffix, 'text':raw.text, 'tags':raw.tags }
    ids = {}
    for id in annos.keys():
        ids[id] = annos[id]['start']

    sorted_ids = sorted(ids.items(), key = operator.itemgetter(1,0))
    _html = ''
    for sorted_id in sorted_ids:
      id = sorted_id[0]
      start = sorted_id[1]
      if start is None:
          continue
      anno = annos[id]
      tags = anno['tags']
      tags_html = ''
      if len(tags):
          tags_html = '<div><b>Tags:</b> ' + ', '.join(tags) + '</div>'
      _html += '<p><div><b>User:</b> %s</div><div><b>Start/End</b>: %s/%s</div><div><b>Quote</b>: <span style="color:gray">%s</span> %s <span style="color:gray">%s</span></div><div><b>Text</b>: %s</div> %s </p>' %  ( anno['user'], anno['start'], anno['end'], anno['prefix'], anno['exact'], anno['suffix'], anno['text'], tags_html )
    html = html % (url, _html)
    r = Response(html.encode('utf-8'))
    r.content_type = 'text/html'
    return r

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
    minutes = defaultdict(int)
    rows = j['rows']
    for row in rows:
        raw = HypothesisRawAnnotation(row)
        created = raw.updated
        minute = created[0:16]
        minutes[minute] += 1
        user = raw.user
        users[user] += 1
        uri = raw.uri

    minutes = sorted(minutes.items(), key=operator.itemgetter(0,1), reverse=True)

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
    s = '<p>minutes: %s </p>' % len(minutes)
    for minute in minutes:
        s += '<div>%s: %s</div>' % (minute[0], minute[1])

    s += '<p>users: %s</p>' % len(users)
    for user in users:
        uname = re.sub('.+\\:','',user[0])
        uname = re.sub('@.+','',uname)
        url = alt_stream + '/stream.alt?user=' +  uname
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
        fe = fg.add_entry()
        fe.title(doc_title + ' ' + r['uri'])
        fe.link(href="https://via.hypothes.is/%s" % r['uri'])
        fe.id("https://hypothes.is/a/%s" % r['id'])
        fe.author({'name': r['user']})
        content = '<p>note by %s on "%s" (%s)</p>' % ( user, doc_title, uri )
        if r.has_key('text'):
            content += '<p>%s</p>' % r['text']
        if r.has_key('tags'):
            content += '<p>[tags: %s]</p>' % ','.join(r['tags'])
        fe.content(content)
    str = fg.rss_str(pretty=True)
    return str

if __name__ == '__main__':

    from wsgiref.simple_server import make_server
    from pyramid.config import Configurator
    from pyramid.response import Response

    config = Configurator()

    config.add_route('annos_for_url', '/annos_for_url')
    config.add_view(annos_for_url, route_name='annos_for_url')

    config.add_route('feed', '/feed')
    config.add_view(feed, route_name='feed')

    config.add_route('urlfeed', '/urlfeed')
    config.add_view(urlfeed, route_name='urlfeed')

    config.add_route('activity', '/activity')
    config.add_view(activity, route_name='activity')

    config.add_route('alt_stream', '/stream.alt')
    config.add_view(HypothesisStream.alt_stream, route_name='alt_stream')

    config.add_route('alt_stream_js', '/stream.alt.js')
    config.add_view(HypothesisStream.alt_stream_js, route_name='alt_stream_js')

    config.add_route('gsearch', '/gsearch')
    config.add_view(gsearch, route_name='gsearch')

    config.add_route('count', '/count')
    config.add_view(count, route_name='count')

    config.add_route('group_urls', '/group_urls')
    config.add_view(group_urls, route_name='group_urls')

    app = config.make_wsgi_app()
    server = make_server(host, port, app)
    server.serve_forever()
    



 


  
 
